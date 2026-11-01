"""Provider-neutral LLM request: system instructions plus a role-separated conversation.

Adapters translate it to their vendor's native format; the application never builds vendor payloads.
New per-call options (tools, output limits...) are added here as typed fields when a caller needs them.
"""
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Kept separate from messages: every provider passes system instructions on their own channel.
    system: str | None = Field(default=None, min_length=1)
    # Earlier turns in order, ending with the message to answer.
    messages: tuple[Message, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ends_with_user_message(self) -> Self:
        if self.messages[-1].role is not MessageRole.USER:
            raise ValueError("An LLM request must end with a user message")
        return self

    @classmethod
    def single_turn(cls, content: str, system: str | None = None) -> Self:
        """A request with no conversation history."""
        return cls(system=system, messages=(Message(role=MessageRole.USER, content=content),))
