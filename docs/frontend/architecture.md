# Frontend Architecture

**For:** developers, reviewers. How the web client in `frontend/` is built, as implemented (2026-11-01).
How it behaves for students: [ux.md](ux.md). What is planned and the decision log:
[roadmap.md](roadmap.md). Commands and setup: `frontend/README.md`.

## Stack

| Concern | Library |
|---|---|
| App | React 19, TypeScript (strict, `noUncheckedIndexedAccess`), Vite |
| Routing | TanStack Router, code-based routes |
| Server state | TanStack Query |
| API types | `openapi-typescript` (generated `src/api/schema.gen.ts`) + `openapi-fetch` |
| Stream validation | Zod |
| UI | Tailwind CSS v4, shadcn/ui components (Radix), lucide icons |
| Markdown | `react-markdown` + `remark-gfm` |
| Tests | Vitest, Testing Library, MSW 3, Playwright |
| Package manager | pnpm (pinned in `package.json`, run through corepack) |

## Why this stack

- **Static SPA, same origin as the API.** FastAPI stays the only backend, so the device cookie,
  Redis-backed session and same-origin guard apply unchanged.
- **Generated API types.** A backend contract change fails `pnpm typecheck`, not production.
- **Zod for the stream.** NDJSON is not described by OpenAPI, so each event is validated at runtime.
- **shadcn/ui.** Accessible Radix primitives, with the component code owned by the project.
- **Rejected: Next.js.** A second (Node) server would duplicate session, cookie and CSRF handling
  FastAPI already owns, and SEO does not matter for a chat app.
- **Rejected: Vercel AI SDK `useChat`.** It expects its own stream protocol; a small `useChatStream`
  hook fits the NDJSON contract instead.

## Source layout

```
frontend/
  index.html, vite.config.ts, playwright.config.ts, eslint.config.js, components.json
  public/logo.png
  e2e/chat.spec.ts                Playwright smoke test (API mocked, production build)
  src/
    main.tsx                      QueryClient, router, theme applied before first paint
    router.tsx                    routes: "/" (new chat), "/c/$conversationId"
    index.css                     theme tokens (light/dark), motion, answer typography
    api/
      schema.gen.ts               generated from FastAPI /openapi.json (pnpm gen:api)
      client.ts                   typed client, ApiError (server error envelope), unwrap()
      conversations.ts            Query hooks: list, messages, delete, feedback
    components/
      AppLayout.tsx               sidebar / mobile drawer, header, theme toggle, skip link
      ui/                         shadcn/ui components we own (button, sheet)
    lib/                          cn() class helper, theme persistence
    features/chat/
      stream/
        events.ts                 Zod schemas for every stream event
        ndjson.ts                 NDJSON line reader
        answer.ts                 pure answer state machine
        history.ts                replays stored answer_content through the live reducer
        streamChat.ts             the POST + header + event loop; never throws
      useChatStream.ts            send / stop / retry / reset
      ChatSession.tsx             provider above the routes
      chatSessionContext.ts       context + useChatSession()
      clipboard.ts                answer -> clipboard text (Markdown, tab-separated tables, source URLs)
      labels.ts                   all student-facing wording
      components/
        ChatPage, Composer        route page; composer stays mounted across the first URL change
        AnswerView, AnswerBlocks  answer + progress; blocks shared by live and stored answers
        Markdown, EvidenceTable   safe text rendering; tables from data, inside TableScroll
        SourceList, SourceCarousel  numbered sources in a scrollable row (touch, drag, keys)
        AnswerActions, Feedback   copy answer; thumbs up/down (stored answers only)
        Notice, HistorySidebar    outcome notices; conversation list with two-click delete
    test/                         Vitest setup, MSW server and stream helpers
```

## Answer streaming

```
Composer -> useChatStream.send -> streamChat (fetch POST /api/v1/chat/stream)
         -> readNdjson (lines -> Zod-validated events) -> applyEvent (answer.ts) -> AnswerView
```

