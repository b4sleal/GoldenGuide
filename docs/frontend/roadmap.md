# Frontend Roadmap

**For:** developers, reviewers. What is planned for the web client, what is still open, and the dated
log of decisions. What is built: [architecture.md](architecture.md) and [ux.md](ux.md). Keep superseded
choices in the log instead of deleting them.

## Committed

0. **Inline sources and citation support** (phase 1 built 2026-11-02; phase 2 next): Gemini-style inline chips with a
   hover card (site, title, snippet), sentence-level highlighting backed by reranker support scores,
   and a bottom list linked to the chips. Plan: [source-citations-plan.md](plans/source-citations-plan.md).
1. **Evidence panel.** Clicking a citation opens the source in a right-hand panel (full screen with a
   back button on phones): the WLU page, the cited excerpt, an **Academic Calendar vs LORIS** badge,
   the effective term, and an "open on wlu.ca" link.
   - Rendering: try an `<iframe>` of the official page. As of 2026-10-31, `academic-calendar.wlu.ca` and
     `www.wlu.ca` send no `X-Frame-Options` / `frame-ancestors` header, so embedding works today, but WLU
     can change that at any time.
   - Fallback (required): render the stored scraped content for that page with the cited passage
     highlighted. This is also the only way to highlight the excerpt, since a cross-origin iframe
     cannot be scripted. Needs an evidence content endpoint.
   - CSP `frame-src` limited to WLU hosts; the iframe gets `sandbox` + `referrerpolicy`.
2. **Prerequisite graph** (React Flow). Interactive graph of a course's prerequisite chain from
   `CourseTerm` data; click a node to see that course. Term-aware: prerequisites can differ by offering.
3. **Distinct outcome states.** "No records found", "not supported", "provider failed" and "retrieval
   incomplete" each look different, with their own wording and action. Never shown as "doesn't exist".
4. **Feedback on live answers.** Return the stored assistant message ID in the stream (e.g. on `ok`)
   so thumbs up/down work without reloading the conversation.

## Likely (after the committed items)

5. **Structured answer cards.** Course card (code, credits, prerequisites, terms) beside the text. Needs a
   new structured stream event (backend contract change).
6. **Term context chip.** Shows the term the resolver chose ("Winter 2027 ▾"); the student can change it.
7. **Carried context display.** Show what the conversation remembers ("Talking about CP264, Winter 2027").
8. **Weekly schedule preview.** Sections on a calendar grid with conflict detection.
9. **Admin dashboard** (admin role): ingestion jobs, partial failures, links to traces.

## Baseline polish

Built: streaming caret, Stop, retry, copy, suggested questions, mobile drawer.
Still to do: regenerate, edit last message, `Ctrl+K` chat search, conversation rename, keyboard
shortcuts.

## Engineering

- Code-split the bundle (~684 kB, 213 kB gzip, one chunk) when the evidence panel and graph land.
- Pin the `node:24-alpine` build image by digest (the Nginx image already is).
- Track time to first status (target < 300 ms), time to first token and total time.

## Open questions

- **Signed-in users:** conversations are owned by an anonymous device cookie today. How history moves
  to an account after sign-in, and whether signed-out use stays allowed.
- **Retention:** how long conversations are kept (students may mention grades); the retention job is
  deferred.
- **Memory limits:** token budget and how much history follow-up resolution receives.
- **Stream versioning:** how additive events (structured cards) are versioned.
- **Evidence content endpoint:** API shape for stored page content plus the cited span.

## Decision log

- **2026-11-02:** One highlight at a time: hovering a chip highlights nothing; a source in its card
  highlights the citation's text; a source in the bottom list highlights only the chips citing it.
  The first version (chip hover lit text and bottom-list entries; bottom-list hover lit text too) was
  too busy to read.
- **2026-11-02:** Sources move to Gemini-style inline chips with a hover card; inline numbers go away
  and repeated citations keep their chips. The bottom list stays, unnumbered, and highlights the chips
  that cite a hovered source. Highlights are sentence-level: the model's citations set segments and
  candidate sources, then the cross-encoder reranker decides which sentences each source supports
  (structured records skip scoring and keep the whole segment). Model-marked spans were rejected as a
  fragile streaming format that would still need checking. Plan: [source-citations-plan.md](plans/source-citations-plan.md).
- **2026-11-01:** Frontend docs split into architecture (built), ux (interaction design) and this
  roadmap; the planning notebook `decisions.md` was retired.
- **2026-11-01:** Sources use one horizontally scrollable row with hidden scrollbars, native touch
  scrolling, mouse dragging and keyboard/arrow navigation. Registration references are consolidated
  in backend context preparation before citation IDs are assigned; every LORIS section still supplies
  evidence/table data, but the model, stream and saved sources share one "LORIS - Registration" link.
  Older history responses remap sources and citation IDs together without rewriting stored rows.
  The frontend preserves the backend's source order and numbering and performs no source merging.
- **2026-11-01:** The new-chat composer starts centered and moves to the bottom using CSS grid
  track interpolation (550 ms). A shared chat route keeps the input mounted through the first
  conversation URL change. Source-specific progress includes decorative dots. Answer actions
  copy editable Markdown, tab-separated table data and source links; rating still needs a saved
  message ID. Theme changes apply immediately, including buttons: per-element color transitions
  were removed after causing lag in populated chats. Composer and loading animations respect
  the system's reduced-motion preference.
- **2026-11-01:** Persist versioned answer snapshots in `chat_messages.answer_content` (migration
  `0004`), after stream post-processing. Sources retain their original numbering. History and live
  answers share renderers; `content` remains unchanged for follow-up memory and older clients.
- **2026-11-01:** Docker development runs `frontend-vite` behind Nginx on the existing public
  frontend port, including the HMR WebSocket. API/auth routing preserves the original Host/Origin.
  The old HTML client was removed; runtime still builds the React app into the Nginx image.
- **2026-11-01:** Backend for the frontend built: conversation storage (anonymous `gg_client` device
  cookie), follow-up memory (recent turns + carried entities), list/messages/delete/feedback
  endpoints, `status` events. See `docs/backend/chat-pipeline.md` §7. Retention job deferred.
- **2026-11-01:** First frontend slice: `frontend/` at repo root, pnpm. Code-based TanStack Router
  routes (`/`, `/c/$conversationId`); live chat state lives above the routes so the first answer keeps
  streaming when the URL gains the new conversation ID. Database tables (`table` events) render from
  data, never as Markdown. History delete is two-click (arm, confirm).
- **2026-10-31:** Conversation memory uses our own PostgreSQL storage with structured carried state,
  provider-neutral. Rejected: provider-managed sessions (vendor lock-in, conflicts with the LLM
  fallback chain, student data held by a third party) and browser-only history (lost across devices,
  untrusted). History is resent each turn; provider context caching lowers the cost through a stable
  prompt prefix. Earlier answers are never evidence: follow-ups re-run retrieval.
- **2026-10-31:** Status messages name the actual source from the query plan; the backend sends codes,
  the frontend owns wording.
- **2026-10-31:** Evidence panel (iframe + stored-content fallback, full screen on phone), prerequisite
  graph and distinct outcome states committed. Loading sequence based on real backend stages.
- **2026-10-31:** React + TS + Vite SPA, same origin as FastAPI; Next.js and Vercel AI SDK rejected
  (see [architecture.md](architecture.md#why-this-stack)).
