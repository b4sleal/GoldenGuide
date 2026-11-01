"""An LLM request is a valid conversation: never empty, always ending with the turn to answer."""
import pytest
from pydantic import ValidationError

from backend.domain.entities.llm import LLMRequest, Message, MessageRole

USER = Message(role=MessageRole.USER, content="Is CP264 offered in winter?")
ASSISTANT = Message(role=MessageRole.ASSISTANT, content="CP264 requires CP164.")


def test_single_turn_is_one_user_message():
    request = LLMRequest.single_turn("question", system="rules")

    assert request.system == "rules"
    assert request.messages == (Message(role=MessageRole.USER, content="question"),)


def test_history_keeps_its_order():
    request = LLMRequest(messages=(USER, ASSISTANT, USER))

    assert [message.role for message in request.messages] == ["user", "assistant", "user"]


@pytest.mark.parametrize("messages", [(), (USER, ASSISTANT)], ids=["empty", "ends-with-assistant"])
def test_request_must_end_with_a_user_message(messages):
    with pytest.raises(ValidationError):
        LLMRequest(messages=messages)


def test_blank_system_instructions_are_rejected_not_sent():
    with pytest.raises(ValidationError):
        LLMRequest.single_turn("question", system="")
