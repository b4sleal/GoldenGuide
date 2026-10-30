# Testing

- [Kinds of tests](#kinds-of-tests)
- [Running tests with only Docker](#running-tests-with-only-docker)
- [Running tests on the host (optional)](#running-tests-on-the-host-optional)
- [Integration test services](#integration-test-services)
- [Static checks](#static-checks)
- [Retrieval evaluation](#retrieval-evaluation)
- [Continuous integration](#continuous-integration)
- [Adding a vector store adapter](#adding-a-vector-store-adapter)

---

## Kinds of tests

| Kind | Location | Needs | Use it for |
| --- | --- | --- | --- |
| **Unit** | `tests/backend/unit/{api,application,automation,core,domain,infra,shared}` | Nothing: no network, no models | Logic GoldenGuide owns: entity extraction, term resolution, plan validation, compilers, evidence budgeting, streaming, auth decisions, use cases with fake ports |
| **Integration** | `tests/backend/integration/infra/` | Real PostgreSQL, Redis, Qdrant | Behaviour that depends on the external system: SQL filters and upserts, migrations, transactions, Redis TTL/atomicity, Qdrant search and filters, adapter contracts |
| **Evaluation** | `tests/eval/` | The running stack and its data | Retrieval quality before and after a change (not pass/fail) |

Rule of thumb: if replacing the real dependency with a fake could let the test pass while
production breaks, it needs an integration test. Unit tests mock **our ports** (domain Protocols),
never SQLAlchemy sessions or SDK clients. Tests mirror the `src/backend` layout and assert behaviour,
not private methods, log messages, SDK call sequences or SQL formatting.

`pytest-asyncio` runs `async def` tests (`asyncio_mode = "auto"`); `pytest-cov` measures coverage.

## Running tests with only Docker

The development image already contains pytest, Ruff and Pyright (the `dev-backend` dependency
group), and `docker compose run` starts a throwaway container, so no local Python or uv is needed
and a running stack is left alone.

```sh
DC="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

# Unit tests
$DC run --rm --no-deps backend start-python-service.sh dev-backend pytest tests/backend/unit -q
```

Integration tests need the stores running (`$DC --profile database --profile state_store
--profile vector-store up -d`). Inside a container the stores are reached by service name, not
`localhost`, so the test URLs are built from the same `.env` credentials:

```sh
$DC run --rm --no-deps backend sh -c '
  export GOLDENGUIDE_TEST_DATABASE_URL="postgresql+asyncpg://$DB__POSTGRES__USER:$DB__POSTGRES__PASSWORD@postgres:5432/goldenguide_test"
  export REDIS_TEST_URL="redis://:$CACHE__REDIS__PASSWORD@redis:6379/15"
  export QDRANT_TEST_URL=http://qdrant:6333 QDRANT_TEST_API_KEY="$VECTOR_STORE__QDRANT__API_KEY"
  export GOLDENGUIDE_REQUIRE_TEST_SERVICES=1
  start-python-service.sh dev-backend pytest tests/backend/integration -q'
```

If the dev backend is already running, `$DC exec backend pytest tests/backend/unit -q` is faster.

## Running tests on the host (optional)

With [uv](https://docs.astral.sh/uv/) installed, tests can run directly on the host against the
Compose services on `localhost`. pytest loads `.env` (`tests/conftest.py`), whose `*_TEST_*` values
already point at those services; real environment variables override it.

```sh
uv sync
uv run pytest tests/backend/unit
uv run pytest tests/backend/integration
```

## Integration test services

| Variable | Default in `.env.dev.example` | Isolation |
| --- | --- | --- |
| `GOLDENGUIDE_TEST_DATABASE_URL` | `postgresql+asyncpg://admin:admin@localhost:5432/goldenguide_test` | Separate database, created by the dev `db-bootstrap`. The name must end in `_test` or the suite refuses to run |
| `REDIS_TEST_URL` | `redis://:admin@localhost:6379/15` | Redis DB 15 and a random key prefix per test |
| `QDRANT_TEST_URL`, `QDRANT_TEST_API_KEY` | `http://localhost:6333`, `qdranttestapikey` | A uniquely named collection per test, deleted afterwards |

Development data is never touched. Cleanup:

- Course persistence tests roll back their transaction; job tests use a unique schema that is
  dropped afterwards; migration tests downgrade and always upgrade back to head; Qdrant
  collections are deleted in `finally`.
- Failing tests still clean up. A **killed** run (crash, second Ctrl+C) can leave stray
  `jobs_review_*` schemas or `gg_contract_test_*` collections; they use unique names and don't
  affect later runs.
- The migration suite includes destructive round trips: never point it at real data, and don't run
  two suites against the same test database at once.

A missing `*_TEST_*` variable **skips** its tests locally (a skip is not a pass). Set
`GOLDENGUIDE_REQUIRE_TEST_SERVICES=1`, as CI does, to make a missing service fail instead. A
configured but unreachable service always fails.

## Static checks

```sh
$DC run --rm --no-deps backend start-python-service.sh dev-backend ruff check src tests
$DC run --rm --no-deps backend start-python-service.sh dev-backend pyright
```

`import-linter` is installed, but layer contracts aren't configured yet.

## Retrieval evaluation

`tests/eval/retrieval_eval.py` runs every case in `retrieval_cases.yml` through the same search the
chat uses and reports where the expected page first appears among the context chunks, before and
after reranking. "Hit" means the page is in the chunks the answer model actually receives. It needs
the running stack and its data:

```sh
docker compose exec -w /app backend python -m tests.eval.retrieval_eval
docker compose exec -w /app backend python -m tests.eval.retrieval_eval --show "What are the important dates"
docker compose exec -w /app backend python -m tests.eval.retrieval_eval --ask "What are the important dates"
```

| Mode | Prints |
| --- | --- |
| (none) | One line per case: rank and coverage before and after rerank, search and rerank time; then totals and the overall run time |
| `--show QUESTION` | Search and rerank time, then the chunks the answer model would receive (title and opening text) |
| `--ask QUESTION` | The full chat pipeline, as the browser gets it: the streamed answer with citation numbers, any tables, the source list, time to first text and total time. This one calls the LLMs |

Run it before and after any retrieval change; it measures quality and its numbers move with the data.

## Continuous integration

`.github/workflows/tests.yml` runs `pytest tests` (every unit and integration test, including future
ones) on pull requests, pushes to `master`/`main`, merge queues and manual dispatch. It starts
disposable PostgreSQL, Redis and Qdrant service containers and needs no application secrets, paid
LLM credentials or access to the deployed site. Dependencies come from `uv.lock`.

To make passing tests mandatory, let the `All tests` job run once, then add a branch ruleset in
GitHub (**Settings > Rules > Rulesets**): target the default branch, require a pull request and the
`All tests` status check, and require branches to be up to date (or use a merge queue). Workflow
YAML alone cannot enforce these settings.

The evaluation script and the nightly ingestion workflow are deliberately outside this gate: they
depend on live data and services.

## Adding a vector store adapter

The shared requirements are in `tests/backend/integration/infra/persistence/vectors/test_contracts.py`:
idempotent replacement, every vector modality, relevance ordering, limits, thresholds, source
filters, provenance, and safely scoped deletion and stale cleanup. They call `AppVectorStore`
backed by the real adapter rather than mocking storage.

When adding a provider to `VectorStoreProvider`, add its fixture and its `VECTOR_STORE_FIXTURES`
entry in the neighbouring `conftest.py`. The fixture yields `(AppVectorStore(adapter),
collection_name)` for a fresh collection supporting dense, sparse and multi-vector operations, and
cleans up afterwards. The enum parametrizes the suite, so a provider without a fixture fails instead
of escaping coverage. Add its disposable CI service if it needs one.
