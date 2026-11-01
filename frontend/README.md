# GoldenGuide frontend

React 19 + TypeScript (strict) + Vite single-page app. How it works: `docs/frontend/architecture.md`.
Interaction design: `docs/frontend/ux.md`. Plans and decision log: `docs/frontend/roadmap.md`.

## Setup

Node 24 and pnpm (pinned in `package.json` via corepack). If `corepack enable` needs admin rights on
your machine, prefix commands with `corepack` instead (`corepack pnpm install`).

```sh
cd frontend
pnpm install
pnpm dev            # http://localhost:5173, proxies /api to the backend
```

The dev proxy targets the backend container's published port and presents requests as coming from
`SITE_ORIGIN` (the backend's host allow-list and same-origin check accept only that origin). Override
with `GG_BACKEND_ORIGIN` / `GG_SITE_ORIGIN` in `frontend/.env.local`; defaults are
`http://localhost:8082` and `http://localhost:8080`.

## Commands

| Command | What it does |
|---|---|
| `pnpm dev` | Dev server with hot reload |
| `pnpm build` | Type-check and build to `dist/` |
| `pnpm typecheck` / `pnpm lint` | `tsc -b` / ESLint |
| `pnpm test` | Unit and component tests (Vitest, Testing Library, MSW) |
| `pnpm test:e2e` | Ensure Chromium is installed, then run Playwright against the production build with a mocked API |
| `pnpm gen:api` | Regenerate `src/api/schema.gen.ts` from the running backend's `/openapi.json` |

`corepack pnpm test:e2e` installs the browser revision required by the installed Playwright version
before starting the tests. Playwright reuses cached browser binaries on later runs and downloads a
new revision when an upgrade requires it. The install is explicitly chained in the script so it
also works when automatic pre/post script hooks are disabled. The first download needs internet.
Minimal Linux/CI images also need Playwright's OS libraries provisioned during environment setup
(`corepack pnpm exec playwright install --with-deps chromium`).

Run `pnpm gen:api` after changing backend request/response models and commit the result; a contract
change then fails `pnpm typecheck` instead of production.

## Layout

```
src/
  api/              typed API client (openapi-fetch) and TanStack Query hooks
  components/       app layout; ui/ holds shadcn/ui components (we own this code)
  features/chat/
    stream/         NDJSON stream contract: Zod event schemas, line reader, answer state
    useChatStream   send / stop / retry; one answer streams at a time
    labels.ts       all student-facing wording for statuses and outcomes
    components/     chat page, answer, sources, feedback, history sidebar
  router.tsx        routes: / (new chat), /c/$conversationId
```

## Stream contract

`POST /api/v1/chat/stream` returns NDJSON (`src/backend/api/streaming.py`). Every line is validated
with Zod (`stream/events.ts`). An answer is complete **only** when the last event is `ok`; it ends as
`error` (server message kept with partial text), `interrupted` (no terminal event), or `stopped`
(Stop pressed). Unknown event types are skipped so additive backend changes do not break deployed
clients; a known event with the wrong shape is an error.

New answers retain ordered text, citation, and table blocks in stored history, together with public
source metadata. Reloading a conversation uses the same renderers as the live answer. Messages
saved before migration `0004` retain their text fallback; previously discarded table data cannot be
recovered exactly. Apply the backend migration before starting the updated backend (the Compose
`provision` job owns migrations); a frontend restart alone does not update the database schema.

## Serving

- Docker development: `docker-compose.dev.yml` runs `frontend-vite` behind the existing `frontend`
  Nginx service. Open http://localhost:8080 (or `FRONTEND_PORT`): UI changes hot-reload, `/c/<id>`
  routes work directly, and API/auth requests keep the same origin. Port 5173 is internal only.
  The source is bind-mounted; Linux dependencies live in `frontend_node_modules`, separate from
  host dependencies. Restart `frontend-vite` after changing `package.json` / `pnpm-lock.yaml`;
  it runs `pnpm install --frozen-lockfile` at startup. Windows file watching uses polling by default;
  set `FRONTEND_DEV_POLLING=false` on hosts with working native file events.
- Docker runtime: `docker/frontend/Dockerfile` builds this app and serves `dist/` with Nginx (SPA fallback,
  `/api` proxied, same origin).
- Without Nginx: FastAPI serves `frontend/dist` when `SERVE_FRONTEND=true` (`src/backend/api/spa.py`);
  run `pnpm build` first.

From the repository root, with the development env file selected:

```sh
docker compose up -d --build frontend
docker compose logs -f frontend frontend-vite
```

The `frontend` profile includes both services. `BACKEND_ORIGIN` can point at a remote backend;
`SITE_ORIGIN` remains the browser's public origin. Running `pnpm dev` locally remains supported.

### Updating a running staging/production frontend

The runtime image has no bind mount: source changes need a new image. Pass the environment's env file
so Compose targets its project (e.g. `goldenguide-prod`); without it, Compose uses the development
project and fails with "port is already allocated".

```sh
docker compose --env-file .env.prod build frontend              # running containers are unaffected
docker compose --env-file .env.prod up -d --no-deps frontend    # replaces only the frontend (~1 s gap)
```

`docker compose restart frontend` does not pick up changes (same image). Hard-refresh the browser
afterwards; `index.html` is `no-cache` and assets are content-hashed.

Configuration regressions can be checked without a Docker daemon:
`uv run pytest tests/deploy/test_frontend_compose.py -q` (Docker Compose CLI required).