1. **Reading.** `readNdjson` decodes bytes with `TextDecoder({stream: true})` and parses complete
   lines only, so lines and multi-byte characters split across network chunks are handled. A trailing
   fragment without `\n` (cut connection) is dropped.
2. **Validation.** Each line is checked against `StreamEvent` (Zod). Unknown `type`s are skipped so a
   new backend event does not break deployed clients; a known type with the wrong shape raises
   `StreamProtocolError`, shown as an "unexpected response" error, never rendered.
3. **State.** `answer.ts` is pure and unit tested. Phases:

   | Phase | Cause | Shown |
   |---|---|---|
   | `pending` | sent, no text yet | latest `status` label ("Searching LORIS registration…") |
   | `streaming` | text/citation/table arrived | text with caret |
   | `complete` | last event `ok` | answer, sources; "Answer ready." announced |
   | `error` | `error` event, or HTTP error before the stream | partial text kept + server message + reference ID + retry |
   | `interrupted` | stream ended with neither `ok` nor `error` | "cut off… not a complete answer" + retry |
   | `stopped` | student pressed Stop (`AbortController`) | "You stopped this answer" + retry |

   Events after a terminal one are ignored.
4. **Rendering.** Text and citations accumulate into Markdown blocks; a citation becomes a link
   titled `gg-citation`, which `Markdown.tsx` renders as a numbered chip. `table` events are separate
   blocks rendered by `EvidenceTable` from the data (never through Markdown, so scraped `|` or `<`
   cannot change the table). `react-markdown` renders no raw HTML and drops unsafe URLs.
5. **Transport errors.** `streamChat` returns `ended | aborted | failed` instead of throwing; the hook
   maps that to one final phase. A network error before the response is `failed`; one after the
   stream started is `ended` (and so `interrupted`).

## Chat session and routing

- `ChatSessionProvider` (in `AppLayout`, above the router outlet) owns `useChatStream`, so a new
  chat's first answer keeps streaming when the URL changes from `/` to `/c/<id>`.
- When the stream's `X-Conversation-Id` names a new conversation, the provider navigates to
  `/c/<id>` (replace) and refreshes the history list. Later questions send that ID back.
- `ChatPage` calls `reset(conversationId)` on route change: switching conversation aborts any running
  answer and clears live turns. The current conversation ID is kept in a ref, updated synchronously,
  so navigation that renders before the reducer does is not mistaken for a switch.
- `ChatPage` shows stored messages (`GET .../messages`) followed by live turns. A conversation started
  on this page (`startedHere`) skips the stored fetch (it would duplicate the first question). The
  messages query does not refetch on focus/reconnect for the same reason; reopening it loads fresh.
- Saved assistant messages include versioned `answer_content` blocks (text, citations, tables) and
  public source metadata. `stream/history.ts` replays those blocks through the live reducer;
  `AnswerBlocks` shares the live renderers, including table scrolling. Message status still controls
  incomplete-answer notices. Older messages with no snapshot render their original `content` text.
- Only one answer streams at a time; `send` and `retry` are ignored while one is running.

## API access

- Same origin only (`credentials: "same-origin"`): the device cookie and the backend's same-origin
  check apply unchanged. URLs are absolute (`window.location.origin`) so the same code runs in tests.
- Error responses are parsed into `ApiError(status, {code, message, request_id, trace_id})`.
- `pnpm gen:api` regenerates types from the running backend; a backend contract change then fails
  `pnpm typecheck`. The NDJSON stream is not in OpenAPI, which is why it has Zod schemas.

## UI

Layout, loading, status wording and accessibility are described in [ux.md](ux.md). Implementation notes:

- Theme choice stored in `localStorage` (`gg-theme`); storage failures are ignored.
- Wording lives in `labels.ts` (status labels, notices, feedback reasons, suggested questions).

## Serving

