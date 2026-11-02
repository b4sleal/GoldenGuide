"""NDJSON streaming protocol for chat answers.

Wire format: one JSON object per line (application/x-ndjson). Event types:

    {"type": "status", "stage": ..., "source": ...}
                                             progress before the text (not terminal): stage is
                                             understanding | searching | writing; source (searching
                                             only) is courses | course_terms | wlu_pages | vector.
                                             Clients map these codes to wording.
    {"type": "text", "text": ...}            answer text, in order
    {"type": "citation", ...}                inline citation markers
    {"type": "sources", "sources": [...]}    source list for the answer: sent once, before the first
                                             text, so citations can show their sources while streaming
    {"type": "saved", "message_id": ...}     the complete answer was stored under this ID (used to
                                             rate it); sent just before "ok", omitted if history
                                             could not be saved
    {"type": "error", "error": {...}}        terminal: generation failed; same envelope as HTTP errors
    {"type": "ok"}                           terminal: the answer is complete

Contract for clients: an answer is complete ONLY if the last event is "ok". If the stream
ends with "error", show that message. If it ends with neither (connection dropped, server
killed, proxy timeout), treat the answer as interrupted.

Failure timing:
    - Before the first event: normal HTTP error status + JSON envelope, because we wait for the first
      event before starting the response (e.g. 404 for another browser's conversation, 429).
    - After the first event: HTTP 200 has already been sent, so we emit an "error" event instead.
      The chat's first event is the "understanding" status, sent at once so the student sees progress:
      retrieval, settings and LLM failures therefore arrive as an "error" event.
"""
import json
from collections.abc import AsyncGenerator

from fastapi import Request
from starlette.responses import StreamingResponse

from backend.api.errors import classify, error_body, report, request_id_of

# Terminal success marker. Kept as a constant so tests and clients agree on its exact form.
OK_EVENT = json.dumps({"type": "ok"}) + "\n"


def _line(event: dict) -> str:
    """Serialize one event as an NDJSON line."""
    return json.dumps(event) + "\n"


async def ndjson_stream(request: Request, events: AsyncGenerator[str, None]) -> StreamingResponse:
    """Wrap a generator of NDJSON lines with the start/ok/error rules described above."""
    # Step 1: wait for the first event before committing to HTTP 200.
    # Any exception raised here propagates to the normal handlers -> correct HTTP status.
    try:
        first = await anext(events)
    except StopAsyncIteration:
        # The chatbot always emits at least a "sources" event, so an empty stream is a bug.
        raise RuntimeError("Chat stream produced no events") from None

    async def body() -> AsyncGenerator[str, None]:
        try:
            # Step 2: forward the first event, then every remaining event as it arrives.
            yield first
            async for event in events:
                yield event
        except Exception as exc:  # Exception, not BaseException: client disconnects (cancellation) must propagate.
            # Step 3a: failure mid-stream. Log it once and tell the client in-band, then stop.
            # No "ok" follows, so the client knows the partial text is not a full answer.
            public = classify(exc)
            report(exc, public)
            yield _line({"type": "error", **error_body(public, request_id_of(request.scope))})
            return
        finally:
            # Always release the upstream generator (closes the LLM stream on disconnect or error).
            await events.aclose()

        # Step 3b: every event was delivered, so mark the answer complete.
        yield OK_EVENT

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={
            # Answers are per-request; never let a browser or proxy cache them.
            "Cache-Control": "no-store",
            # Tell NGINX not to buffer, otherwise tokens arrive in large bursts instead of streaming.
            "X-Accel-Buffering": "no",
        },
    )
