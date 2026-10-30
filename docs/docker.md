# Running GoldenGuide with Docker Compose

First-time setup is in [getting started](getting-started.md). This page covers how the Compose
stack is put together and how to run it in other shapes: separate machines, production, limited
hardware.

- [Compose files](#compose-files)
- [Profiles](#profiles)
- [Images](#images)
- [Development vs runtime](#development-vs-runtime)
- [Separate machines](#separate-machines)
- [Production](#production)
- [Staging and environment files](#staging-and-environment-files)
  - [Public hostnames and tunnels](#public-hostnames-and-tunnels)
- [Frontend, authentication and tunnel](#frontend-authentication-and-tunnel)
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

```sh
# Development
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all-dev --profile embedding-gpu up -d --build
# Production
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile all --profile embedding-gpu up -d --build
# Staging: production overrides with staging's own environment file
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.prod.yml --profile all --profile embedding-gpu up -d --build
# Validate without starting anything
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all-dev config --quiet
```

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
| `frontend` | Nginx: static UI and API reverse proxy |
| `auth` | Development Keycloak |
| `observability` | Loki, Alloy, Grafana, Jaeger, OpenTelemetry Collector |
| `log-shipper` | Alloy only, for machines that send logs to another machine's Loki |
| `tailnet` | Tailscale node for private networking between machines |
| `tunnel` | Cloudflare Tunnel (publishes the frontend at the public domain) |
| `all` | Everything except the embedding services, including the tunnel |
| `all-dev` | Everything except the embedding services, the tunnel and Keycloak (add `--profile auth` to test sign-in) |

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
| `development` | toolchain as `app`; dependencies sync at container start | Dev `backend`, `provision` |
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
| Frontend | Files baked into the Nginx image | `src/frontend` mounted read-only |
| Test database | Not created | `db-bootstrap` also creates `goldenguide_test` |

Embedding services are restarted manually so model loading stays explicit. Changes to the
`Dockerfile` or `docker/start-python-service.sh` need `--build`.

**IDE workspace.** `.devcontainer/compose.yml` adds a `workspace` service (the `development` image,
sleeping) that mounts the same `python_dev_env` volume as `backend` and `provision`. The IDE uses its
interpreter for type hints and test runs, so the venv and uv cache exist once and are shared. See
[editor setup](getting-started.md#editor-setup-type-hints-from-docker).

## Separate machines

Every profile can run on its own host. Point each host's `.env` at the others' endpoints:

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
- **Tailscale** (`--profile tailnet` on each machine, with `TS_AUTHKEY` and `MACHINE_NAME`) puts the
  machines on one private network without exposing ports to the internet. Publish shared services
  on that machine's Tailscale IP via the relevant `*_BIND_ADDRESS`.
- Published ports bind to loopback by default. Otherwise set the bind address to a private
  interface and allow only the client hosts through the firewall/security group.
- PostgreSQL and Redis connections are not TLS-encrypted today: keep them on a trusted private
  network or VPN. MinIO and Qdrant support TLS through their `SECURE`/`HTTPS` flags (the server or a
  reverse proxy must also serve TLS).
- Observability on another machine: see [observability](observability.md#multiple-machines).

## Production

```sh
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile all --profile embedding-gpu up -d --build
# Rebuild and restart only the API after a code change (provision runs first and applies any new migration)
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile all --profile embedding-gpu up -d --build backend
```

Without `--env-file .env.prod`, Compose reads `.env` (development) and stops on the first missing production
variable, for example `KC_ADMIN_PASSWORD`.

`docker-compose.prod.yml` removes every development credential fallback: Compose refuses to start
if any admin, database, object-store, vector-store or cache secret is missing (for every service in
the file, including profiles that host doesn't run). With `APP_ENV=production`, the backend also
requires an HTTPS `SITE_ORIGIN` and a trace exporter. The development test database is not created.

Database creation in production belongs to infrastructure code (Terraform/CDK for RDS) or a DBA,
never to the application; `provision` only migrates an existing database.

**Secrets.** On one self-managed host, `.env.prod` readable only by the deploy user (`chmod 600`) and
never committed is acceptable. A larger deployment has no env file on disk: a secret manager (AWS
Secrets Manager, Azure Key Vault) or the CI/CD pipeline injects the values as environment variables
when the containers start. `EnvSecretReader` already reads `os.environ`, and a `.env` file never
overrides a variable that is already set. Plain environment variables are visible to anyone with
Docker access on the host (`docker inspect`); a manager-backed `SecretReader` avoids that.

## Staging and environment files

Staging is a production-style copy of the stack for the whole team (QA, staff). It runs the same
Compose files as production, with its own data stores, credentials, OIDC client and tunnel, and
`APP_ENV=staging`.

| Environment | File | Template | Compose command |
| --- | --- | --- | --- |
| Development | `.env` | `.env.dev.example` | `docker-compose.yml` + `docker-compose.dev.yml` |
| Staging | `.env.staging` | `.env.staging.example` | `--env-file .env.staging`, `docker-compose.yml` + `docker-compose.prod.yml` |
| Production | `.env.prod` | `.env.prod.example` | `--env-file .env.prod`, `docker-compose.yml` + `docker-compose.prod.yml` |

- `.env` stays the development file because the tests and `uv run` read it (`tests/conftest.py`,
  `EnvSecretReader`). Its template is `.env.dev.example`.
- Every `.env.*` file except the `.example` templates is git-ignored. Never commit one. Back the real
  values up in a password manager: they are not in git.
- The staging and production templates leave every credential blank on purpose.
  `docker-compose.prod.yml` refuses to start while one is empty, so nobody deploys with `admin/admin`.
  The development template has working `admin/admin` defaults.
- `--env-file` makes Compose read that file instead of `.env`. The file sets `ENV_FILE=<its own name>`,
  which the Python services use as their `env_file`, so substitution and the containers read the
  same values. Without the flag, Compose falls back to `.env`.
- Each environment has its own Cloudflare tunnel and token (`TUNNEL_TOKEN` in its file); see
  [Public hostnames](#public-hostnames-and-tunnels).
- On dedicated hosts, save the environment's file as `.env` and drop the `--env-file` flag.
- Each environment file sets its own `COMPOSE_PROJECT_NAME` (`goldenguide-staging`, `goldenguide-prod`;
  development keeps the default `goldenguide`). Compose prefixes containers, networks and volumes with
  it, so each environment has its own data (`goldenguide-prod_pg_data`, `goldenguide_pg_data`, ...) even on
  one machine. Images are shared, since their names are fixed.
- To run two environments at the same time on one machine, also give each its own `APP_NETWORK_SUBNET` and
  host ports; they would otherwise collide. Check what Compose will apply with
  `docker compose --env-file .env.staging config`.
- PostgreSQL stores its user and password in its data directory on first start. If you copy data between
  environments, the target's `DB__POSTGRES__USER` and `DB__POSTGRES__PASSWORD` must match the copied database.
- To drop the `-f` and `--profile` flags, set `COMPOSE_PATH_SEPARATOR=;` (`:` on Linux),
  `COMPOSE_FILE=docker-compose.yml;docker-compose.prod.yml` and `COMPOSE_PROFILES=all,embedding-gpu`
  in the environment's file. A command-line `-f` overrides `COMPOSE_FILE`.
- Staging is configured like production (HTTPS origin, OIDC, no `LOCAL_ADMIN`), but the backend's
  startup checks (HTTPS `SITE_ORIGIN`, no `LOCAL_ADMIN`, required trace exporter) currently apply only
  to `APP_ENV=production`. Staging does not enforce them yet.

### Public hostnames and tunnels

| Environment | Hostname | Tunnel | Who can reach it |
| --- | --- | --- | --- |
| Production | `askgoldenguide.ca` | `goldenguide-prod` | Public |
| Staging | `staging.askgoldenguide.ca` | `goldenguide-staging` | Team only: Cloudflare Access policy |
| Development | Optional, one per developer (for example `dev-<name>.askgoldenguide.ca`) | One tunnel per developer | Only that developer: Cloudflare Access policy |

- Each tunnel's public hostname in the Cloudflare Zero Trust dashboard points at `http://frontend:8080`.
  That name resolves on the Compose network of the machine running that tunnel's `cloudflared`, so
  the same route reaches whichever stack the tunnel runs next to.
- The tunnel token is that tunnel's identity and a secret. Keep each token only in its own environment's
  file, and never share one between machines: `cloudflared` instances using the same token become
  replicas and Cloudflare splits traffic between them.
- Add the Access policy before the hostname goes live. A new public hostname is open until a policy exists.
- Set `SITE_ORIGIN`, `ALLOWED_HOSTS` and `OIDC_REDIRECT_URI` in the environment's file to its hostname,
  and register that redirect URI on a separate OIDC client per environment.

### Keycloak for staging and production

Staging and production run their own Keycloak (profile `all`) with the hosted realm
`deploy/keycloak/realm.hosted.json`. `docker-compose.prod.yml` mounts it in place of the development
realm. Its redirect URIs and web origins come from `SITE_ORIGIN`, so one file serves both environments.
It seeds one user, the first GoldenGuide admin (`KC_ADMIN_USERNAME`, `KC_ADMIN_PASSWORD`, role `KC_ADMIN_ROLE`);
brute-force protection is on, registration is off, and PKCE is required.

| Environment | Keycloak address (`KC_HOSTNAME`) | Tunnel route |
| --- | --- | --- |
| Production | `https://auth.askgoldenguide.ca` | `auth.askgoldenguide.ca` → `http://keycloak:8081` on the prod tunnel |
| Staging | `https://auth-staging.askgoldenguide.ca` | `auth-staging.askgoldenguide.ca` → `http://keycloak:8081` on the staging tunnel |

Set up, once per environment:
1. **Tunnel route.** Add the hostname above to that environment's tunnel in the Cloudflare dashboard.
   Don't put a Cloudflare Access policy on the whole hostname: the backend calls it to verify sign-ins.
   Do protect the admin console, `/admin*` and `/realms/master*`, with your team-only Access policy.
2. **Start it.** `KC_HOSTNAME`, `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are already in the
   env file. The realm imports only into an empty `keycloak_data` volume; to re-import, remove that volume.
3. **Admins.** The first admin (`KC_ADMIN_USERNAME` / `KC_ADMIN_PASSWORD`) can sign in to GoldenGuide as soon
   as the realm is imported. The seed runs only on that first import: on an existing `keycloak_data` volume,
   changing these variables does nothing, so create or reset the user in the console instead. To add team members,
   sign in to `<KC_HOSTNAME>/admin/` with `KC_BOOTSTRAP_ADMIN_USERNAME` and `KC_BOOTSTRAP_ADMIN_PASSWORD`
   (Keycloak's master realm, not a GoldenGuide user), switch to the `goldenguide` realm, create each person and
   give them the `goldenguide-admin` role.
4. **Optional: Google sign-in.** In the `goldenguide` realm, add Identity providers > Google with a client ID and
   secret from a Google Cloud OAuth client. Its authorized redirect URI is
   `<KC_HOSTNAME>/realms/goldenguide/broker/google/endpoint`. A person who signs in with Google for the first time
   has no role until you give them `goldenguide-admin` (or create the user first and link by email).
5. **Turn sign-in on.** Set `AUTH_MODE=oidc` in the env file and recreate the backend (`up -d backend`).
   Do this only after the tunnel route exists, or the backend can't reach Keycloak.

This is still Keycloak's development mode (`start-dev`, built-in database). It is suitable for a small team;
a hardened setup (production mode, a PostgreSQL database for Keycloak, backups) is a separate step.

## Frontend, authentication and tunnel

- The browser uses `/api/...` on the frontend origin. Nginx forwards those requests, cookies and
  streamed responses to `BACKEND_ORIGIN`; static files never touch FastAPI. HTTPS backend origins are
  checked against the Nginx image's CA bundle.
- Set `SITE_ORIGIN` and `OIDC_REDIRECT_URI` to the frontend's public origin and add that host to
  `ALLOWED_HOSTS`. To embed the chat in a WLU page, set `FRAME_ANCESTORS` and the frame policy in
  `docker/frontend/default.conf.template`.
- `TRUSTED_PROXY_CIDRS` defaults to the Compose subnet so per-client rate limiting works behind
  Nginx. For a remote frontend, set it to that proxy's private IP; never trust arbitrary forwarders.
  Change `APP_NETWORK_SUBNET` if the default conflicts with a VPN.
- **Cloudflare Tunnel** (`--profile tunnel`, `TUNNEL_TOKEN`) publishes the frontend without opening
  inbound ports. Each environment has its own tunnel and hostname; see
  [Public hostnames](#public-hostnames-and-tunnels).
- Keycloak's `auth` profile is a development server. Production uses the institution's managed OIDC
  provider or a separately hardened Keycloak ([security](security.md)).

## Resource limits

Every container has `cpus`, `mem_limit` and a matching `memswap_limit` (matching values disable
swap: a service over its RAM is OOM-killed and restarted instead of swapping). Defaults:

| Services | CPU / RAM |
| --- | --- |
| Small services | 0.5 / 512 MiB |
| Backend, provision, PostgreSQL, Keycloak | 1 / 1 GiB |
| Qdrant | 1 / 2 GiB |
| Each embedding service | 2 / 4 GiB system RAM |

Change them with the `*_CPUS` / `*_MEMORY_LIMIT` variables. They are maximums, not reservations;
their sum can exceed the machine, so run only the profiles you need. New limits apply when
containers are recreated. Embedding BLAS threads (`EMBEDDING_THREADS`) and uv's download/install
concurrency (`UV_CONCURRENT_*`) are bounded too. Logs rotate at 10 MiB × 3 files.

Not covered by container limits:

- **Windows / WSL.** Docker Desktop, the WSL kernel and page cache share one WSL budget. Copy or merge
  `wslconfig.example` into `%UserProfile%\.wslconfig` (4 CPUs, 8 GB, no swap, gradual memory
  reclaim), then `wsl --shutdown` and restart Docker Desktop. On backends with direct CPU/RAM
  settings, use Docker Desktop's Settings > Resources.
- **Image builds.** `RUN` steps ignore service limits. Use a capped builder:

  ```sh
  docker buildx create --name goldenguide-limited --driver docker-container --driver-opt memory=4g,memory-swap=4g,cpu-quota=200000,cpu-period=100000,default-load=true --buildkitd-config docker/buildkitd.toml
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --parallel 1 --profile all-dev --profile embedding-gpu build --builder goldenguide-limited
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all-dev --profile embedding-gpu up -d --no-build
  ```

- **GPU memory.** GPU reservation grants access to the device; it doesn't cap VRAM.
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
| **Build cache limit** | Docker Desktop > Settings > Docker Engine: merge [`docker/daemon.example.json`](../docker/daemon.example.json) | Keeps at most 10 GB of build cache and rotates container logs (10 MB × 3) for every container, not only GoldenGuide's |
| **Shrink freed space automatically** | Merge [`wslconfig.example`](../wslconfig.example) into `%UserProfile%\.wslconfig` | `sparseVhd=true` returns freed space to Windows for disks created afterwards |
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
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile "*" rm -sf backend provision
docker compose -f docker-compose.yml -f .devcontainer/compose.yml rm -sf workspace   # if you use the IDE workspace
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
