"""Fit structured (database) evidence into the prompt's token budget by choosing a detail tier.

Every Evidence record carries up to three renderings: detailed `content`, `compact_content` and
`minimal_content`. The whole set uses one tier, the richest that the DBEvidenceProfile allows; when
even the minimal tier exceeds the budget, a ValueError is raised and the orchestrator reports the
request as UNSUPPORTED (it never silently drops records).
"""
from enum import StrEnum

import structlog

from backend.domain.entities.retrieval import Evidence
from backend.domain.settings.profiles import DBEvidenceProfile

logger = structlog.get_logger(__name__)


class DBEvidenceTier(StrEnum):
    DETAILED = "detailed"
    COMPACT = "compact"
    MINIMAL = "minimal"


class DBEvidenceSelector:
    """Select the most informative DB representation within budget."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Conservative approximation until a tokenizer is integrated.
        return (len(text) + 2) // 3

    @staticmethod
    def _content(evidence: Evidence, tier: DBEvidenceTier) -> str:
        """The record's text at `tier`, falling back to the next richer rendering when one is missing."""
        if tier == DBEvidenceTier.DETAILED:
            return evidence.content

        if tier == DBEvidenceTier.COMPACT:
            return evidence.compact_content or evidence.content

        return (
                evidence.minimal_content
                or evidence.compact_content
                or evidence.content
        )

    @classmethod
    def _render(
            cls,
            evidence: list[Evidence],
            tier: DBEvidenceTier,
    ) -> list[Evidence]:
        return [
            item.model_copy(
                update={"content": cls._content(item, tier)}
            )
            for item in evidence
        ]

    @classmethod
    def _tokens(cls, evidence: list[Evidence]) -> int:
        # Includes the source header context_resolver wraps around each record in the prompt.
        return sum(
            cls.estimate_tokens(
                f"--- SOURCE ({item.title}) ---\n{item.content}\n"
            )
            for item in evidence
        )

    @classmethod
    def select(
            cls,
            evidence: list[Evidence],
            profile: DBEvidenceProfile,
    ) -> list[Evidence]:
        """`evidence` rendered at the richest eligible tier; ValueError when no tier fits the budget."""
        if not evidence:
            return []

        count = len(evidence)

        # A record threshold is a preference; a token threshold
        # can also qualify a larger set for a richer tier.
        candidates = (
            (DBEvidenceTier.DETAILED, profile.detailed),
            (DBEvidenceTier.COMPACT, profile.compact),
            (DBEvidenceTier.MINIMAL, profile.minimal),
        )

        for tier, settings in candidates:
            rendered = cls._render(evidence, tier)
            tokens = cls._tokens(rendered)

            if tier == DBEvidenceTier.MINIMAL:
                eligible = tokens <= settings.max_tokens
            else:
                eligible = (
                        count <= settings.max_records
                        or tokens <= settings.max_tokens
                )

                # Never exceed the overall DB evidence budget.
                eligible = (
                        eligible
                        and tokens <= profile.minimal.max_tokens
                )

            if eligible:
                logger.info(
                    "db_evidence_selected",
                    profile=profile.name,
                    tier=tier.value,
                    records=count,
                    estimated_tokens=tokens,
                )
                return rendered

        raise ValueError(
            f"DB evidence exceeds the configured budget: "
            f"{profile.name}, records={count}"
        )