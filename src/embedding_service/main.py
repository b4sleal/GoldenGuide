"""Local embedding service: dense embeddings and sparse vectors on CPU or GPU, behind an API key."""
import onnxruntime as ort
import structlog
from fastapi import Depends, FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

import goldenguide_common.contracts.embedding_api as Schemas
from embedding_service.api.auth import build_api_key_verifier
from embedding_service.api.limits import build_text_limit
from embedding_service.api.memory import MemoryObservationMiddleware
from embedding_service.core.registry import build_model_registry
from embedding_service.models.embedding.service import LocalEmbeddingService
from embedding_service.models.reranker.service import LocalRerankerService
from embedding_service.models.vectorizer.service import LocalSparseVectorizerService
from goldenguide_common.config.env_reader import EnvSecretReader
from goldenguide_common.config.loader import ConfigLoader
from goldenguide_common.logging.bootstrap import configure_observability

# Step 1: logging and tracing before anything else, so model loading is logged in the
# standard format. The service name keeps these logs/spans separate from the API's.
reader = EnvSecretReader()
configure_observability(reader, default_service_name="goldenguide-embedding")

logger = structlog.get_logger()

app = FastAPI(
    title="GoldenGuide Local Embedding Service",
    version="1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Step 2: continue the caller's trace. The backend's HTTPX client sends a `traceparent` header,
# so each embedding request shows up as a child of the chat request that triggered it.
FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")

# Step 3: load configuration and only the models for this runtime (cpu or gpu).
config = ConfigLoader(reader).load_local_embedding_config()
app.add_middleware(
    MemoryObservationMiddleware,
    info_interval_seconds=config.settings.memory_log_interval_seconds,
)
runtime = config.settings.runtime
if runtime == "gpu":
    ort.preload_dlls()

verify_api_key = build_api_key_verifier(config.settings.api_key.get_secret_value())
enforce_text_limit = build_text_limit(config.settings.max_texts_per_request)

embeddings = build_model_registry({ # Get only CPU or GPU models
    name: settings
    for name, settings in config.local_embedding.items()
    if runtime == settings.runtime
})
vectorizers = build_model_registry({ # Get only CPU or GPU models
    name: settings
    for name, settings in config.local_sparse_vectorizer.items()
    if runtime == settings.runtime
})
rerankers = build_model_registry({ # Get only CPU or GPU models
    name: settings
    for name, settings in config.local_reranker.items()
    if runtime == settings.runtime
})
embedding_service = LocalEmbeddingService(embeddings)
vectorizer_service = LocalSparseVectorizerService(vectorizers)
reranker_service = LocalRerankerService(rerankers)
logger.info("embedding_service.ready", runtime=runtime, models=sorted([*embeddings, *vectorizers, *rerankers]))

# Logging convention for the endpoints below: one line per successful call, with the model and the
# number of texts. Timing lives on the request's trace span. Failures are logged and traced by
# FastAPI/uvicorn and the OTel instrumentation, so they are not repeated here.


@app.get("/health")
async def health():
    """Report service readiness and the model keys loaded in this runtime."""

    return {
        "status": "ok",
        "service": "embedding",
        "models": list(embeddings.keys()) + list(vectorizers.keys()) + list(rerankers.keys()),
    }


@app.post("/embed/query", response_model=Schemas.EmbedResponse, dependencies=[Depends(verify_api_key)])
async def embed_query(request: Schemas.EmbedQueryRequest):
    """Generate one dense or multi-vector representation for a query."""

    vector = await embedding_service.embed_query(request.model_key, request.text)
    logger.info("embedding.query_embedded", model=request.model_key, texts=1)
    return Schemas.EmbedResponse(vectors=[vector])


@app.post("/embed/documents", response_model=Schemas.EmbedResponse, dependencies=[Depends(verify_api_key)])
async def embed_documents(request: Schemas.EmbedDocumentsRequest):
    """Generate dense or multi-vector representations for documents."""

    enforce_text_limit(request.texts)
    vectors = await embedding_service.embed_documents(request.model_key, request.texts)
    logger.info("embedding.documents_embedded", model=request.model_key, texts=len(request.texts))
    return Schemas.EmbedResponse(vectors=vectors)


@app.post("/sparse/query", response_model=Schemas.SparseQueryResponse, dependencies=[Depends(verify_api_key)])
async def sparse_query(request: Schemas.SparseQueryRequest):
    """Generate one sparse vector for a query."""

    result = await vectorizer_service.vectorize_query(model_key=request.model_key, text=request.text)
    logger.info("embedding.query_vectorized", model=request.model_key, texts=1)
    return Schemas.SparseQueryResponse(vector=result)


@app.post("/sparse/documents", response_model=Schemas.SparseDocumentsResponse, dependencies=[Depends(verify_api_key)])
async def sparse_documents(request: Schemas.SparseDocumentsRequest):
    """Generate sparse vectors for documents in input order."""

    enforce_text_limit(request.texts)
    result = await vectorizer_service.vectorize_documents(model_key=request.model_key, texts=request.texts)
    logger.info("embedding.documents_vectorized", model=request.model_key, texts=len(request.texts))
    return Schemas.SparseDocumentsResponse(vectors=result)


@app.post("/rerank", response_model=Schemas.RerankResponse, dependencies=[Depends(verify_api_key)])
async def rerank(request: Schemas.RerankRequest):
    """Score each document for the supplied query in input order."""

    scores = await reranker_service.rerank(request.model_key, request.query, request.documents)
    logger.info("embedding.documents_reranked", model=request.model_key, texts=len(request.documents))
    return Schemas.RerankResponse(scores=scores)
