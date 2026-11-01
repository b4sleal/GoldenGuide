# Security model

> **Audience:** Developers, operators and reviewers.

- [Access policy](#access-policy)
- [Sign-in (OIDC)](#sign-in-oidc)
- [Local admin without sign-in](#local-admin-without-sign-in)
- [Microsoft Entra ID for WLU](#microsoft-entra-id-for-wlu)
- [Service clients](#service-clients)
- [Rate limiting](#rate-limiting)
- [Fail-closed rules](#fail-closed-rules)
- [HTTP hardening](#http-hardening)
- [Secrets and network exposure](#secrets-and-network-exposure)
- [Untrusted input](#untrusted-input)

---

## Access policy

| Caller | Can do |
| --- | --- |
| Anyone | Chat (`/api/v1/chat/stream`), rate-limited per client |
| This browser (anonymous device cookie) | Its own conversations: list, read, delete, rate answers. The `gg_client` cookie is random, HttpOnly, SameSite=Lax (Secure on HTTPS), renewed for a year on each chat; only its SHA-256 hash is stored. Another browser's conversation or message returns `404`, never `403`. Delete and feedback also require same-origin. Students never see stored diagnostics |
| Signed-in student | Same as anyone today. `require_student` exists if WLU wants chat limited to authenticated students (an open decision) |
| Signed-in admin | Every admin route and `/docs`; holds every scope |
| This machine, sign-in off, `LOCAL_ADMIN=true` | Same as an admin ([local admin](#local-admin-without-sign-in)); never via the tunnel, never in production |
| Service client (bearer key) | Only the scopes configured for it, e.g. `sources:collect`, `indexing:sync`, `jobs:read` |

Admin routes are mounted under `/api/v1/admin` behind `get_principal` and an origin check. Each
child router also declares the scope it requires (`require_scope`), so a route stays protected even
if it is ever mounted somewhere else.

Scopes: `settings:write`, `documents:write`, `sources:collect`, `indexing:sync`, `jobs:read`.

## Sign-in (OIDC)

`AUTH_MODE=oidc` enables sign-in; `disabled` turns it off. The flow is the standard OpenID Connect
authorization-code flow with **PKCE (S256)** and a **nonce-bound ID token**, implemented with
Authlib and joserfc (`src/backend/infra/security/oidc/authlib_client.py`):

1. `GET /api/v1/auth/login` stores a single-use OAuth transaction (PKCE verifier, nonce, state) in
   Redis and redirects to the provider.
2. `GET /api/v1/auth/callback` consumes that transaction once, exchanges the code, and verifies the
   ID token: signature against the provider's JWKS, issuer, audience/authorized party, expiry and
   nonce. Any failure is a rejected login.
3. Roles are read from the standard `roles` claim (Entra app roles) and Keycloak's
   `realm_access.roles`. **Only explicitly configured roles count** (`OIDC_ADMIN_ROLE`,
   `OIDC_STUDENT_ROLE`): a successful institutional login alone never makes someone a student or
   an admin.
4. A server-side session is created in Redis. The browser holds only an opaque, random `gg_session`
   cookie. Session subjects are issuer-qualified, so identical `sub` values from two providers never
   collide.

Everything provider-specific comes from the discovery document (`OIDC_DISCOVERY_URL`). HTTPS is
required for every provider URL except the local development hosts listed in
`configs/base/system_config.yml`.

**Development provider.** The `auth` profile runs Keycloak with the realm in
`deploy/keycloak/realm.json`: client `goldenguide-web`, role `goldenguide-admin`, and one user whose
username, password and role come from `KC_TEST_ADMIN_USERNAME`, `KC_TEST_ADMIN_PASSWORD` and
`KC_TEST_ADMIN_ROLE` in `.env`. Development normally runs with sign-in off, so this is optional.

Both bundled realms define only the admin role. `OIDC_STUDENT_ROLE` still maps a student role when the
identity provider defines one (for example a WLU Entra app role); with no such role, signed-in users get
no GoldenGuide role and chat stays public.

**Staging and production.** Each runs its own Keycloak with `deploy/keycloak/realm.hosted.json`: the same client
and roles, redirect URIs taken from `SITE_ORIGIN`, PKCE required, brute-force protection on, registration off,
and one seeded user: the first GoldenGuide admin, from `KC_ADMIN_USERNAME`, `KC_ADMIN_PASSWORD` and
`KC_ADMIN_ROLE`. Other team members are created in the console or sign in through Google as an identity provider
inside Keycloak; roles are always assigned in Keycloak ([environments](environments.md#keycloak-for-staging-and-production)).
It still runs in Keycloak's development mode, which suits a small team; a hardened setup or the institution's
managed provider is the longer-term answer.

## Local admin without sign-in

For development, `AUTH_MODE=disabled` with `LOCAL_ADMIN=true` (the `.env.dev.example` default) treats
requests from **this machine** as an admin, so data can be loaded from `/docs` without running
sign-in. A request counts as local only if:

1. it did not come through the Cloudflare tunnel: Cloudflare's edge adds `CF-Connecting-IP` to every
   request it forwards, and any request carrying that header is refused; and
2. its direct peer is a loopback or private address (the Nginx container or Docker's gateway).

A developer's public dev hostname (a Cloudflare tunnel) is therefore not treated as local: requests
through it carry `CF-Connecting-IP` and get no `LOCAL_ADMIN` access. Protect dev and staging hostnames
with a Cloudflare Access policy as well ([environments](environments.md#public-hostnames-and-tunnels)).

Inside Docker no request arrives from `127.0.0.1`, so an address check alone can't identify "this
machine". The guarantee comes from published ports binding to loopback (`*_BIND_ADDRESS=127.0.0.1`,
the default): the only route in from outside is then the tunnel. If you publish the frontend or backend on a LAN or
Tailscale address, everyone who can reach them counts as local: turn `LOCAL_ADMIN` off or use
`AUTH_MODE=oidc`. `LOCAL_ADMIN` is ignored when sign-in is enabled, and the backend refuses to start
with it when `APP_ENV=production`.

## Microsoft Entra ID for WLU

Nothing in the domain or application layers is Keycloak-specific, so moving students and faculty to
WLU's Microsoft accounts is a configuration change:

```env
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/<wlu-tenant-id>/v2.0/.well-known/openid-configuration
OIDC_CLIENT_ID=<app registration client id>
OIDC_CLIENT_SECRET=<app registration secret>
OIDC_REDIRECT_URI=https://askgoldenguide.ca/api/v1/auth/callback
OIDC_ADMIN_ROLE=<app role for administrators>
OIDC_STUDENT_ROLE=<app role for students>
```

In Entra, define app roles (e.g. `Student`, `Faculty`, `Admin`) on the app registration and assign
them to groups; they arrive in the `roles` claim that GoldenGuide already reads. A faculty role
(for features such as syllabus uploads) would be one new `Role` value and a mapping. This is
planned and not yet tested against a real WLU tenant.

## Service clients

Machine callers (the nightly ingestion workflow) don't sign in. They send
`Authorization: Bearer <key>` for a client configured in `system.service_clients`
(`configs/base/system_config.yml`) with only the scopes it needs.

- The server stores only **SHA-256 hashes** of keys, two per client (current and previous) for
  rotation without downtime. A client with no hash configured is disabled.
- A bearer request is never mixed with a cookie: a wrong key is `401` and does not fall back to the
  session. Service-key authentication works regardless of `AUTH_MODE`.
- Create a key (prints the key once and the hash setting for `.env`; nothing is written to disk):

  ```sh
  docker compose exec backend python -m backend.core.startup.service_key github_actions_nightly
  ```

## Rate limiting

Chat is limited per client: `CHAT_RATE_LIMIT` requests (default 10) per `CHAT_RATE_WINDOW_SECONDS`
(default 60), answered with `429` and `Retry-After`. The counter lives in Redis, so the limit holds
across every API replica. Forwarded client addresses are trusted only from `TRUSTED_PROXY_CIDRS`
(by default, the Compose network the Nginx frontend is on); anyone else could forge the header.

## Fail-closed rules

| Situation | Result |
| --- | --- |
| `AUTH_MODE=disabled` and an admin route is called from outside this machine, or `LOCAL_ADMIN` is off | `503`: nobody can be authorized |
| `LOCAL_ADMIN=true` with `APP_ENV=production` | Backend refuses to start |
| No session cookie / expired session | `401` |
| Session store (Redis) unavailable | Request fails (`5xx`); an outage never grants access |
| OAuth transaction missing, reused or expired | Login rejected |
| ID token fails any check | Login rejected |
| Production started without a credential | Compose refuses to start (`docker-compose.prod.yml`) |
| `APP_ENV=production` with a non-HTTPS `SITE_ORIGIN` | Backend refuses to start |

Optional caches behave the other way on purpose: a cache miss or outage falls back to PostgreSQL.

## HTTP hardening

- **Same-origin check** on every state-changing request from a browser session (CSRF defense in
  depth on top of the session cookie's attributes).
- **Security headers** middleware: CSP with `frame-ancestors` from `FRAME_ANCESTORS` (`'none'` by
  default; set it to approved WLU origins to embed the chat), plus the usual hardening headers.
  Static UI headers live in `docker/frontend/default.conf.template`.
- **Session cookie** is `HttpOnly`, `SameSite=Lax`, and holds only a random id.
- **Allowed hosts** (`ALLOWED_HOSTS`); WebSocket attempts are refused cleanly (the API is HTTP-only).
- `OIDC_REDIRECT_URI` must equal `SITE_ORIGIN` + `/api/v1/auth/callback`, or the backend won't start.
- **Error boundary.** Errors return one envelope with `request_id` and `trace_id`; stack traces and
  internal details stay in the logs.
- **API docs** (`/docs`, `/openapi.json`) are admin-only.
  Swagger UI's inline initializer is allowed by a SHA-256 hash of its exact bytes, added to
  `script-src` on that response only; the CSP never allows arbitrary inline scripts.

## Secrets and network exposure

- Secrets come only from the environment through the `SecretReader` port (`${secrets:NAME}` in
  YAML is resolved at load time and never logged). The log redactor masks token-like fields.
- Published ports bind to `127.0.0.1` by default (`*_BIND_ADDRESS`). Multi-machine traffic stays on
  a private Tailscale network: each machine's `tailscale` container forwards only the ports in
  `deploy/tailscale/serve.json`, and only to tailnet devices. Public traffic enters only through the Cloudflare Tunnel to the
  frontend, never directly to the backend or a data store.
- The embedding service requires its own API key (`LOCAL_EMBEDDING_SERVICE__API_KEY`); Qdrant,
  MinIO, Redis and PostgreSQL all require credentials.
- PostgreSQL and Redis connections are not TLS-encrypted today; run them on a trusted private
  network. MinIO and Qdrant support TLS through their `SECURE` / `HTTPS` flags.

## Untrusted input

Scraped content, uploaded files, user messages and LLM output are all treated as untrusted. The
router LLM's plan is validated against the entities extracted in code before anything runs, so a
prompt cannot trigger arbitrary queries or privileged operations. Database access is parameterized.
Questions and answers are logged for review, so log retention and access must be treated as student
data.
