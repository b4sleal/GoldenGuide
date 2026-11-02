# Frontend Interaction Design

**For:** developers, designers, reviewers. How the web client looks and behaves for a student, as built
(2026-11-01). How it is implemented: [architecture.md](architecture.md). What comes next:
[roadmap.md](roadmap.md).

## Goals

- A familiar AI-chat layout: conversation in the centre, chat history on the left.
- Every answer visibly grounded in official WLU sources: the product's main differentiator.
- Fast and polished: it should *feel* instant even while retrieval and generation run.
- Clean, typed, tested code a WLU engineer could maintain.

## Layout

- **Desktop:** history sidebar (new chat, conversation list) and the chat in the centre.
- **Phone (< `md`):** the sidebar becomes a drawer (Radix dialog).
- **New chat:** the composer starts centred with suggested questions and moves to the bottom when the
  first question is sent (CSS grid track interpolation, 550 ms). The same input stays mounted through
  the first URL change, so a draft is never lost.
- **Themes:** light and dark, system default, the choice remembered in the browser. Theme changes
  apply immediately; per-element colour transitions were removed because they lagged in long chats.

## Loading and perceived performance

Principle: something on screen always reflects **real progress**. No fake progress bars.

Response-time thresholds (Nielsen Norman Group, "Response Times: The 3 Important Limits"):
under **0.1 s** feels instant; under **1 s** keeps flow; past **~10 s** users lose attention.

| Moment | What the student sees |
|---|---|
| Send pressed (0 ms) | Question appears immediately; input clears; the answer area shows a progress label. |
| Before first token | The backend's current stage ("Searching LORIS registration…") with decorative dots. |
| First token | Progress swaps to streaming text with a caret; the source list arrives before the text, so citation chips show their titles as they stream in. |
| > 10 s (`SLOW_ANSWER_MS`) | "Still working, checking more sources…"; Stop stays available. |

### Status messages

The backend sends `status` events with **codes only**; the frontend owns the wording, all in
`frontend/src/features/chat/labels.ts`. Each status is real progress taken from the validated query
plan, sent once per source, never guessed from the question text.

| Event | Student sees |
|---|---|
| (sent, nothing received yet) | "Sending…" |
| `stage: understanding` | "Understanding your question…" |
| `stage: searching`, `source: courses` | "Searching Academic Calendar courses…" |
| `stage: searching`, `source: course_terms` | "Searching LORIS registration…" |
| `stage: searching`, `source: wlu_pages` | "Searching Academic Calendar programs…" |
| `stage: searching`, `source: vector` | "Searching WLU pages…" |
| `stage: writing` | "Writing answer…" |

## Answers

- **Citations** are inline chips after the text they support: the first source's title, plus "+N" when
  a citation names several; there are no `[1]` numbers. Hovering a chip (a click, tap or Enter on
  touch and keyboard) opens a card under it with each cited source's site, title and a two-line preview;
  it fits about two entries and scrolls the rest, stays open while the pointer moves into it, and
  Escape closes it. Only one card is open at a time: opening another chip's card, even by hovering,
  closes one that was pinned by a click. Entries open the source in a new tab. Hovering the chip highlights nothing;
  hovering a source in its card highlights the text the citation covers (since the previous citation,
  within the same paragraph or list item).
- **Tables** of database records (sections, meetings, seats) render from data in a scrollable,
  keyboard-focusable region; wide tables scroll instead of squeezing cells.
- **Sources** sit in one horizontally scrollable row: native touch scrolling, mouse dragging, arrow
  buttons only when the row overflows. The frontend keeps the backend's order and never merges sources
  itself. Entries are not numbered; hovering or focusing one highlights the chips that cite it (not their
  text). Chips never highlight entries in the row: one highlight at a time keeps the answer calm.
- **Copy** puts editable Markdown (without citation chips), tab-separated table data and a plain list
  of source links on the clipboard.
- **Feedback** (thumbs up/down, with a reason for thumbs down) is offered on every completed answer,
  as soon as the stream reports its stored message ID (`saved` event), and on answers loaded from
  history. A live answer that failed or was cut off gets it after a reload. If history could not
  be saved, the answer has no ID and only Copy is shown.

## Unfinished answers

An answer is complete only when the stream ends with `ok`. Anything else is shown as incomplete,
keeping any partial text, never as a confident answer:

| Ending | Student sees |
|---|---|
| `error` event or HTTP error | The server's message, a reference ID and Retry |
| Stream ended with no terminal event | "The answer was cut off before it finished. This is not a complete answer." + Retry |
| Stop pressed | "You stopped this answer. It may be incomplete." + Retry |
| Stored answer that failed or was cut off | A matching "may be incomplete" notice in history |

## Accessibility

Target: WCAG 2.2 AA.

- Keyboard: skip link, visible focus rings, Enter sends / Shift+Enter new line, Stop button, focusable
  table and source regions.
- Screen readers: the progress label is `role="status"`; completion ("Answer ready.") is announced
  once, not on every token.
- Motion: 150–250 ms, `opacity`/`transform` only; all animation disabled under
  `prefers-reduced-motion`.
- History delete takes two clicks (arm, confirm); the delete button is always visible on touch screens.
