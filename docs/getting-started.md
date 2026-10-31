# Getting started

> **Audience:** Developers setting up a machine.

The only requirement is **Docker**. Python, uv, databases and models all run in containers.

- [Prerequisites](#prerequisites)
- [1. Configure](#1-configure)
- [2. Start the stack](#2-start-the-stack)
- [3. Load data](#3-load-data)
- [CPU-only machines](#cpu-only-machines)
- [Day-to-day development](#day-to-day-development)
- [Stopping](#stopping)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Need | Why |
| --- | --- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS, Linux) or Docker Engine + Compose v2 | Runs everything |
| One LLM API key (Gemini by default; OpenAI also supported) | Planning and answering questions. Embeddings and reranking run locally |
| Recommended: an NVIDIA GPU with the [container toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) | GPU embedding service. Without one, use the [CPU profile](#cpu-only-machines) |
| ~30 GB free disk | Images (torch/CUDA are large), model weights, data volumes |

## 1. Configure

```sh
git clone https://github.com/b4sleal/GoldenGuide.git
cd GoldenGuide
cp .env.dev.example .env
```

`.env` is the development file. Staging and production use `.env.staging` and `.env.prod`, created from
`.env.staging.example` and `.env.prod.example` ([environments](environments.md)).

`.env.dev.example` already contains working local defaults for every service, the development identity
provider and the integration tests. The only value you must add is an LLM key:

```env
MODEL_PROVIDER__GEMINI__API_KEY=your-key
```

`.env` is git-ignored. Never commit it, and change the default passwords on any machine reachable by
others.

**Windows only.** Docker Desktop runs in WSL 2, which by default may use most of the machine's CPU
and RAM. Apply the example budget (4 CPUs, 8 GB RAM, no swap) once:

```powershell
Copy-Item wslconfig.example "$env:USERPROFILE\.wslconfig"   # or merge it into an existing .wslconfig
wsl --shutdown                                               # then restart Docker Desktop
```

The file applies to every WSL distribution, not just GoldenGuide, so adjust it to your machine.

## 2. Start the stack

```sh
docker compose up -d --build --remove-orphans
```

`.env` tells Compose which files and profiles to use (`COMPOSE_FILE`, `COMPOSE_PROFILES`; defaults
`all-dev,embedding-gpu`). `all-dev` starts everything except the public tunnel, Keycloak and the embedding service; the second profile
picks the embedding service. Without an NVIDIA GPU, see [CPU-only machines](#cpu-only-machines).
The first start builds images and downloads dependencies and models, which takes a while. Later
starts reuse them.

| URL | What |
| --- | --- |
| http://localhost:8080 | GoldenGuide (frontend; proxies `/api` to the backend) |
| http://localhost:8082 | Backend API directly |
| http://localhost:8080/docs | Interactive API docs (admins) |
| http://localhost:3000 | Grafana: logs and traces |
| http://localhost:16686 | Jaeger: traces |
| http://keycloak.localhost:8081 | Keycloak: development identity provider (only with the `auth` profile) |
| http://localhost:9001 | MinIO console |
| http://localhost:6333/dashboard | Qdrant dashboard |

All ports bind to `127.0.0.1` only.

## 3. Load data

A fresh stack has no data, so chat has nothing to answer from yet. Loading data is an **admin
operation**. With the defaults (`AUTH_MODE=disabled`, `LOCAL_ADMIN=true`) requests from this
machine are treated as admin, so no sign-in is needed:

1. Open http://localhost:8080/docs.
2. Run, in order: collect sources (`/admin/sources/...`), then sync indexes (`/admin/indexing/...`).
   Each returns a job; poll `/admin/jobs/{run_id}` until it finishes. The full order and options
   are in [ingestion](ingestion.md#running-ingestion).

Local admin never applies to requests through the public tunnel, and the backend refuses to start
with it in production ([security](security.md#local-admin-without-sign-in)).

**To test real sign-in** instead, set `AUTH_MODE=oidc`, add `auth` to `COMPOSE_PROFILES` in `.env`, run
`docker compose up -d --remove-orphans` (the backend waits for Keycloak to be ready) and sign in at
http://localhost:8080/api/v1/auth/login as the development realm's user (`KC_TEST_ADMIN_USERNAME` /
`KC_TEST_ADMIN_PASSWORD` in `.env`).

`scripts/nightly_ingestion.py` runs the whole sequence with a service key, which is how scheduled
refreshes work ([nightly ingestion](nightly-ingestion.md)).

## CPU-only machines

Point the backend at the CPU service in `.env`, then pick the CPU profile:

```env
LOCAL_EMBEDDING_SERVICE__HOST=local-embedding-cpu
LOCAL_EMBEDDING_SERVICE__PORT=8002
EMBEDDING_RUNTIME=cpu
COMPOSE_PROFILES=all-dev,embedding-cpu
```

```sh
docker compose up -d --build --remove-orphans
```

The CPU service loads only the dense MiniLM embedding model and a MiniLM cross-encoder. ColBERT and SPLADE are
GPU-only (`configs/catalogs/providers/ml_local.yml`), and the default retrieval profile (`deep_cloud`) uses both.
CPU-only operation with the default profile has **not been verified**, and answers will differ. If the
embedding service runs on another machine, leave out the embedding
profile and set `LOCAL_EMBEDDING_SERVICE__HOST` to that machine ([docker](docker.md#separate-machines)).

## Day-to-day development

| Change | What to do |
| --- | --- |
| Backend Python (`src/backend`) | Nothing: Uvicorn reloads automatically |
| Frontend (`src/frontend`) | Refresh the browser (files are mounted read-only into Nginx) |
| Embedding service code or `configs/` | `docker compose restart local-embedding-gpu` (or `-cpu`), or `restart backend` for backend config |
| Python dependencies (`pyproject.toml` / `uv.lock`) | Restart the backend; it syncs its venv on start. Embedding dependencies need `up -d --build` |
| `Dockerfile` or `docker/start-python-service.sh` | `up -d --build` |
| Database schema | Add an Alembic migration; the `provision` job applies it on the next start |

Run commands inside the containers instead of installing tools locally, e.g.
`docker compose exec backend pytest tests/backend/unit -q` ([testing](testing.md)).

## Editor setup: type hints from Docker

The Python packages live in the dev stack's Docker volume, so you do not need a local `.venv`. Point
the IDE at the interpreter inside the `workspace` container, which uses the same venv as the backend:

`workspace` is part of the `all-dev` profile, so it starts and stops with the dev stack. To run it alone:

```sh
docker compose up -d workspace
# One time, or after uv.lock changes. Skip if the dev stack has already started once.
docker compose exec workspace uv sync --locked --no-default-groups --group dev-backend
```

**IntelliJ IDEA Ultimate / PyCharm Professional** (stays in your normal window, so Git works as usual):
Settings → Project → Python Interpreter → Add Interpreter → **On Docker Compose**. Configuration files:
`docker-compose.yml` and `docker-compose.dev.yml`. Service: `workspace`. Interpreter path:
`/home/app/.cache/venv/bin/python`. Do not choose the "uv" or "Virtualenv" types: they run on Windows
and fail with a working-directory error for `/app`. If the IDE reports that a local Python 3 SDK is
needed to render docstrings, add any local Python as a second SDK; it is only used for that.

**VS Code:** `.devcontainer/devcontainer.json` is optional. "Reopen in Container" starts `workspace` and
runs the sync. A JetBrains dev container opens a second window with the IDE running inside Docker,
where Git is not available, so prefer the Docker Compose interpreter above.

The IDE interpreter configuration is machine-level, so each developer sets it up once.

## Stopping

```sh
docker compose --profile "*" stop   # every profile, including ones started by hand
```

Never use `down -v` unless you intend to delete the databases, vectors and object storage. Disk
cleanup that keeps your data is in [docker](docker.md#disk-usage-and-cleanup).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| A service keeps restarting | `docker compose logs <service>`; it may be hitting its memory limit (`*_MEMORY_LIMIT` in `.env`) |
| Embedding service unhealthy for minutes | First start downloads models (GPU: ~2 GB); the healthcheck allows 120 s and retries |
| `503 Authentication is not configured` | Sign-in is off and the request isn't local: check `LOCAL_ADMIN=true`, or use `AUTH_MODE=oidc` |
| Sign-in fails | `OIDC_CLIENT_ID`, roles and `OIDC_CLIENT_SECRET` must match the realm (the defaults in `.env.dev.example` do) |
| Answers say information couldn't be checked | A store or provider failed; find the `trace_id` in Grafana |
| Integration tests skipped | The `*_TEST_*` variables are missing from `.env` ([testing](testing.md)) |
