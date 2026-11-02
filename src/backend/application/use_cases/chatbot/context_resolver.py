"""Build the answer model's context: structured evidence first, then semantic (vector) search results.

Semantic search runs through the profile's fallback chain (search -> rerank -> whole pages). Every
reference gets one citation entry; LORIS sections share that entry while keeping distinct evidence
blocks. Links inside the evidence are renumbered into request-wide @@n@@ placeholders that the link
resolver restores in the streamed answer.
"""
import re
from urllib.parse import urlparse

import structlog

from backend.application.services.chatbot.reranking import (
    drop_duplicate_chunks,
    rerank_hits,
)
from backend.application.services.chatbot.retrieval_router import (
    RetrievalProfileRouter,
)
from backend.application.services.chatbot.whole_documents import (
    expand_to_whole_documents,
)
from backend.application.use_cases.chatbot.link_resolver import COURSE_CODE_PATTERN
from backend.application.use_cases.chatbot.source_references import (
    is_registration_source,
    registration_source,
    source_snippet,
)
from backend.application.use_cases.ingestion.upload_doc import document_blob_key
from backend.domain.entities.ingestion_types import KnowledgeSourceType
from backend.domain.entities.retrieval import Evidence
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.providers.embedding import (
    EmbeddingOrchestrator,
)
from backend.domain.ports.providers.reranker import RerankerOrchestrator
from backend.domain.ports.providers.sparse import (
    SparseVectorizerOrchestrator,
)
from backend.domain.ports.providers.vector_store.port import (
    VectorStore,
)
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.ai_behavior import (
    RAGSource,
    ResolvedRAGContext,
)
from backend.domain.settings.chat import SourceSnippetSettings
from backend.domain.settings.institution import InstitutionProfile
from backend.domain.settings.profiles import RetrievalProfile

logger = structlog.get_logger(__name__)

# A stored Markdown link to a source-local placeholder: `[label](@@n@@)`, tolerating escaped parentheses.
PLACEHOLDER_LINK = re.compile(r"\[([^\]\n]*)\]\s*\\?\(\s*@@(\d+)@@\s*\\?\)")
COURSE_CODE = re.compile(COURSE_CODE_PATTERN, re.IGNORECASE)


