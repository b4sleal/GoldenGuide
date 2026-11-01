"""Chat conversation settings (catalogs/chat/chat.yml)."""
from pydantic import BaseModel, ConfigDict, Field


class FrozenChatSettings(BaseModel):
    model_config = ConfigDict(frozen=True)


class ConversationHistorySettings(FrozenChatSettings):
    """How much of the conversation the answer model sees with each new question."""
    max_turns: int = Field(ge=0, description="Earlier completed question/answer pairs to include; 0 disables history.")
    max_chars_per_message: int = Field(gt=0, description="Each earlier message is cut to this many characters.")


class ChatSettings(FrozenChatSettings):
    conversation_history: ConversationHistorySettings
