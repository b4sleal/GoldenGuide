"""AI behavior settings: router/generation prompts (runtime-editable), retrieval profile catalog,
and the retrieval -> generation contract (ResolvedRAGContext).
"""
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.domain.entities.retrieval import EvidenceTable
from backend.domain.settings.profiles import LLMProfile, RetrievalProfile

# -------------------------------------------------
# Base
# -------------------------------------------------

class FrozenAIBehavior(BaseModel):
    model_config = ConfigDict(frozen=True)

# -------------------------------------------------
# Runtime defaults (still domain — affects behavior)
# -------------------------------------------------
class PromptTemplate(FrozenAIBehavior):
    """An LLM prompt: fixed instructions plus a per-question template.

    `system` never changes between questions, so providers can cache it. `turn` holds everything that
    does (date, context, question) and is filled with str.format.
    """
    system: str = Field(min_length=1)
    turn: str = Field(min_length=1)

class RouterLLM(PromptTemplate):
    pass

class GenerationLLM(PromptTemplate):
    pass

class RuntimeDefaultsCatalog(FrozenAIBehavior):
    version: int = 1
    router_llm: RouterLLM
    generation_llm: GenerationLLM


type RetrievalStrategy = Mapping[str, str]


class AIBehaviorSettings(FrozenAIBehavior):
    """Startup AI defaults and retrieval strategy, with their shared YAML-controlled version."""

    version: int = Field(default=1, ge=1)
    runtime_defaults: RuntimeDefaultsCatalog
    retrieval_strategy: RetrievalStrategy

    @model_validator(mode="before")
    @classmethod
    def apply_version(cls, value: Any) -> Any:
        """Copy the YAML version into defaults without modifying the caller's configuration."""
        if not isinstance(value, dict):
            return value

        data = dict(value)
        defaults = dict(data.get("runtime_defaults") or {})

        # SettingsService uses this version to decide whether persisted defaults need refreshing.
        defaults["version"] = data.get("version", 1)
        data["runtime_defaults"] = defaults

        return data


type RetrievalProfileCatalog = Mapping[str, RetrievalProfile]

# External
class RAGSource(FrozenAIBehavior):
    title: str
    url: str | None = None
    source_type: str | None = None

class ResolvedRAGContext(FrozenAIBehavior):
    """The formal contract between Retrieval and Generation."""
    context_text: str
    sources: list[RAGSource]
    llm_profile: LLMProfile
    profile_name: str
    links: dict[str, str] = Field(default_factory=dict)
    # Tables the answer may place with {{TABLE:<table_id>}} markers (application/use_cases/chatbot/evidence_tables.py).
    tables: list[EvidenceTable] = Field(default_factory=list)
    # Semantic search was requested but every retrieval profile failed; the context holds structured records only.
    semantic_failed: bool = False


