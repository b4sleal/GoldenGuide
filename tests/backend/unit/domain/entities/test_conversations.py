"""Stored messages are self-consistent: questions have text, and only errored answers carry an error."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.domain.entities.conversations import ChatMessageCreate, MessageStatus
from backend.domain.entities.llm import MessageRole
from backend.domain.ports.repositories.filters import ConversationFilter

CONVERSATION = uuid4()


def message(**fields) -> ChatMessageCreate:
    return ChatMessageCreate(**({"conversation_id": CONVERSATION, "role": MessageRole.ASSISTANT, "content": ""} | fields))


def test_answer_that_failed_before_any_text_is_storable():
    stored = message(status=MessageStatus.ERROR, error_type="TimeoutError")
    assert stored.content == ""


def test_question_needs_content():
    with pytest.raises(ValidationError, match="needs content"):
        message(role=MessageRole.USER)


@pytest.mark.parametrize("fields", [
    {"status": MessageStatus.ERROR},                                        # Error without its type.
    {"status": MessageStatus.COMPLETE, "error_type": "TimeoutError"},       # Error type on a success.
    {"status": MessageStatus.INTERRUPTED, "error_type": "TimeoutError"},
])
def test_error_details_appear_only_on_errored_messages(fields):
    with pytest.raises(ValidationError, match="error_type"):
        message(**fields)


def test_conversation_filter_knows_when_it_is_empty():
    assert ConversationFilter().is_empty()
    assert not ConversationFilter(client_id_hash="device").is_empty()
