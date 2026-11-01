"""Adapters translate one provider-neutral request into each vendor's native conversation format."""
from backend.domain.entities.llm import LLMRequest, Message, MessageRole
from backend.infra.ml.llms.gemini import to_contents
from backend.infra.ml.llms.openai import to_messages

CONVERSATION = LLMRequest(
    system="Answer from the evidence only.",
    messages=(
        Message(role=MessageRole.USER, content="CP264 prerequisites?"),
        Message(role=MessageRole.ASSISTANT, content="CP164."),
        Message(role=MessageRole.USER, content="Is it offered in winter?"),
    ),
)


def test_gemini_names_the_assistant_turn_model_and_keeps_system_out_of_contents():
    contents = to_contents(CONVERSATION)

    assert [content.role for content in contents] == ["user", "model", "user"]
    assert [part.text for content in contents for part in content.parts or []] == [
        "CP264 prerequisites?", "CP164.", "Is it offered in winter?",
    ]


def test_openai_sends_system_first_then_the_conversation():
    assert to_messages(CONVERSATION) == [
        {"role": "system", "content": "Answer from the evidence only."},
        {"role": "user", "content": "CP264 prerequisites?"},
        {"role": "assistant", "content": "CP164."},
        {"role": "user", "content": "Is it offered in winter?"},
    ]


def test_openai_omits_the_system_message_when_there_is_none():
    assert to_messages(LLMRequest.single_turn("question")) == [{"role": "user", "content": "question"}]
