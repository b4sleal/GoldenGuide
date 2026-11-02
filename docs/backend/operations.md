# Operations

> **Audience:** whoever keeps GoldenGuide running, and developers who are on call for it.

What to do day to day: check that it is healthy, deploy a change, take and restore backups, rotate a secret,
add an admin, and fix the problems that have actually come up. How the environments differ is in
[environments](environments.md); how to run a single environment is in [docker](docker.md).

- [Commands](#commands)
- [Everyday checks](#everyday-checks)
- [Deploy a change](#deploy-a-change)
- [Roll back](#roll-back)
- [Backups and restore](#backups-and-restore)
- [Rotate a secret](#rotate-a-secret)
- [Add an admin](#add-an-admin)
- [Troubleshooting](#troubleshooting)
- [Accounts and ownership](#accounts-and-ownership)
- [Known limitations](#known-limitations)

---

## Commands

`.env.prod` chooses the Compose files and profiles (`COMPOSE_FILE`, `COMPOSE_PROFILES`), so every production command
starts with `docker compose --env-file .env.prod`. On a dedicated host that saves the file as `.env`, drop the flag.

On a machine without an NVIDIA GPU, set `COMPOSE_PROFILES=all,embedding-cpu` in the env file. For staging, swap in
`.env.staging` ([environments](environments.md#environment-files)).

## Everyday checks

| Check | How |
| --- | --- |
| Are all containers up and healthy? | `docker compose --env-file .env.prod ps`. The backend, frontend, Postgres, Redis, Qdrant, MinIO and embedding service should say `healthy` |
| Does the API answer? | `curl http://localhost:8082/health/live` on the host (the default `BACKEND_PORT`; use `localhost`, because `127.0.0.1` is not in `ALLOWED_HOSTS` and gets a `400`). It checks only that the process responds, not the data stores |
| Is the site reachable? | Open `https://askgoldenguide.ca`. A browser error from Cloudflare while the containers are healthy points at the tunnel (see [Troubleshooting](#troubleshooting)) |
| What went wrong? | `docker logs --tail 50 goldenguide-prod-backend-1` (add `-f` to follow). Every error response carries a `request_id` and `trace_id` that also appear in the logs |
| Logs and traces across containers | Grafana at `http://localhost:3000` on the host that runs the observability profile ([observability](observability.md)) |
| Did the nightly ingestion work? | The **Nightly ingestion** workflow in GitHub Actions, and `GET /api/v1/admin/jobs/{run_id}` ([nightly ingestion](nightly-ingestion.md)) |

## Deploy a change

1. Get the new code on the host (`git pull`).
2. Back up PostgreSQL first if the change includes a migration ([Backups](#backups-and-restore)).
3. Rebuild and restart only what changed:

   ```sh
   docker compose --env-file .env.prod up -d --build --remove-orphans backend
   ```

   The `provision` job runs first and applies any new migration; the backend starts after it succeeds. Use
   `--build frontend` for a UI change. Changing `.env.prod` needs no rebuild, only
   `docker compose --env-file .env.prod up -d backend` (a plain `restart` does not re-read the file).
4. Recreate the job worker too: it runs the same image, so a backend change is a worker change.

   ```sh
   docker compose --env-file .env.prod --profile worker up -d --no-build --no-deps worker
   ```

   On stop, the worker lets running jobs finish for up to 60 s
   (`system.jobs.worker.shutdown_graceful_timeout_seconds`), then records them as interrupted. Prefer
   deploying between jobs; an interrupted import is resubmitted with `mode=update`.
5. Check that the backend is `healthy`, the worker logs `worker.started`, and the site loads.

## Roll back

- **Code:** check out the previous commit and run the same `up -d --build backend`.
- **Database:** only the baseline migration exists today, so there is no earlier schema version to step back
  to. Treat a database rollback as a **restore from backup**. Once later migrations exist, each one has a
  `downgrade()`, and CI tests the full downgrade and upgrade round trip. Run
  `uv run alembic downgrade -1` from a developer machine against the production database, after a backup.

## Backups and restore

| Store | Holds | Back it up? | If it is lost |
| --- | --- | --- | --- |
| PostgreSQL | Courses, course terms, pages, uploaded-document records, runtime settings, job history | **Yes**: this is the authoritative data | Restore the backup |
| MinIO | Raw crawled HTML, LORIS extracts, **uploaded original files** | **Yes** for uploads, which cannot be re-fetched. Crawled sources can be collected again | Restore, or re-run collection |
| Keycloak data | Users and credentials in the hosted realm | **Yes** | Recreate the users (the first admin is re-seeded on an empty volume) |
| Qdrant | Vectors derived from PostgreSQL | Optional | Re-run indexing (`/admin/indexing/.../sync` with mode `fresh`) |
| Redis | Sessions, rate limits, caches | No | People sign in again |

**Back up PostgreSQL** (the user is `DB__POSTGRES__USER` from `.env.prod`):

```sh
docker exec goldenguide-prod-postgres-1 pg_dump -U <user> -d goldenguide -Fc -f /tmp/goldenguide.dump
docker cp goldenguide-prod-postgres-1:/tmp/goldenguide.dump ./goldenguide.dump
```

Use `docker cp` rather than redirecting the command's output: PowerShell would convert the binary dump to text.
Store the file somewhere other than the host. `pg_restore -l goldenguide.dump` lists what it contains.

**Restore.** Restore into a new, empty database first and compare row counts before replacing anything:
`pg_restore -U <user> -d <new_database> goldenguide.dump`. This exact restore has not been rehearsed on this
project: do a trial run before you rely on it.

**Copy data between environments or hosts.** This is how production received its initial data. Stop the store
first, so the files are consistent, then copy the volume:

```sh
docker compose <source-environment> stop postgres
docker volume create goldenguide-prod_pg_data
docker run --rm -v goldenguide_pg_data:/from:ro -v goldenguide-prod_pg_data:/to busybox sh -c "cp -a /from/. /to/"
```

PostgreSQL keeps its user and password inside the data directory, so the target environment's
`DB__POSTGRES__USER` and `DB__POSTGRES__PASSWORD` must be the same as the source's.

## Upgrade Procrastinate (the job queue)

`procrastinate` is pinned exactly in `pyproject.toml` because its database schema is versioned with
the package. Its schema is created by Alembic revision `0005`, which runs a frozen copy of the 3.10.0
`schema.sql` (`src/backend/infra/persistence/db/migrations/sql/`). To upgrade:

1. Read the release notes for every version between the current and the target one.
2. Bump the pin, then `uv lock`.
3. For each release that ships SQL migrations (`procrastinate schema --migrations-path` lists them;
   files are named `{version}_{nn}_{pre|post}_*.sql`), copy them into `migrations/sql/` and add one
   Alembic revision that runs them in order, the same way `0005` runs its script.
4. Deploy with downtime (simplest): stop the `worker` profile and the backend, run `provision`, start
   them again. Zero-downtime upgrades need each version's `pre` script, that release, then its `post`
   script, one version at a time (Procrastinate's migration guide).
5. Never edit `0005` or a shipped SQL copy: they are history.

## Rotate a secret

Change the value, then recreate every service that reads it (`docker compose --env-file .env.prod up -d <service>`).
Some secrets are stored in more than one place:

| Secret | Where it lives | How to rotate |
| --- | --- | --- |
| LLM API keys (`MODEL_PROVIDER__*`) | `.env.prod` | Replace, recreate `backend` |
| Cloudflare tunnel token (`TUNNEL_TOKEN`) | `.env.prod`, Cloudflare | Create a new token for the tunnel in the Cloudflare dashboard, replace, recreate `tunnel` |
| Nightly service key | Hash in `.env.prod`, plain key in the GitHub secret `GOLDENGUIDE_NIGHTLY_KEY` | Generate a new key with `python -m backend.core.startup.service_key github_actions_nightly`, put the old hash in `..._PREVIOUS_KEY_HASH` and the new one in `..._KEY_HASH`, recreate `backend`, update the GitHub secret, then clear the previous hash ([security](security.md#service-clients)) |
| OIDC client secret (`OIDC_CLIENT_SECRET`) | `.env.prod` **and** the Keycloak client | Change it on the client's Credentials tab in the Keycloak console, put the same value in `.env.prod`, recreate `backend`. The realm file is only read on first import |
| Keycloak console admin (`KC_BOOTSTRAP_ADMIN_*`) | Keycloak master realm | Change the password in the console; the env value only applies on first start |
| PostgreSQL password | Inside the database **and** `.env.prod` | `ALTER USER ... PASSWORD ...` in the database, update `.env.prod`, recreate `backend` and `provision` |
| Redis, MinIO, Qdrant, embedding keys | `.env.prod` (read at start) | Replace, recreate the store and the services that call it |

## Add an admin

Admins are users of the `goldenguide` realm in Keycloak with the `goldenguide-admin` role. Sign in to
`<KC_HOSTNAME>/admin/` with `KC_BOOTSTRAP_ADMIN_USERNAME` and `KC_BOOTSTRAP_ADMIN_PASSWORD`, switch to the
`goldenguide` realm, create the user, set a password, and add the role under Role mapping. Google sign-in and the
first seeded admin are described in [environments](environments.md#keycloak-for-staging-and-production).

## Troubleshooting

Every entry here has happened on this project.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `pull access denied for goldenguide-backend` | The image was never built on this host (or was removed); it is not published anywhere | Build it: `docker compose --env-file .env.prod build backend` |
| `Pool overlaps with other one on this address space` | Another environment's Docker network already uses the subnet | Give this environment its own `APP_NETWORK_SUBNET` in its env file |
| `required variable ... is missing a value` (for example `KC_ADMIN_PASSWORD`) | Compose was started without `--env-file .env.prod`, so it read the development `.env` | Add `--env-file .env.prod` |
| Backend restarts and logs `Missing OIDC settings: OIDC_DISCOVERY_URL, OIDC_CLIENT_ID` | `AUTH_MODE=oidc` with those values blank | Fill the `OIDC_*` values, or set `AUTH_MODE=disabled` (public chat only, admin routes return 503) |
| Backend shows `unhealthy` and the log shows `/health/live` answered `400` | The container's own healthcheck uses `Host: localhost`, which is not in `ALLOWED_HOSTS` | Add `localhost` to `ALLOWED_HOSTS` |
| Browser says `Invalid host header` | The hostname is not in `ALLOWED_HOSTS` | Add it and recreate the backend |
| `/api/v1/auth/login` sends the browser to `keycloak.localhost:8081` | The backend read Keycloak's address at startup and has not been recreated since the env file changed | `docker compose --env-file .env.prod up -d backend` |
| Keycloak page: "Restart login cookie not found" | The browser dropped or never sent Keycloak's cookies: a stale login page, a blocked-cookie setting, or an embedded browser | Start again from `/api/v1/auth/login` in a private window with extensions off. The log line is `LOGIN_ERROR ... cookie_not_found` |
| `job_zombies_failed` warning in the worker log (backend log with `in_process`) | A running job stopped sending heartbeats (its worker was killed or restarted mid-job), or a run stayed queued for 24 h | Nothing is wrong. Its unfinished batches can be re-run with mode `retry` |
| A job stays `queued` | No worker is running (`JOBS__EXECUTION=worker` needs the `worker` profile up), or workers are busy with other jobs | Start the worker; check its log for `worker.started`. Queued runs are failed after 24 h |
| `queue_stalled_job_retried` warning in the worker log | A worker died while holding a job; the periodic cleanup released it | Nothing to do: the job is not re-run (its run was failed by the sweep). Resubmit it if needed |
| `job_request_unreadable` error, run failed with `InvalidRequest` | The run's stored request could not be read (e.g. a run recorded by an incompatible version) | Resubmit the job from its endpoint |
| Embedding service restarts during a sync; the worker logs many `embedding_record_failed` `ConnectError` | The container was OOM-killed (SIGKILL leaves no traceback). Confirm with `docker events --since 1h --filter container=goldenguide-prod-local-embedding-gpu-1` (`oom`, then `die` exit 137); `OOMKilled` resets on restart | Its memory is bounded by `ml_local.yml` (SPLADE `max_batch_tokens`, `max_concurrent_inferences`): lower those rather than raising `EMBEDDING_GPU_MEMORY_LIMIT`. `embedding.memory_sample` log lines show its RSS per document request |
| Qdrant near 100% CPU during or after a sync, collection `yellow` | Its optimizer is building search indexes for new points; Qdrant has 1 CPU by default | Nothing is wrong: search stays correct while `yellow`, and it turns `green` when indexing catches up. If it stays `yellow` for hours, check that the `colbert` vector has `hnsw_config.m: 0` (`GET /collections/<name>`); collections created before 2026-11-02 built an HNSW graph over every ColBERT token vector. Fix in place: `PATCH /collections/<name>` with `{"vectors":{"colbert":{"hnsw_config":{"m":0}}}}`. If filtered requests (`points/count`, `points/scroll`) are slow, check the payload indexes exist (`payload_schema`) and run `provision` |
| Payload indexes or a new collection missing after a deploy | `provision` did not run: `up --no-deps backend` skips it | `docker compose --env-file .env.prod --profile provision run --rm provision`; it is idempotent |
| A tunnel hostname opens a Cloudflare error page | The tunnel has no route for that hostname, or points at a name that does not exist on this stack's network | In the Cloudflare dashboard, check the public hostname targets `http://frontend:8080` (site) or `http://keycloak:8081` (Keycloak) |

## Accounts and ownership

Whoever takes over needs access to these. Fill in the owner column.

| System | What it is used for | Owner |
| --- | --- | --- |
| Domain `askgoldenguide.ca` and Cloudflare (DNS, tunnels, Access) | Public hostnames, the prod and staging tunnels, access policies | _to fill in_ |
| GitHub repository | Code, CI, the nightly workflow. Secret `GOLDENGUIDE_NIGHTLY_KEY`; variables `GOLDENGUIDE_BASE_URL` and `GOLDENGUIDE_REGISTRATION_TERMS` | _to fill in_ |
| Tailscale | Private network between machines, if more than one host is used | _to fill in_ |
| LLM providers (Gemini, OpenAI) | Answering and query planning | _to fill in_ |
| Google Cloud (optional) | The OAuth client if Google sign-in is added to Keycloak | _to fill in_ |
| The host machine(s) | Where each environment runs | _to fill in_ |

## Known limitations

- **Keycloak runs in development mode** (built-in database). That suits a small team; a hardened setup (production
  mode, PostgreSQL, backups) or the institution's managed provider is the longer-term answer.
- **Staging does not enforce production's startup checks.** The HTTPS-origin, no-`LOCAL_ADMIN` and
  trace-exporter checks apply only when `APP_ENV=production`.
- **No alerting.** Nothing notifies anyone when the site is down or a nightly run fails, other than GitHub's own
  failure emails.
- **No automated backups.** The commands above are manual.
- **Jobs are not retried automatically.** A job interrupted by a worker restart is recorded as failed;
  resubmit it (imports are idempotent with `mode=update`).
- **CPU-only embedding is limited** (see [getting started](getting-started.md#cpu-only-machines)).