class RAGContextResolver:
    """Combine factual and semantic evidence into one source format."""

    def __init__(
            self,
            router: RetrievalProfileRouter,
            embedding_orchestrator: EmbeddingOrchestrator,
            sparse_vectorizer_orchestrator: SparseVectorizerOrchestrator,
            vector_store: VectorStore,
            blob_storage: BlobStorage,
            reranker_orchestrator: RerankerOrchestrator,
            school_db: SchoolDB,
            institution: InstitutionProfile,
            snippet_settings: SourceSnippetSettings,
    ):
        self.router = router
        self.embedding = embedding_orchestrator
        self.sparse = sparse_vectorizer_orchestrator
        self.vector_store = vector_store
        self.blob_storage = blob_storage
        self.reranker = reranker_orchestrator
        self.school_db = school_db
        self.registration_url = str(institution.registration_url)
        self.snippet_max_chars = snippet_settings.max_chars

    @classmethod
    def _resolve_evidence_placeholders(
            cls,
            content: str,
            external_links: list[str],
            course_links: dict[str, str],
    ) -> str:
        """Replace stored `[label](@@n@@)` links with their plain label, so the model's context holds no
        Markdown links to imitate. A course code's link is kept in `course_links` (code -> URL); the
        answer links every mention of that code afterwards (ChatbotLinkResolver)."""

        def replace(match: re.Match) -> str:
            label, offset = match.group(1), int(match.group(2)) - 1
            code = label.strip().upper()
            if COURSE_CODE.fullmatch(code) and 0 <= offset < len(external_links):
                url = cls._valid_url(external_links[offset])
                if url:
                    course_links.setdefault(code, url)
            return label

        return PLACEHOLDER_LINK.sub(replace, content)

    @staticmethod
    def _valid_url(value: str | None) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None

        parsed = urlparse(value.strip())

        if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
        ):
            return None

        return value.strip()

    @classmethod
    def _source_url(cls, payload: dict) -> str | None:
        """Read source URLs from known ingestion payload locations."""
        extra = payload.get("extra") or {}

        candidates = (
            extra.get("url"),
            extra.get("calendar_url"),
            payload.get("calendar_url"),
            payload.get("parent_url"),
            payload.get("url"),
        )

        for candidate in candidates:
            valid = cls._valid_url(candidate)
            if valid:
                return valid

        return None

    @staticmethod
    def _clean_unresolved_links(content: str) -> str:
        """Leave plain labels when the local link table is absent: `[CP164](@@3@@)` becomes `CP164`.

        Never turn @@1@@ into a guessed URL, and never leave `[CP164]`, which the model copies as is.
        """
        return PLACEHOLDER_LINK.sub(lambda match: match.group(1), content or "")

    async def search_candidates(self, question: str, profile: RetrievalProfile) -> list[RetrievedChunk]:
        """First-stage semantic search: embed the question for each vector the collection has, then fuse."""
        retrieval = profile.vector_retrieval
        collection = profile.vector_collection

        logger.info(
            "retrieval_attempt_started",
            profile=profile.name,
            collection=collection.key,
        )

        dense_vector = None
        sparse_vector = None
        multi_vector = None

        if collection.vectors.dense is not None:
            dense_vector = await self.embedding.embed_query(
                text=question,
                profile=collection.vectors.dense.embedding,
            )

        if collection.vectors.sparse is not None:
            sparse_vector = await self.sparse.vectorize_query(
                text=question,
                profile=collection.vectors.sparse.vectorizer,
            )

        if collection.vectors.multi_vector is not None:
            multi_vector = await self.embedding.embed_query(
                text=question,
                profile=collection.vectors.multi_vector.embedding,
            )

        hits = await self.vector_store.search(
            name=collection.key,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            multivector=multi_vector,
            limit=retrieval.search.top_k,
        )

        logger.info(
            "semantic_hits_received",
            count=len(hits),
        )
        return hits

    async def resolve_context(
            self,
            question: str,
            top_k: int = 8,
            factual: list[Evidence] | None = None,
            semantic_enabled: bool = True,
    ) -> ResolvedRAGContext:
        primary_profile = self.router.route_question(question)

        if not semantic_enabled:
            context_text, sources, course_links = await self._prepare_context(
                hits=[],
                max_chunks=0,
                factual=factual,
            )

            return ResolvedRAGContext(
                context_text=context_text,
                sources=sources,
                course_links=course_links,
                llm_profile=primary_profile.llm,
                profile_name=primary_profile.name,
            )

        execution_chain = [
            primary_profile,
            *primary_profile.fallback,
        ]
        last_error = None

        for profile in execution_chain:
            try:
                # Duplicates go first so they neither cost reranking time nor take answer slots.
                hits = drop_duplicate_chunks(await self.search_candidates(question, profile))

                # Search finds candidates; the cross-encoder decides which actually answer the question.
                hits = await rerank_hits(question, hits, profile.vector_retrieval.rerank, self.reranker)

                # Few, small enough pages left: send them whole so lists (deadlines, steps) arrive complete.
                hits = await expand_to_whole_documents(hits, top_k, profile.vector_retrieval.whole_documents, self.school_db)

                context_text, sources, course_links = await self._prepare_context(
                    hits=hits,
                    max_chunks=top_k,
                    factual=factual,
                )

                return ResolvedRAGContext(
                    context_text=context_text,
                    sources=sources,
                    course_links=course_links,
                    llm_profile=profile.llm,
                    profile_name=profile.name,
                )

            except Exception as exc:
                logger.warning(
                    "retrieval_strategy_failed",
                    failed_profile=profile.name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                last_error = exc

        logger.error(
            "all_retrieval_strategies_failed",
            initial_strategy=primary_profile.name,
        )

        if factual:
            context_text, sources, course_links = await self._prepare_context(
                hits=[],
                max_chunks=0,
                factual=factual,
            )

            return ResolvedRAGContext(
                context_text=context_text,
                sources=sources,
                course_links=course_links,
                llm_profile=primary_profile.llm,
                profile_name=primary_profile.name,
                semantic_failed=True,
            )

        raise RuntimeError(
            "All retrieval strategies in the fallback chain failed."
        ) from last_error

    async def _prepare_context(
            self,
            hits,
            max_chunks: int,
            factual: list[Evidence] | None = None,
    ) -> tuple[str, list[RAGSource], dict[str, str]]:
        blocks: list[str] = []
        sources: list[RAGSource] = []
        course_links: dict[str, str] = {}

        seen_chunks: set[str] = set()
        source_indices: dict[tuple[str, str], int] = {}

        def add(
                source_id: str,
                title: str,
                url: str | None,
                content: str,
                source_type: str,
        ):
            if not content or not content.strip():
                return

            chunk_key = f"{source_id}:{content}"

            if chunk_key in seen_chunks:
                return

            seen_chunks.add(chunk_key)

            source = RAGSource(
                title=title, url=self._valid_url(url), source_type=source_type,
                snippet=source_snippet(content, self.snippet_max_chars),
            )
            registration = is_registration_source(source, self.registration_url)
            # Keep each record's content/title and chunk identity, but share the registration
            # citation before generation. The stream and recorder therefore use the same IDs.
            reference_id = ("registration", self.registration_url) if registration else ("record", source_id)
            if reference_id not in source_indices:
                sources.append(registration_source(self.registration_url) if registration else source)
                source_indices[reference_id] = len(sources)

            number = source_indices[reference_id]

            blocks.append(
                f"--- SOURCE {number} ({title}) ---\n{content}"
            )

        # Structured records are authoritative.
        for item in factual or []:
            if item.source_id.startswith("course_term:"):
                source_type = "course_terms"
            elif item.source_id.startswith("course:"):
                source_type = "courses"
            else:
                source_type = "factual"

            add(
                source_id=item.source_id,
                title=item.title,
                url=item.url,
                content=self._resolve_evidence_placeholders(
                    content=item.content,
                    external_links=item.external_links,
                    course_links=course_links,
                ),
                source_type=source_type,
            )

        # Semantic results supplement structured evidence.
        for hit in hits[:max_chunks]:
            payload = hit.payload or {}
            extra = payload.get("extra") or {}

            source_type = (
                    payload.get("source_type")
                    or "vector"
            )
            source_id = str(
                payload.get("source_id", "")
            )

            title = (
                    extra.get("title")
                    or payload.get("title")
                    or "Untitled source"
            )

            content = (
                    payload.get("text")
                    or hit.content
                    or ""
            )

            content = self._clean_unresolved_links(content)
            url = self._source_url(payload)

            if source_type == KnowledgeSourceType.DOC:
                # Payload fields are top-level for documents (DocumentVectorPayload); older points used "extra".
                filename = payload.get("filename") or extra.get("filename", "")

                if filename and source_id:
                    url = await self.blob_storage.get_link(document_blob_key(source_id, filename))

            add(
                source_id=f"vector:{source_id}",
                title=title,
                url=url,
                content=content,
                source_type=source_type,
            )

        return "\n\n".join(blocks), sources, course_links
