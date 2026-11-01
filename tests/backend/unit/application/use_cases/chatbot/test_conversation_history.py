"""History is scoped to the device: anything outside it is not found, and only answers can be rated."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.domain.entities.answer_content import (
    AnswerCitationBlock,
    AnswerTableBlock,
    StoredAnswerContent,
)
from backend.domain.entities.conversations import (
    ChatMessageRead,
    ConversationSummary,
    FeedbackRating,
    MessageFeedbackCreate,
)
from backend.domain.entities.llm import MessageRole
from backend.domain.errors import NotFoundError
from tests.backend.unit.application.services.router.factories import INSTITUTION

NOW = datetime.now(UTC)
MINE, THEIRS = uuid4(), uuid4()


def stored(message_id, conversation_id, role):
    return ChatMessageRead(
        id=message_id, position=message_id, conversation_id=conversation_id, role=role,
        content="text", created_at=NOW,
    )


class Conversations:
    """In-memory ConversationRepository holding one conversation per device."""

    def __init__(self):
        self.owners = {MINE: "my-device", THEIRS: "their-device"}
        self.messages = [
            stored(1, MINE, MessageRole.USER), stored(2, MINE, MessageRole.ASSISTANT),
            stored(3, THEIRS, MessageRole.ASSISTANT),
        ]
        self.feedback = []

    async def fetch_conversations(self, page_params, filters, *, view_model):
        return [
            ConversationSummary(id=conversation_id, title=None, created_at=NOW, updated_at=NOW)
            for conversation_id, owner in self.owners.items()
            if owner == filters.client_id_hash and filters.id in (None, conversation_id)
        ]

    async def fetch_messages(self, page_params, filters, *, view_model):
        return [
            view_model.model_validate(message.model_dump()) for message in self.messages
            if filters.id in (None, message.id) and filters.conversation_id in (None, message.conversation_id)
        ]

    async def delete_conversations(self, filters):
        if self.owners.get(filters.id) != filters.client_id_hash:
            return 0
        del self.owners[filters.id]
        return 1

    async def upsert_feedback(self, payload):
        self.feedback.append(payload)


@pytest.fixture
def conversations():
    return Conversations()


@pytest.fixture
def history(conversations):
    @asynccontextmanager
    async def start():
        yield SimpleNamespace(conversations=conversations)

    return ConversationHistory(SimpleNamespace(start=start), INSTITUTION)


def thumbs_up(message_id):
    return MessageFeedbackCreate(message_id=message_id, rating=FeedbackRating.UP)


async def test_lists_only_this_devices_conversations(history):
    assert [summary.id for summary in await history.list_conversations("my-device", 30, 0)] == [MINE]


async def test_messages_hide_internal_diagnostics(history):
    messages = await history.messages("my-device", MINE, 200, 0)

    assert [message.id for message in messages] == [1, 2]
    assert "query_plan" not in messages[0].model_dump()


async def test_history_returns_saved_content_and_only_public_source_metadata(history, conversations):
    content = StoredAnswerContent(blocks=[AnswerTableBlock(title="Sections", columns=["Section"], rows=[["A"]])])
    conversations.messages[1] = conversations.messages[1].model_copy(update={
        "answer_content": content,
        "sources": [{"title": "CP264", "url": "https://loris.wlu.ca", "private_diagnostic": "secret"}],
        "query_plan": {"internal": "plan"}, "request_id": "private-request", "trace_id": "a" * 32,
    })

    _question, answer = await history.messages("my-device", MINE, 200, 0)

    assert answer.answer_content == content
    assert answer.sources[0].title == "CP264"
    public = answer.model_dump()
    assert not {"query_plan", "request_id", "trace_id", "retrieval_outcomes", "error_message"} & public.keys()
    assert "private_diagnostic" not in public["sources"][0]


async def test_another_devices_conversation_is_not_found(history):
    with pytest.raises(NotFoundError):
        await history.messages("my-device", THEIRS, 200, 0)
    with pytest.raises(NotFoundError):
        await history.delete("my-device", THEIRS)


async def test_history_merges_old_registration_sources_and_preserves_calendar_citation(history, conversations):
    url = str(INSTITUTION.registration_url)
    calendar = "https://academic-calendar.wlu.ca/cp264"
    original = conversations.messages[1].model_copy(update={
        "sources": [
            {"title": "Section A", "url": url, "source_type": "course_terms"},
            {"title": "Section B", "url": url, "source_type": "course_terms"},
            {"title": "CP264", "url": calendar, "source_type": "courses"},
        ],
        "answer_content": StoredAnswerContent(blocks=[AnswerCitationBlock(source_nums=[2, 3], urls=[url, calendar])]),
    })
    conversations.messages[1] = original
    _question, answer = await history.messages("my-device", MINE, 200, 0)

    assert [source.title for source in answer.sources] == ["LORIS - Registration", "CP264"]
    assert answer.answer_content.blocks[0].source_nums == [1, 2]
    assert answer.answer_content.blocks[0].urls == [url, calendar]
    assert conversations.messages[1] is original
    assert len(original.sources) == 3


async def test_rating_an_own_answer_is_stored(history, conversations):
    await history.rate("my-device", thumbs_up(2))

    assert conversations.feedback == [thumbs_up(2)]


@pytest.mark.parametrize("message_id", [1, 3, 99], ids=["a-question", "another-devices-answer", "missing"])
async def test_only_own_answers_can_be_rated(history, conversations, message_id):
    with pytest.raises(NotFoundError, match="Message not found"):
        await history.rate("my-device", thumbs_up(message_id))
    assert conversations.feedback == []
