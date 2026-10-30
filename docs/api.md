# HTTP API

All application routes are under `/api/v1`. Admins can browse the interactive OpenAPI docs at
`/docs` (admin-only). Access rules are explained in [security](security.md).

## Endpoints

| Method & path | Access | Purpose |
| --- | --- | --- |
| `POST /chat/stream` | Public, rate-limited | Ask a question; NDJSON event stream (below) |
| `POST /chat/feedback` | Public | Planned (`501`) |
| `GET /auth/login` | Public | Start OIDC sign-in (Keycloak today, Microsoft Entra planned) |
| `GET /auth/callback` | Public | OIDC redirect target; creates the session |
| `GET /auth/me` | Signed in | Current principal and roles |
| `POST /auth/logout` | Signed in, same-origin | End the session |
| `GET`, `PATCH /admin/settings/` | `settings:write` | Runtime defaults: prompts, router and answer models, retrieval behaviour. Versioned |
| `GET /admin/documents/` | `documents:write` | List uploaded documents |
| `POST /admin/documents/upload` | `documents:write` | Upload a document (stored in MinIO, embedded) |
| `DELETE /admin/documents/{id}` | `documents:write` | Planned (`501`) |
| `POST /admin/sources/academic-calendar/discover` | `sources:collect` | Crawl the Academic Calendar for a year (defaults to current) |
| `POST /admin/sources/academic-calendar/import` | `sources:collect` | Parse discovered calendar pages into courses and programs |
| `POST /admin/sources/websites/discover` | `sources:collect` | Crawl one WLU website (`wlu`, `students_wlu`, `scholars_wlu`) |
| `POST /admin/sources/websites/import` | `sources:collect` | Parse that site's crawled pages into `wlu_pages` |
| `POST /admin/sources/registration/export` | `sources:collect` | Download one LORIS term's offerings |
| `POST /admin/sources/registration/import` | `sources:collect` | Load that extract into course terms |
| `POST /admin/indexing/courses/sync` | `indexing:sync` | Embed courses into the vector store |
| `POST /admin/indexing/course-terms/sync` | `indexing:sync` | Embed course terms |
| `POST /admin/indexing/pages/sync` | `indexing:sync` | Embed WLU pages |
| `GET /admin/jobs/{run_id}` | `jobs:read` | Status, batches and outcome of a job run |

Admins hold every scope; service clients hold only theirs. State-changing admin requests from a
browser must be same-origin.

**Jobs.** Every `sources` and `indexing` endpoint returns `202 Accepted` immediately:

```json
{"run_id": 42, "job_name": "website_crawl:wlu", "status": "queued", "status_url": "/api/v1/admin/jobs/42"}
```

Poll `status_url` until the status is final (`success`, `partial_success`, `failed`, `cancelled`).
Most accept a `mode` of `fresh`, `update` or `retry` ([ingestion](ingestion.md#jobs-modes-and-retries)).
A second submission of the same job while one is running is `409`.

## Health

| Path | Meaning |
| --- | --- |
| `/health/live` | Liveness: the process answers HTTP. Deliberately does not check data stores, so an outage in a dependency doesn't restart a healthy API. |
| `/health` | Same check under the older path (used by the Compose healthcheck). |

A dependency-aware readiness endpoint is planned. The embedding service has its own `/health`.

## Errors

Every error uses one envelope and carries correlation ids, which also appear in the logs and traces:

```json
{"error": {"code": "...", "message": "...", "request_id": "...", "trace_id": "..."}}
```

Internal details and stack traces are never returned.

## Chat stream contract

`POST /api/v1/chat/stream` takes `{"query": "What are the prerequisites for CP264?"}` (1–4,000
characters) and returns `application/x-ndjson`: one JSON object per line.

```sh
curl -N -H 'Content-Type: application/json' -d '{"query":"When is the last day to drop a fall course?"}' \
  http://localhost:8080/api/v1/chat/stream
```

| Event | Meaning |
| --- | --- |
| `{"type": "text", "text": "..."}` | Answer text, in order |
| `{"type": "citation", ...}` | Inline citation marker pointing at a source |
| `{"type": "table", ...}` | A table built from database records (e.g. LORIS sections), at the position the answer placed it |
| `{"type": "sources", "sources": [...]}` | The source list for the answer, always the last content event |
| `{"type": "ok"}` | **Terminal**: the answer is complete |
| `{"type": "error", "error": {...}}` | **Terminal**: generation failed after the stream started; same envelope as HTTP errors |

An answer is complete **only** if the last event is `ok`. A stream that ends without `ok` or
`error` (connection dropped, proxy timeout) must be treated as incomplete. This exists because once
a streaming response has started, its HTTP status can no longer change.

Errors before the stream starts (validation, rate limit `429`) are ordinary HTTP errors.
