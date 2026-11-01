"""A stored turn keeps everything that ran, however the answer ends; history never breaks answering."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.application.use_cases.chatbot.chat_turn import ChatTurn
from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.domain.entities.conversations import (
    ChatTurnContext,
    ConversationRead,
    MessageStatus,
)
from backend.domain.entities.llm import MessageRole
from backend.domain.entities.retrieval_plan import PreLLMExtraction
from backend.domain.errors import DependencyUnavailableError, NotFoundError
from backend.domain.settings.chat import ConversationHistorySettings
from tests.backend.unit.application.services.router.factories import INSTITUTION

HISTORY = ConversationHistorySettings(max_turns=3, max_chars_per_message=1500)
DEVICE = ChatTurnContext(client_id_hash="device", request_id="req-1", trace_id="a" * 32)


class Conversations:
    """In-memory ConversationRepository; `fail` makes every write raise, as an outage would."""

    def __init__(self, fail=False):
        self.fail, self.owners, self.messages = fail, {}, []

    async def create_conversation(self, payload):
        self._check()
        conversation_id = uuid4()
        self.owners[conversation_id] = payload.client_id_hash
        return conversation_id

    async def fetch_conversations(self, page_params, filters, *, view_model=ConversationRead):
        now = datetime.now(UTC)
        return [
            ConversationRead(id=filters.id, client_id_hash=owner, created_at=now, updated_at=now)
            for conversation_id, owner in self.owners.items()
            if conversation_id == filters.id and owner == filters.client_id_hash
        ]

    async def append_message(self, payload):
        self._check()
        self.messages.append(payload)

    async def fetch_messages(self, page_params, filters, *, view_model):
        self._check()
        stored = [
            view_model.model_validate(message.model_dump() | {"id": index, "position": index, "created_at": datetime.now(UTC)})
            for index, message in enumerate(self.messages, start=1)
            if message.conversation_id == filters.conversation_id
        ]
        return list(reversed(stored))[:page_params.limit]   # Newest first, as ChatTurn asks.

    def _check(self):
        if self.fail:
            raise ConnectionError("database down")


def app_db(conversations):
    @asynccontextmanager
    async def start():
        yield SimpleNamespace(conversations=conversations)

    return SimpleNamespace(start=start)


def chat_turn(chatbot, conversations):
    db = app_db(conversations)
    return ChatTurn(chatbot, db, ConversationHistory(db, INSTITUTION), HISTORY)


class Chatbot:
    """Records a plan, streams `chunks`, then raises `failure` (if any) or waits forever if `hang`."""

    def __init__(self, chunks=("CP264 ", "is offered."), failure=None, hang=False):
        self.chunks, self.failure, self.hang = chunks, failure, hang

    async def ask(self, question, recorder, memory):
        self.earlier = memory.earlier
        recorder.query_plan = PreLLMExtraction()
        for chunk in self.chunks:
            recorder.record_answer_event({"type": "text", "text": chunk})
            yield chunk
        if self.hang:
            await asyncio.Event().wait()
        if self.failure:
            raise self.failure


async def run(turn, context=DEVICE):
    conversation_id, answer = await turn.start("Is CP264 offered in winter?", context)
    return conversation_id, [line async for line in answer]


async def test_completed_turn_stores_question_then_answer_with_diagnostics():
    conversations = Conversations()

    conversation_id, lines = await run(chat_turn(Chatbot(), conversations))

    question, answer = conversations.messages
    assert lines == ["CP264 ", "is offered."]
    assert conversations.owners == {conversation_id: "device"}
    assert (question.role, question.content) == (MessageRole.USER, "Is CP264 offered in winter?")
    assert (answer.role, answer.status, answer.content) == (MessageRole.ASSISTANT, MessageStatus.COMPLETE, "CP264 is offered.")
    assert answer.query_plan is not None and answer.trace_id == "a" * 32
    assert answer.error_type is None
    assert answer.answer_content.blocks[0].text == "CP264 is offered."


async def test_failure_mid_answer_stores_partial_text_plan_and_error_then_still_raises():
    conversations = Conversations()
    failure = DependencyUnavailableError("The answer service is unavailable", internal_detail="LLM timed out")
    turn = chat_turn(Chatbot(chunks=("CP264 ",), failure=failure), conversations)

    with pytest.raises(DependencyUnavailableError):
        await run(turn)

    answer = conversations.messages[-1]
    assert (answer.status, answer.content) == (MessageStatus.ERROR, "CP264 ")
    assert (answer.error_type, answer.error_code, answer.error_message) == (
        "DependencyUnavailableError", "dependency_unavailable", "LLM timed out",
    )
    assert answer.query_plan is not None
    assert answer.answer_content.blocks[0].text == "CP264 "


async def test_student_disconnecting_stores_an_interrupted_answer():
    conversations = Conversations()
    turn = chat_turn(Chatbot(chunks=("CP264 ",), hang=True), conversations)
    _, answer = await turn.start("Is CP264 offered in winter?", DEVICE)

    async def consume():
        async for _ in answer:
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.gather(*turn._saving)  # The save outlives the cancelled stream.

    answer_message = conversations.messages[-1]
    assert (answer_message.status, answer_message.content) == (MessageStatus.INTERRUPTED, "CP264 ")
    assert answer_message.answer_content.blocks[0].text == "CP264 "


async def test_history_outage_never_breaks_the_answer():
    turn = chat_turn(Chatbot(), Conversations(fail=True))

    conversation_id, lines = await run(turn)

    assert conversation_id is None
    assert lines == ["CP264 ", "is offered."]


async def test_continuing_another_devices_conversation_is_not_found():
    conversations = Conversations()
    theirs = await conversations.create_conversation(SimpleNamespace(client_id_hash="their-device"))
    turn = chat_turn(Chatbot(), conversations)

    with pytest.raises(NotFoundError):
        await turn.start("question", DEVICE.model_copy(update={"conversation_id": theirs}))
    assert conversations.messages == []


async def test_continuing_an_owned_conversation_appends_to_it():
    conversations = Conversations()
    mine = await conversations.create_conversation(SimpleNamespace(client_id_hash="device"))

    conversation_id, _ = await run(chat_turn(Chatbot(), conversations), DEVICE.model_copy(update={"conversation_id": mine}))

    assert conversation_id == mine
    assert {message.conversation_id for message in conversations.messages} == {mine}


async def test_a_follow_up_sees_the_earlier_completed_turn_but_not_itself():
    conversations = Conversations()
    chatbot = Chatbot()
    turn = chat_turn(chatbot, conversations)
    first, _ = await run(turn)

    await run(turn, DEVICE.model_copy(update={"conversation_id": first}))

    assert [(message.role, message.content) for message in chatbot.earlier] == [
        (MessageRole.USER, "Is CP264 offered in winter?"),
        (MessageRole.ASSISTANT, "CP264 is offered."),
    ]
