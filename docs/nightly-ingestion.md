# Scheduled ingestion

> **Audience:** Operators.

The backend accepts source collection and indexing requests with **202 Accepted** and a response like:

```json
{"run_id": 42, "job_name": "website_crawl:wlu", "status": "queued", "status_url": "/api/v1/admin/jobs/42"}
```

Poll `status_url` using the same bearer key. `queued` and `running` are unfinished;
`success`, `partial_success`, `failed` and `cancelled` are final. Only `success` passes
the scheduled workflow. Polling needs the `jobs:read` scope. Internal exception details
stay in server job records and logs, rather than HTTP responses.

## Enable the nightly workflow

1. Make sure the backend is running. All nine source and indexing endpoints answer `202 Accepted` and a status
   URL, so any caller must poll that URL instead of treating the first response as completion.
2. Generate the nightly caller's key in the running backend container:
   `docker compose exec backend python -m backend.core.startup.service_key github_actions_nightly`.
   Store the printed hash in the backend's
   `SERVICE_CLIENT__GITHUB_ACTIONS_NIGHTLY__KEY_HASH` secret and restart the backend.
   Keep the plain key only with the caller.
3. In GitHub repository Actions secrets, set `GOLDENGUIDE_NIGHTLY_KEY` to the plain key.
   Its configured scopes are `sources:collect`, `indexing:sync`, and `jobs:read`.
4. Set Actions repository variable `GOLDENGUIDE_BASE_URL` to your public HTTPS origin,
   for example `https://askgoldenguide.ca` (no `/api` suffix).
5. Set `GOLDENGUIDE_REGISTRATION_TERMS` to the space-separated six-digit LORIS term
   codes you intend to refresh. Empty explicitly skips registration and prints that fact.
   Maintain this list when registration periods change; the workflow does not infer terms.
6. Once reviewed and published on the default branch, run **Nightly ingestion** manually
   in Actions and inspect its statuses before relying on the daily schedule.

The workflow runs at **05:00 America/Toronto**, including daylight-saving adjustments.
GitHub schedules can be delayed and require the workflow on the default branch; they are
not an exact-time delivery guarantee. See [GitHub schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Configure GitHub Actions failure notifications in your account: the workflow sends no separate email, Slack
message or Grafana alert.

## Pipeline and execution limits

The workflow sequentially discovers/imports the current Academic Calendar, then each of
`wlu`, `students_wlu`, and `scholars_wlu`, exports/imports configured LORIS terms, and syncs
courses, course terms and pages into the vector index. Each stage waits for the preceding
run to succeed. Discovery uses `fresh` to find new URLs even on an empty installation;
imports and indexing use `update` to process changed data. This revisits source URLs
daily; crawl requests use concurrency 4 and retain the existing robots/rate-limit policy.
The client supports `--sites`, `--terms`, and `--crawl-mode` for deliberate local runs.

`scripts/nightly_ingestion.py` uses Python's standard library and reads the bearer key
from stdin. It refuses HTTP origins, redirects and unexpected status URLs. It prints
run IDs and outcomes, never keys or raw response bodies. A POST is sent once: after a
timeout or connection loss, inspect server records before submitting another request.

Polling stops after two hours per job or five hours for the pipeline. The Actions job
has a 330-minute limit. A polling timeout, cancelled workflow or unreachable site does
**not** cancel a server job. A new run of the same job name is rejected with 409 while
the previous run is queued/running, including across backend instances. GitHub also
serializes manual/scheduled runs with `cancel-in-progress: false`.

## Lifecycle and recovery

Execution uses tasks in the API process, not a durable queue. The task launcher sends
heartbeats throughout planning, crawling, importing and auditing. Shutdown cancels and
awaits tasks, records interrupted runs as failed, and marks unfinished batches failed
for retry. A hard crash is recovered by the periodic zombie sweep after heartbeat expiry
(default five minutes, checked every two minutes). The sweep includes abandoned queued
runs and only fails unfinished batches. It does not automatically replay work.

Timing comes from `system.jobs` in YAML. Submission exclusion uses a short
[PostgreSQL transaction advisory lock](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS)
inside the persistence adapter; no schema migration is required.

The host and its dependencies must be running. Restarts interrupt work; a future durable
worker would be a separate adapter. Heartbeat recovery is not a fencing mechanism for
arbitrarily paused workers or network partitions. Different job names can still operate
on related data; the nightly schedule orders its stages, but there is no global ingestion lock.

The existing crawler treats an unavailable robots.txt policy as a disallowed host. That
failure is logged, but currently can produce a successful run with no fetched pages.
The workflow checks recorded job outcomes; it does not independently prove source coverage.
