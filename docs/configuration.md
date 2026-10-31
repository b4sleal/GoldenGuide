# Configuration

> **Audience:** Developers and operators.

Two kinds of settings, kept apart on purpose:

| Kind | Where | Examples |
| --- | --- | --- |
| **Behaviour** (versioned with the code) | `configs/` YAML | Providers, models, retrieval profiles, chunking, prompts, scraping targets, lexicon |
| **Deployment** (per machine) | Environment / `.env` | Hosts, ports, credentials, API keys, resource limits, bind addresses |

- [Layered YAML](#layered-yaml)
- [What lives where](#what-lives-where)
- [Catalogs, profiles and active selections](#catalogs-profiles-and-active-selections)
- [Retrieval profiles](#retrieval-profiles)
- [Runtime settings](#runtime-settings)
- [Secrets and environment variables](#secrets-and-environment-variables)

---

## Layered YAML

`ConfigLoader` (`src/goldenguide_common/config/loader.py`) merges, in order (later wins):

1. `configs/base/*.yml`: defaults for every environment
2. `configs/catalogs/<group>/*.yml`: what exists (providers, profiles) and what is active
3. `configs/environments/<APP_ENV>.yml`: `development`, `staging` or `production` overrides

The merged tree is validated into typed Pydantic settings (`src/backend/domain/settings/`) at
startup. Invalid configuration stops the process at boot, not at the first request. References
such as `${catalog.providers.llm.gemini_fast}` (OmegaConf interpolation) let profiles reuse
provider definitions instead of copying them.

## What lives where

| File | Contents |
| --- | --- |
| `base/system_config.yml` | Logging, OIDC client behaviour (timeouts, clock skew, local dev hosts), job heartbeat and zombie-sweep timing, service clients and their scopes |
| `base/ai_behavior.yml` | Router LLM and answer LLM prompts and defaults (admins can override at runtime) |
| `base/embedding_service.yml` | Settings for the embedding service process |
| `catalogs/providers/infra.yml` | PostgreSQL, Redis, Qdrant, MinIO connection definitions (secrets referenced, not stored) |
| `catalogs/providers/ml_cloud.yml` | Cloud LLMs (Gemini, OpenAI) and cloud embeddings |
| `catalogs/providers/ml_local.yml` | Local models: MiniLM, ColBERT, SPLADE, cross-encoder rerankers, each for CPU or GPU |
| `catalogs/providers/text_splitter.yml` | Chunk sizes and overlaps (small 300 … large 1,500 characters) |
| `catalogs/profiles/vector_collection.yml` | Collection layouts: `dense`, `sparse`, `multi`, `multi_sparse` (version, chunking, enrichment, vector types) |
| `catalogs/profiles/vector_retrieval.yml` | Search strategies: candidate count, rerank depth and score gaps, whole-page budget |
| `catalogs/profiles/db_evidence.yml` | Token budgets for structured evidence per detail tier |
| `catalogs/profiles/retrieval_profile.yml` | Named bundles of the above plus an LLM and optional fallback profiles |
| `catalogs/active/infra.yml` | Which store definitions are in use for each role (`db.app`, `cache.app`, ...) |
| `catalogs/router/router.yml` | Query router settings, e.g. the entity lookup cache TTL (one day) |
| `catalogs/scraping/websites.yml` | Websites to crawl: seeds, allowed domains, rules |
| `catalogs/text_enrichment/retrieval_text.yml` | Templates that add context to each chunk before embedding |
| `catalogs/text_enrichment/wlu_lexicon.yml` | WLU faculties, departments, subjects and their aliases |
| `catalogs/institution/institution.yml` | The institution served: code (`WLU`), timezone, LORIS registration URL |

## Catalogs, profiles and active selections

The pattern is the same everywhere:

```
catalog.providers.<kind>.<name>   a concrete thing that can be used (a model, a database)
catalog.profiles.<kind>.<name>    a reusable combination of providers
catalog.active.<role>             which one this deployment uses
```

The composition root resolves each `provider:` value through a registry to an adapter. Adding an
implementation is an adapter plus a registry entry; selecting it is a YAML change. Use cases never
name a vendor.

## Retrieval profiles

`catalogs/profiles/retrieval_profile.yml`:

| Profile | Vector collection | Search | Semantic search falls back to |
| --- | --- | --- | --- |
| `fast_local` | `dense` | Dense only | None |
| `balanced_local` | `sparse` | Hybrid (dense + sparse) | `fast_local` |
| `fast_cloud` | `sparse` | Hybrid, balanced depth | `balanced_local` |
| `balanced_cloud` | `multi` | ColBERT, deep | `fast_cloud` |
| `deep_cloud` (current default) | `multi_sparse` | Hybrid + ColBERT, rerank, whole pages | `balanced_cloud` |

Each profile combines a vector collection layout, a retrieval strategy, a database evidence budget
and an answer LLM. If semantic search fails on the chosen profile, the profile's fallback profiles
are tried in order (only the profile's own fallback list, not the fallbacks of those). Every profile
uses the same answer model (`gemini_deep`); the LLM settings also accept fallback models, but none
are configured.
Every question uses `deep_cloud` today (`RetrievalProfileRouter`); routing easy questions to cheaper
profiles is the intended next step and needs no change outside that router.

Changing a collection's chunking, enrichment or vectors requires bumping its `version` and
re-indexing; provisioning refuses to run against a collection whose stored version doesn't match.

## Runtime settings

Some behaviour can change without a deploy: `GET` / `PATCH /api/v1/admin/settings/` reads and
updates runtime defaults (prompts, model choices) stored in PostgreSQL, versioned, and cached in
Redis. YAML provides the defaults; saved settings override them.

## Secrets and environment variables

**Secrets are never written in YAML.** A value like `${secrets:DB__POSTGRES__PASSWORD}` is looked
up through the `SecretReader` port when configuration loads and is never logged. Today that reader
is `EnvSecretReader` (environment variables plus `.env`); a cloud deployment can swap in AWS Secrets
Manager or Parameter Store without touching callers.

One env file per environment, all git-ignored; only the `.example` templates are tracked:

| Environment | File | Template |
| --- | --- | --- |
| Development | `.env` (also read by the tests and `uv run`) | `.env.dev.example`: working local defaults |
| Staging | `.env.staging` | `.env.staging.example`: credentials left blank |
| Production | `.env.prod` | `.env.prod.example`: credentials left blank |

Staging and production run with `docker compose --env-file <file>`; the file sets `ENV_FILE` so the
containers read the same values ([environments](environments.md#environment-files)). In a real
production deployment the values come from a secret manager or the CI/CD pipeline as environment
variables, not from a file on disk.

The templates list the variables each environment needs; the rest have
defaults in `docker-compose.yml` or the code. The main groups:

| Group | Variables |
| --- | --- |
| App | `APP_ENV`, `SITE_ORIGIN`, `ALLOWED_HOSTS`, `AUTH_MODE`, `LOCAL_ADMIN`, `FRAME_ANCESTORS`, `CHAT_RATE_LIMIT`, `CHAT_RATE_WINDOW_SECONDS` |
| Stores | `DB__POSTGRES__*`, `CACHE__REDIS__*`, `VECTOR_STORE__QDRANT__*`, `BLOB_STORAGE__MINIO__*` |
| Models | `MODEL_PROVIDER__GEMINI__API_KEY`, `MODEL_PROVIDER__OPENAI__API_KEY`, `LOCAL_EMBEDDING_SERVICE__*`, `EMBEDDING_RUNTIME` |
| Auth | `OIDC_*`, `KC_TEST_ADMIN_*` (development realm user), `KC_ADMIN_*` (first admin of the hosted realm), `KC_BOOTSTRAP_ADMIN_*` (Keycloak console), `KC_HOSTNAME`, `SERVICE_CLIENT__<NAME>__KEY_HASH` |
| Networking | `BACKEND_ORIGIN`, `*_PORT`, `*_BIND_ADDRESS`, `TRUSTED_PROXY_CIDRS`, `APP_NETWORK_SUBNET`, `MACHINE_NAME`, `TS_AUTHKEY`, `TUNNEL_TOKEN` (one per environment) |
| Compose | `ENV_FILE` and `COMPOSE_PROJECT_NAME` (set by the staging and production files); `COMPOSE_FILE`, `COMPOSE_PROFILES`, `COMPOSE_PATH_SEPARATOR` (set by every environment file) |
| Observability | `OTEL_EXPORTER_OTLP_ENDPOINT`, `LOKI_PUSH_URL`, `CONTAINER_LOG_FORMAT`, `GRAFANA_ADMIN_*` |
| Limits | `*_CPUS`, `*_MEMORY_LIMIT`, `EMBEDDING_THREADS`, `UV_CONCURRENT_*` |
| Tests | `GOLDENGUIDE_TEST_DATABASE_URL`, `REDIS_TEST_URL`, `QDRANT_TEST_*`, `GOLDENGUIDE_REQUIRE_TEST_SERVICES` |
