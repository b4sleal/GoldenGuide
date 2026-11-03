# HTTP API

> **Audience:** Developers and anyone calling the API.

All application routes are under `/api/v1`. Admins can browse the interactive OpenAPI docs at
`/docs` (admin-only). Access rules are explained in [security](security.md).

## Endpoints

| Method & path | Access | Purpose |
| --- | --- | --- |
| `POST /chat/stream` | Public, rate-limited | Ask a question; NDJSON event stream (below). Stores the turn; returns `X-Conversation-Id`. Send it back as `conversation_id` to continue |
| `GET /chat/conversations` | This browser, rate-limited | This browser's conversations, most recently active first (`limit`, `offset`) |
| `GET /chat/conversations/{id}/messages` | This browser, rate-limited | Ordered messages: role, content, status, optional `answer_content` and public `sources`. No internal diagnostics |
| `DELETE /chat/conversations/{id}` | This browser, same-origin | Permanently delete a conversation with its messages and feedback |
| `PUT /chat/messages/{id}/feedback` | This browser, same-origin | Thumbs up/down with optional `reason` and `comment` on an answer; replaces an earlier rating |

"This browser" means the anonymous `gg_client` cookie (HttpOnly, random, stored only as a hash).
A conversation or message belonging to another browser returns `404`, never `403`.
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
The `indexing` endpoints also take `payload_only=true` (with `fresh` or `retry`; `422` with `update`):
it rewrites the payload of existing vectors without embedding, e.g. after adding a payload field.
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
characters, plus an optional `conversation_id` to continue a conversation) and returns
`application/x-ndjson`: one JSON object per line. The stored conversation's ID comes back in the
`X-Conversation-Id` response header.

```sh
curl -N -H 'Content-Type: application/json' -d '{"query":"When is the last day to drop a fall course?"}' \
  http://localhost:8080/api/v1/chat/stream
```

| Event | Meaning |
| --- | --- |
| `{"type": "status", "stage": "...", "source": "..."}` | Progress before the text (not terminal). `stage`: `understanding`, `searching` (with `source`: `courses`, `course_terms`, `wlu_pages`, `vector`), `writing`. The client maps codes to wording |
| `{"type": "text", "text": "..."}` | Answer text, in order |
| `{"type": "citation", ...}` | Inline citation marker pointing at a source |
| `{"type": "table", ...}` | A table built from database records (e.g. LORIS sections), at the position the answer placed it |
| `{"type": "sources", "sources": [...]}` | The source list for the answer (title, URL, type, preview), sent once, before the first `text`, so inline citations can show their sources while the text streams |
| `{"type": "saved", "message_id": 42}` | The complete answer was stored under this ID; use it for `PUT /chat/messages/{id}/feedback`. Sent just before `ok`; omitted if history could not be saved (the answer is still complete) |
| `{"type": "ok"}` | **Terminal**: the answer is complete |
| `{"type": "error", "error": {...}}` | **Terminal**: generation failed after the stream started; same envelope as HTTP errors |

An answer is complete **only** if the last event is `ok`. A stream that ends without `ok` or
`error` (connection dropped, proxy timeout) must be treated as incomplete. This exists because once
a streaming response has started, its HTTP status can no longer change.

Errors before the stream starts (validation, rate limit `429`, another browser's conversation
`404`) are ordinary HTTP errors. The first event (`status: understanding`) is sent immediately, so
retrieval, settings and LLM failures arrive as an `error` event.
