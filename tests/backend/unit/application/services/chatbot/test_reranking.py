"""rerank_hits: reorders search hits by cross-encoder score and keeps top_k; failures keep search order."""
import json

import httpx

from backend.application.services.chatbot.reranking import drop_duplicate_chunks, rerank_hits
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from backend.domain.settings.profiles import RerankerProfile, RetrievalRerank
from backend.infra.ml.rerank.local import LocalReranker
from backend.infra.ml.rerank.standard_orchestrator import StandardRerankerOrchestrator
from goldenguide_common.contracts.embedding_models import CrossEncoderRerankerSettings, LocalRerankerProvider

SETTINGS = CrossEncoderRerankerSettings(
    name="cross_encoder", provider=LocalRerankerProvider.CROSS_ENCODER, model_name="m",
    max_length=512, batch_size=8, device="cpu", runtime="cpu",
)
PROFILE = RerankerProfile(primary=SETTINGS)


def hit(text, score):
    return RetrievedChunk(content=text, score=score, payload={"text": text})


# Search order puts the observance calendar first; the cross-encoder knows the deadlines page answers it.
HITS = [hit("Diwali Nov 6, Remembrance Day Nov 11", 0.9), hit("Jul 27: Last day to register", 0.8),
        hit("Lab safety training", 0.7)]


class FakeReranker:
    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.calls = scores, error, []

    async def rerank(self, query, documents, profile):
        self.calls.append((query, documents, profile))
        if self.error:
            raise self.error
        return self.scores


async def test_hits_are_reordered_by_reranker_score_and_cut_to_top_k():
    reranker = FakeReranker(scores=[0.1, 5.2, -3.0])

    ranked = await rerank_hits("important dates", HITS, RetrievalRerank(top_k=2, reranker=PROFILE), reranker)

    assert [h.content for h in ranked] == ["Jul 27: Last day to register", "Diwali Nov 6, Remembrance Day Nov 11"]
    assert [h.score for h in ranked] == [5.2, 0.1]   # The answer sees the reranker's score, not the fused one.
    assert reranker.calls == [("important dates", [h.content for h in HITS], PROFILE)]


async def test_without_rerank_settings_hits_are_untouched():
    reranker = FakeReranker()

    assert await rerank_hits("q", HITS, None, reranker) == HITS
    assert reranker.calls == []


async def test_reranker_failure_keeps_search_order():
    ranked = await rerank_hits("q", HITS, RetrievalRerank(top_k=2, reranker=PROFILE), FakeReranker(error=httpx.ConnectError("down")))

    assert ranked == HITS[:2]


async def test_wrong_number_of_scores_keeps_search_order():
    ranked = await rerank_hits("q", HITS, RetrievalRerank(top_k=2, reranker=PROFILE), FakeReranker(scores=[9.0]))

    assert ranked == HITS[:2]   # One score for three hits cannot be paired: no hit is dropped or mis-scored.


async def test_local_reranker_sends_groups_and_keeps_document_order():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={"scores": [float(len(d)) for d in payload["documents"]]})

    service = type("Service", (), {
        "host": "embed", "port": 8001, "max_texts_per_request": 2, "request_timeout_seconds": 5.0,
        "api_key": type("Key", (), {"get_secret_value": lambda self: "k"})(),
    })()
    reranker = LocalReranker(SETTINGS, service)
    reranker.client = httpx.AsyncClient(base_url="http://embed:8001", transport=httpx.MockTransport(handler))

    scores = await StandardRerankerOrchestrator({"cross_encoder": reranker}).rerank("q", ["a", "bb", "ccc"], PROFILE)

    assert scores == [1.0, 2.0, 3.0]
    assert [r["documents"] for r in requests] == [["a", "bb"], ["ccc"]]
    assert {r["model_key"] for r in requests} == {"cross_encoder"}


def test_duplicate_chunk_texts_keep_only_the_first():
    copy = hit("Jul 27: Last day to register", 0.5)  # Same text stored under a second record.

    assert drop_duplicate_chunks([HITS[1], copy, HITS[0]]) == [HITS[1], HITS[0]]


async def test_hits_far_below_the_best_are_dropped():
    reranker = FakeReranker(scores=[2.0, 7.0, 5.0])  # Best 7.0; a gap of 2.5 keeps scores >= 4.5.

    ranked = await rerank_hits("q", HITS, RetrievalRerank(top_k=3, reranker=PROFILE, max_score_gap=2.5), reranker)

    assert [h.score for h in ranked] == [7.0, 5.0]
