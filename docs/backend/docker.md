# Running GoldenGuide with Docker Compose

> **Audience:** Developers and operators.

First-time setup is in [getting started](getting-started.md). This page covers how the Compose
stack is put together and how to run it in other shapes: separate machines and limited hardware.
Development, staging and production, env files, hostnames, tunnels and Keycloak are in
[environments](environments.md); running and troubleshooting them is in [operations](operations.md).

- [Compose files](#compose-files)
- [Profiles](#profiles)
- [Images](#images)
- [Development vs runtime](#development-vs-runtime)
- [Separate machines](#separate-machines)
- [Resource limits](#resource-limits)
- [Disk usage and cleanup](#disk-usage-and-cleanup)
- [Data and reproducibility](#data-and-reproducibility)

---

## Compose files

| File | Role |
| --- | --- |
| `docker-compose.yml` | Runtime stack: every service, profile, limit, healthcheck and network. Built images, no source mounts |
| `docker-compose.dev.yml` | Development overrides: source mounts, auto-reload, a shared dev venv, the `goldenguide_test` database |
| `docker-compose.prod.yml` | Production overrides: every credential required (`${VAR:?}`), no development fallbacks |

Each environment file chooses its Compose files and default profiles (`COMPOSE_FILE`,
`COMPOSE_PROFILES`), so the commands stay short. `.env` is development; staging and production pass
their own file with `--env-file`:

```sh
# Development
docker compose up -d --build --remove-orphans
# Production
docker compose --env-file .env.prod up -d --build --remove-orphans
# Staging: production overrides with staging's own environment file
docker compose --env-file .env.staging up -d --build --remove-orphans
# Validate without starting anything
docker compose config --quiet
# Stop, logs, one service
docker compose down
docker compose logs -f backend
docker compose up -d --build backend
```

Any `--profile` flag replaces `COMPOSE_PROFILES` instead of adding to it, so list every profile you
want (`--profile all-dev --profile auth --profile embedding-gpu`) or change the file.
`--remove-orphans` removes containers of this project whose service no longer exists, such as the
`*-run-<id>` containers an IDE's `docker compose run` leaves behind.

Each rebuild moves an image's tag to the new build and leaves the old one as an untagged `<none>`
image. After `--build`, remove them with `docker image prune -f`: it deletes only untagged images no
container uses, never tagged images, volumes or the build cache. Optional, it only frees disk.

## Profiles

Profiles decide **which** services run; the override files decide **how**.

| Profile | Services |
| --- | --- |
| `database` | PostgreSQL + one-shot `db-bootstrap` (creates the databases) |
| `vector-store` | Qdrant |
| `object-store` | MinIO |
| `state_store` | Redis (AOF persistence) |
| `embedding-gpu` / `embedding-cpu` | Embedding service on an NVIDIA GPU (port 8001) or CPU (port 8002) |
| `provision` | One-shot job: migrations, buckets, vector collections |
| `backend` | FastAPI API |
| `worker` | Job worker (`python -m backend.worker`, same image as the backend): runs queued crawls, imports and indexing when `JOBS__EXECUTION=worker`. Opt-in, not in `all`/`all-dev`: `--profile worker` (scale with `--scale worker=N`) |
| `frontend` | Nginx: UI and API reverse proxy; development also starts the internal Vite service |
| `auth` | Development Keycloak |
| `observability` | Loki, Alloy, Grafana, Jaeger, OpenTelemetry Collector |
| `log-shipper` | Alloy only, for machines that send logs to another machine's Loki |
| `tailnet` | Tailscale device (`<MACHINE_NAME>-docker`) forwarding this machine's services to other machines; opt-in, not in `all`/`all-dev` |
| `tunnel` | Cloudflare Tunnel (publishes the frontend at the public domain) |
| `services` | The shared services: PostgreSQL (+ `db-bootstrap`), Qdrant, MinIO, Redis, Keycloak. For a machine that hosts them for another machine's backend |
| `all` | Everything except the embedding services, including the tunnel |
| `all-dev` | Everything except the embedding services, the tunnel and Keycloak (add `auth` to `COMPOSE_PROFILES` to test sign-in), plus the IDE `workspace` |

Neither aggregate includes an embedding service: add `embedding-gpu` **or** `embedding-cpu`, or
neither when another machine runs it. `all-dev` selects services, it does not make them development
services: that comes from `docker-compose.dev.yml`.

## Images

One `Dockerfile` builds every Python image; the `DEPENDENCY_GROUP` build argument picks the
`pyproject.toml` group.

| Stage | Contents | Used by |
| --- | --- | --- |
| `python` | Python 3.14-slim, non-root `app` user (uid 10001), model cache paths | Base of everything |
| `toolchain` | + compilers, `libpq`, uv 0.10.11 (the version that wrote `uv.lock`) | Building |
| `development` | toolchain as `app`; dependencies sync at container start | Dev `backend`, `provision`, `workspace` |
| `builder` | Installs one dependency group and the project into `/venv` (`uv sync --locked`) | Building runtime images |
| `runtime` | Python + the finished `/venv` + `configs/`; no compilers, no uv | `goldenguide-backend`, `goldenguide-embedding-gpu`, `goldenguide-embedding-cpu` |

Dependencies are installed before source is copied, so code changes reuse the cached dependency
layer. The CPU group uses CPU-only PyTorch wheels; the GPU group uses CUDA builds. They are mutually
exclusive in one venv but separate containers can run side by side. The frontend is a separate
Nginx image (`docker/frontend/`) with no Python.

## Development vs runtime

| | Runtime (`docker-compose.yml`) | Development (`+ docker-compose.dev.yml`) |
| --- | --- | --- |
| Backend, provision | Runtime image, installed (non-editable) package | `development` image, repo bind-mounted at `/app`, Uvicorn `--reload` on `src/backend` |
| Python dependencies | Baked into the image | One `python_dev_env` volume holding the uv cache and the venv; `uv sync --locked` at start |
| Embedding services | Runtime image | Same runtime image with `src/` and `configs/` mounted over it (`PYTHONPATH=/app/src`) |
| Frontend | `frontend/` built in a Node stage, baked into the Nginx image | `frontend-vite` hot-reloads bind-mounted `frontend/`; Nginx proxies UI/HMR to Vite and API requests to the backend |
| Test database | Not created | `db-bootstrap` also creates `goldenguide_test` |

Embedding services are restarted manually so model loading stays explicit. Changes to the
`Dockerfile` or `docker/start-python-service.sh` need `--build`.

Development keeps the same public frontend URL (default http://localhost:8080); Vite's port 5173
is not published. Windows mounts use polling (`FRONTEND_DEV_POLLING=true`); native Linux mounts can
set it to `false`. `frontend_node_modules` holds Linux dependencies separately from host dependencies.
Restart `frontend-vite` after a frontend lockfile change to sync that volume. The dev proxy image
does not build production assets; the runtime image still does. See [frontend setup](../../frontend/README.md).

**IDE workspace.** `docker-compose.dev.yml` adds a `workspace` service to `all-dev` (the `development`
image, sleeping) that mounts the same `python_dev_env` volume as `backend` and `provision`. The IDE uses its
interpreter for type hints and test runs, so the venv and uv cache exist once and are shared. See
[editor setup](getting-started.md#editor-setup-type-hints-from-docker).

## Separate machines

Every profile can run on its own host. Point each host's `.env` at the others' endpoints. The
`--profile` flags below replace that host's `COMPOSE_PROFILES`; setting `COMPOSE_PROFILES` in the
host's `.env` instead (e.g. `database,vector-store,embedding-gpu,tailnet`) keeps the bare `up` command:

```sh
docker compose --profile vector-store up -d          # vector machine
docker compose --profile database up -d              # database machine
docker compose --profile embedding-gpu up -d --build # GPU machine
docker compose --profile backend up -d --build       # API machine
```

- The `backend` profile doesn't start stores or migrations. Set `DB__POSTGRES__HOST`,
  `VECTOR_STORE__QDRANT__HOST`, `BLOB_STORAGE__MINIO__HOST`, `CACHE__REDIS__HOST` and the embedding
  host/port to the real private endpoints, and run provisioning explicitly before starting a remote
  backend: `docker compose run --rm provision`.
- Set `BACKEND_ORIGIN` on the frontend host to the backend origin (scheme and port). Docker service
  names resolve only within one host's Compose networks; Compose doesn't create a cross-host network.
- Published ports bind to loopback by default, so a machine's own services stay at `localhost` and
  nothing is exposed to its network. Reach other machines over Tailscale (below), or set a bind
  address to a private interface and allow only the client hosts through the firewall.

### Over Tailscale

**Optional.** Docker alone runs the whole stack on one machine; this is only for spreading the work
over several machines (a GPU machine for embeddings, another for the data stores, another for the
API, ...). The machines join one private Tailscale network, and each runs only its own profiles.

**One env file per machine**, each a copy of `.env.dev.example` (or the staging/production example)
with its [Machines](../../.env.dev.example) section filled in:

```env
# .env.data-node: data stores, provisioning and embeddings
ENV_FILE=.env.data-node
MACHINE_NAME=data-node
COMPOSE_PROFILES=services,provision,embedding-gpu,log-shipper,tailnet
DATA_NODE_HOST=data-node-docker.tail1234.ts.net
APP_NODE_HOST=app-node-docker.tail1234.ts.net
TS_AUTHKEY=tskey-auth-...
LOKI_PUSH_URL="http://${APP_NODE_HOST}:3100/loki/api/v1/push"
OTEL_EXPORTER_OTLP_ENDPOINT="http://${APP_NODE_HOST}:4317"

# .env.app-node: backend, frontend and observability
ENV_FILE=.env.app-node
MACHINE_NAME=app-node
COMPOSE_PROFILES=backend,frontend,observability,tailnet
DATA_NODE_HOST=data-node-docker.tail1234.ts.net
DB__POSTGRES__HOST="${DATA_NODE_HOST}"
VECTOR_STORE__QDRANT__HOST="${DATA_NODE_HOST}"
BLOB_STORAGE__MINIO__HOST="${DATA_NODE_HOST}"
CACHE__REDIS__HOST="${DATA_NODE_HOST}"
LOCAL_EMBEDDING_SERVICE__HOST="${DATA_NODE_HOST}"
```

Start the machine with the data stores first, then the others:

```sh
docker compose --profile "*" down                                         # stop whatever ran before
docker compose --env-file .env.data-node up -d --build --remove-orphans   # on the data node
docker compose --env-file .env.app-node up -d --build --remove-orphans    # on the app node
```

- `ENV_FILE` must name the file itself: Compose reads `--env-file` for profiles and substitution,
  but containers read `ENV_FILE` (default `.env`). A backend failing with `Errno -2 Name or service
  not known` while connecting to `postgres` means it got the wrong file.
- `*_HOST` names are defined once and referenced as `"${DATA_NODE_HOST}"` (double quotes). Define them above
  the lines that use them. Adding a machine is one more line, e.g. `GPU_NODE_1_HOST=gpu-node-1-docker.tail1234.ts.net`.
- Every published port stays on `127.0.0.1`, so each machine keeps `localhost` access to its own services.
- `MACHINE_NAME` labels logs in Grafana (`{host="data-node"}`), so every machine's logs appear on the
  observability machine.
- Use a tagged auth key. Each device keeps its identity in the `tailscale_state` volume, so the key
  is only used the first time; deleting that volume or the device makes it join as a new device.

#### Adding a machine

Example: a second GPU machine for embeddings, `gpu-node-1`.

1. **Install Docker** on it and clone the repository. If its containers will call another machine
   (a backend, or anything sending logs to the observability machine), also install the
   [Tailscale client](https://tailscale.com/download) and sign in to the same tailnet. A machine that
   only serves others, like this one, doesn't need it.
2. **Create an auth key** in the Tailscale admin console (Settings > Keys): tagged, ideally single-use.
3. **Create its env file** from `.env.dev.example` (or the staging/production example) as
   `.env.gpu-node-1`, using the same credentials as the other machines:
   ```env
   ENV_FILE=.env.gpu-node-1
   MACHINE_NAME=gpu-node-1
   COMPOSE_PROFILES=embedding-gpu,log-shipper,tailnet
   TS_AUTHKEY=tskey-auth-...
   APP_NODE_HOST=app-node-docker.tail1234.ts.net
   LOKI_PUSH_URL="http://${APP_NODE_HOST}:3100/loki/api/v1/push"
   OTEL_EXPORTER_OTLP_ENDPOINT="http://${APP_NODE_HOST}:4317"
   ```
4. **Start it:** `docker compose --env-file .env.gpu-node-1 up -d --build --remove-orphans`. Its
   `tailscale` container joins as `gpu-node-1-docker`. Check with `tailscale status` on any machine
   with the client, or in the admin console under Machines.
5. **Point the callers at it.** In the env file of every machine that uses it, add the name and
   reference it, then restart that machine's affected services:
   ```env
   GPU_NODE_1_HOST=gpu-node-1-docker.tail1234.ts.net
   LOCAL_EMBEDDING_SERVICE__HOST="${GPU_NODE_1_HOST}"
   ```
6. **Verify** from a calling machine: `Test-NetConnection gpu-node-1-docker.tail1234.ts.net -Port 8001`
   (PowerShell) or `nc -zv gpu-node-1-docker.tail1234.ts.net 8001`, and look for `{host="gpu-node-1"}`
   in Grafana.

A setting points at one machine, so two embedding machines don't share the load: the backend uses the
one it is configured with. Spreading requests over several needs a load balancer or an orchestrator
([architecture](architecture.md#scaling)).

How it works:

- **Incoming:** the `tailscale` container is its own tailnet device, `<MACHINE_NAME>-docker`. It
  forwards the ports in [`deploy/tailscale/serve.json`](../../deploy/tailscale/serve.json) to services
  by name, so only devices on your tailnet can reach them, e.g. `data-node-docker.<tailnet>.ts.net:6333`.
  Nothing extra is published on the host, and a forwarded service that isn't running on that
  machine refuses the connection. Docker Desktop and Linux work the same way.
- **Clients** use the other machine's name, never an IP: `DB__POSTGRES__HOST=data-node-docker.<tailnet>.ts.net`,
  `LOKI_PUSH_URL=http://app-node-docker.<tailnet>.ts.net:3100/loki/api/v1/push`, and so on. Find the
  tailnet suffix with `tailscale status --json` (`MagicDNSSuffix`) or in the admin console.
- **Outgoing:** a machine whose containers call another machine (the backend; Alloy and traces
  sent to the observability machine) currently needs the Tailscale app on the host. Containers reach
  tailnet names through it. Machines that only serve, such as a database or embedding machine, don't.
- **Future development: Docker-only outgoing.** Not built yet. A gateway container (e.g. HAProxy sharing the `tailscale`
  container's network, resolving names through Tailscale's DNS at `100.100.100.100`) would let callers
  use `tailscale:5432` instead of a host app, so Docker would be the only install on every machine.
  It needs kernel-mode Tailscale (`NET_ADMIN`, `/dev/net/tun`) and ports that don't collide with
  the incoming forwards.
- Every forwarded port is open to the whole tailnet. Use tagged keys and Tailscale access rules
  if the tailnet holds anything besides your own machines.
- PostgreSQL and Redis connections are not TLS-encrypted today: keep them on a trusted private
  network or VPN. MinIO and Qdrant support TLS through their `SECURE`/`HTTPS` flags (the server or a
  reverse proxy must also serve TLS).
- Observability on another machine: see [observability](observability.md#multiple-machines).

## Resource limits

Every container has `cpus`, `mem_limit` and a matching `memswap_limit` (matching values disable
swap: a service over its RAM is OOM-killed and restarted instead of swapping). Defaults:

| Services | CPU / RAM |
| --- | --- |
| Small services | 0.5 / 512 MiB |
| Backend, provision, PostgreSQL, Keycloak | 1 / 1 GiB |
| Qdrant | 1 / 2 GiB |
| Job worker (`WORKER_CPUS` / `WORKER_MEMORY_LIMIT`) | 2 / 2 GiB: the worker process plus `system.jobs.worker.compute_processes` (2) parsing children; keep the two in step |
| Each embedding service | 2 / 4 GiB system RAM |

Change them with the `*_CPUS` / `*_MEMORY_LIMIT` variables. They are maximums, not reservations;
their sum can exceed the machine, so run only the profiles you need. New limits apply when
containers are recreated. Embedding BLAS threads (`EMBEDDING_THREADS`) and uv's download/install
concurrency (`UV_CONCURRENT_*`) are bounded too. Logs rotate at 10 MiB × 3 files.

Not covered by container limits:

- **Windows / WSL.** Docker Desktop, the WSL kernel and page cache share one WSL budget. Copy or merge
  `wslconfig.example` into `%UserProfile%\.wslconfig` (6 CPUs, 12 GB, no swap, gradual memory
  reclaim), then `wsl --shutdown` and restart Docker Desktop. On backends with direct CPU/RAM
  settings, use Docker Desktop's Settings > Resources.
- **Image builds.** `RUN` steps ignore service limits. Use a capped builder:

  ```sh
  docker buildx create --name goldenguide-limited --driver docker-container --driver-opt memory=4g,memory-swap=4g,cpu-quota=200000,cpu-period=100000,default-load=true --buildkitd-config docker/buildkitd.toml
  docker compose --parallel 1 build --builder goldenguide-limited
  docker compose up -d --no-build --remove-orphans
  ```

- **GPU memory.** GPU reservation grants access to the device; it doesn't cap VRAM. The embedding
  service bounds its own: SPLADE runs on the GPU with a token budget (`max_batch_tokens`,
  `max_concurrent_inferences` in `ml_local.yml`, ~1 GB peak at the defaults), so its system RAM
  stays near its startup level (~2-2.7 GB with all four models loaded, of the 4 GiB limit).
  Lower `max_batch_tokens` for a smaller GPU; Windows "shared GPU memory" is system RAM and is not
  relied on.
- **Disk I/O.** Compose can't promise a portable disk-I/O cap on Docker Desktop.

References: [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/),
[Buildx container driver](https://docs.docker.com/build/builders/drivers/docker-container/),
[WSL configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config).

## Disk usage and cleanup

### Capping Docker's disk

A repository can't limit host disk usage on its own: Docker Desktop keeps images, volumes and build
cache in one virtual disk, and only Docker Desktop's settings can cap it (Compose has no size limit
for local volumes). Set these once per machine:

| Setting | Where | Recommended |
| --- | --- | --- |
| **Disk usage limit** (hard cap for everything Docker stores) | Docker Desktop > Settings > Resources > Advanced | 30 GB is enough for one GoldenGuide stack with GPU embeddings (~13 GB images, ~2.5 GB models, data and caches). Use more if you keep large datasets or several stacks |
| **Build cache limit** | Docker Desktop > Settings > Docker Engine: merge [`docker/daemon.example.json`](../../docker/daemon.example.json) | Keeps at most 10 GB of build cache and rotates container logs (10 MB × 3) for every container, not only GoldenGuide's |
| **Shrink freed space automatically** | Merge [`wslconfig.example`](../../wslconfig.example) into `%UserProfile%\.wslconfig` | `sparseVhd=true` returns freed space to Windows for disks created afterwards |
| **Linux hosts** | Put `/var/lib/docker` on its own fixed-size partition or volume | The partition size is the cap |

The capped builder ([build limits](#resource-limits)) also garbage-collects its own cache above
10 GB (`docker/buildkitd.toml`). When the disk limit is reached, builds and writes fail rather than
filling the host, so keep the cleanup commands below in mind.

Large Python dependencies are stored once:

| Where | What | Notes |
| --- | --- | --- |
| Runtime images | Each service's venv, built in | Shared by the runtime stack and the dev embedding services, so dev + prod on one machine costs no extra torch/CUDA |
| `python_dev_env` volume (dev only) | uv cache + the backend/provision dev venv | Same volume, so uv hardlinks the venv from its cache (`UV_LINK_MODE=hardlink`) instead of storing packages twice |
| `embedding_gpu_models` / `embedding_cpu_models` | Model weights (Hugging Face and FastEmbed caches), downloaded at service start | Survive image rebuilds; deleting them only forces a re-download |

Images that declare a `VOLUME` (Postgres for `db-bootstrap`, Jaeger) get a `tmpfs` at that path, so
the stack never creates anonymous, hash-named volumes.

See what uses space, then reclaim it:

```sh
docker system df -v                       # sizes per image, container and volume
docker image prune                        # dangling <none> layers left by rebuilds (safe)
docker builder prune                      # BuildKit cache; the next build re-downloads packages
docker volume ls --filter dangling=true   # volumes no container uses; review before removing
```

Never remove `pg_data`, `qdrant_data`, `minio_data`, `redis_data`, `keycloak_data` or `grafana_data`:
they hold data, not caches. The dev venv volume is always safe to delete; the next start rebuilds it:

```sh
docker compose rm -sf backend provision workspace
docker volume rm goldenguide_python_dev_env
```

**Windows: the disk file doesn't shrink.** Docker Desktop stores everything in
`%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx`, which grows but never shrinks on its own. After a
big cleanup, quit Docker Desktop, run `wsl --shutdown`, then compact it from an **administrator**
PowerShell:

```powershell
Optimize-VHD -Path "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx" -Mode Full
```

Without Hyper-V, use `diskpart`: `select vdisk file="<path>"`, `attach vdisk readonly`,
`compact vdisk`, `detach vdisk`. Never use Docker Desktop's *Clean / Purge data*: it deletes every
volume.

## Data and reproducibility

- Data lives in named volumes (`goldenguide_pg_data`, `goldenguide_qdrant_data`, ...), which survive
  `stop`, `down` and rebuilds. Only `down -v` or `docker volume rm` deletes them.
- Qdrant and MinIO images are pinned by digest so their storage formats never upgrade silently.
  Upgrading them is deliberate maintenance work: back up first.
- Python dependencies come from `uv.lock` (`--locked` fails instead of re-resolving).
- Jaeger traces are in memory and lost on restart; logs persist in Loki.
