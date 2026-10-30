"""Choose the retrieval profile (vector collection, reranking, LLM, evidence budget) for a question.

Every question currently uses one profile. Each profile still carries its own fallback chain
(see RAGContextResolver), so a failing provider degrades to the next profile rather than failing.
"""
import structlog

from backend.domain.settings.ai_behavior import RetrievalProfileCatalog
from backend.domain.settings.profiles import RetrievalProfile

logger = structlog.get_logger()

# Must name a profile in configs/catalogs/profiles/retrieval_profile.yml.
DEFAULT_PROFILE = "deep_cloud"


class RetrievalProfileRouter:

    def __init__(self, retrieval_profiles: RetrievalProfileCatalog):
        self.retrieval_profiles = retrieval_profiles

    def route_question(self, query: str) -> RetrievalProfile:
        """The profile to answer `query` with (the default profile until routing by question exists)."""
        profile = self.retrieval_profiles.get(DEFAULT_PROFILE)

        logger.info(
            "retrieval_profile_selected",
            profile=DEFAULT_PROFILE,
        )

        return profile