| Mode | How |
|---|---|
| Development | `pnpm dev` on :5173. Proxies `/api` to the backend (`GG_BACKEND_ORIGIN`, default `http://localhost:8082`) and rewrites `Host`/`Origin` to `SITE_ORIGIN` (`GG_SITE_ORIGIN`, default `http://localhost:8080`), which the backend's host allow-list and same-origin check require. Dev only. |
| Docker development | Nginx on `FRONTEND_PORT` (default :8080) proxies UI and the HMR WebSocket to internal `frontend-vite:5173`; API/auth requests go directly to `BACKEND_ORIGIN`, preserving the public Host/Origin and cookies. React source is bind-mounted; Linux dependencies live in a named volume. Polling is enabled by default for Windows mounts. |
| Docker | `docker/frontend/Dockerfile`: Node 24 stage runs `pnpm install --frozen-lockfile && pnpm build`; Nginx serves `dist/`. `try_files $uri /index.html` for client routes; `index.html` `no-cache`; `/assets/` (hashed) cached immutable. CSP no longer allows CDNs. |
| FastAPI only | `SERVE_FRONTEND=true` mounts `frontend/dist` via `src/backend/api/spa.py` (`SpaStaticFiles`): extensionless non-`/api` paths fall back to `index.html`; missing assets and unknown API paths stay 404; startup fails with a clear message if the build is missing. |

The dev proxy permits React Refresh's inline preamble and same-origin WebSockets in its CSP.
The runtime proxy retains its stricter policy and immutable caching for built assets.

## Tests

| File | Covers |
|---|---|
| `stream/ndjson.test.ts` | split lines, split UTF-8, blank lines, unknown types, bad shapes, bad JSON |
| `stream/answer.test.ts` | every phase, status, citations, table order, sources, no change after terminal |
| `stream/history.test.ts` | restored block order, original source numbering, legacy text fallback, table-only answers |
| `useChatStream.test.tsx` | complete, conversation ID round trip, error event, closed and dropped stream, Stop, HTTP 429, protocol error, retry, reset (MSW) |
| `components/ChatPage.test.tsx` | full streamed answer and URL change, interrupted notice, return to new chat, partial answer kept through navigation, stored history, 404, thumbs-down with reason (MSW + memory router) |
| `components/Composer.test.tsx` | draft kept through automatic URL assignment, cleared on explicit switch; Enter / Shift+Enter / Stop |
| `components/AnswerView.test.tsx` | source-specific progress dots removed when content arrives |
| `components/AnswerActions.test.tsx` | copy on live answers, denied clipboard + retry, Copy beside feedback, no Copy when empty |
| `components/EvidenceTable.test.tsx` | database values and line breaks preserved; labelled, focusable table viewports (data and Markdown tables) |
| `components/SourceList.test.tsx` | backend order/numbering kept, no frontend merging, nav controls only on overflow, mouse drag vs click, touch left to browser |
| `clipboard.test.ts` | ordered prose, table values and source URLs; no citation hints; empty answers |
| `api/client.test.ts` | fetch resolved per request (test-installed fetch works), same-origin credentials, feedback bodies |
| `lib/theme.test.ts` | no animation on first paint, rapid toggles, reduced motion, blocked storage |
| `e2e/chat.spec.ts` | production build in Chromium, desktop and phone viewports, API mocked |
| `tests/backend/unit/api/test_spa.py` | SPA fallback, assets, API 404s, missing build |
| `tests/deploy/test_frontend_compose.py` | merged dev/runtime configuration, public origin, Vite dependency, Linux modules, remote backend settings (Compose CLI only; no daemon) |

## Known gaps

- The stream does not return the stored assistant message ID, so feedback is only available on
  answers loaded from history.
- Bundle is ~684 kB (213 kB gzip) in one chunk.
- `node:24-alpine` build image is not pinned by digest (the Nginx image is).

Plans for each are in [roadmap.md](roadmap.md).
