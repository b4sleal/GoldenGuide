import { apiUrl, NETWORK_ERROR, toApiError } from "@/api/client";
import type { Schemas } from "@/api/client";

import type { ApiErrorBody, StreamEvent } from "./events";
import { readNdjson, StreamProtocolError } from "./ndjson";

const PROTOCOL_ERROR: ApiErrorBody = {
  code: "unexpected_response",
  message: "GoldenGuide sent an answer this page could not read. Refresh the page and try again.",
};

export const STREAM_PATH = "/api/v1/chat/stream";
/** Response header naming the stored conversation; sent back to continue it. */
export const CONVERSATION_HEADER = "X-Conversation-Id";

export interface StreamHandlers {
  onConversation: (conversationId: string) => void;
  onEvent: (event: StreamEvent) => void;
}

/** How the request ended, as far as the transport can tell. Answer phases are derived from events. */
export type StreamEnd =
  | { kind: "ended" } // body closed; whether it was complete depends on the last event
  | { kind: "aborted" }
  | { kind: "failed"; error: ApiErrorBody }; // before the stream started, or unreadable mid-stream

/**
 * POST a question and deliver each stream event in order. Never throws: every way the request can
 * end is returned, so the caller can map it to exactly one answer state.
 */
export async function streamChat(
  request: Schemas["ChatRequest"],
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<StreamEnd> {
  let response: Response;
  try {
    response = await fetch(apiUrl(STREAM_PATH), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify(request),
      credentials: "same-origin",
      signal,
    });
  } catch {
    return signal.aborted ? { kind: "aborted" } : { kind: "failed", error: NETWORK_ERROR };
  }

  try {
    // Failures before the first event are ordinary HTTP errors with the JSON envelope (404, 422, 429...).
    if (!response.ok || !response.body) {
      const body: unknown = await response.json().catch(() => null);
      return { kind: "failed", error: toApiError(response.status, body).body };
    }

    const conversationId = response.headers.get(CONVERSATION_HEADER);
    if (conversationId) handlers.onConversation(conversationId);

    for await (const event of readNdjson(response.body)) handlers.onEvent(event);
    return { kind: "ended" };
  } catch (error) {
    if (signal.aborted) return { kind: "aborted" };
    if (error instanceof StreamProtocolError) {
      console.error("Chat stream contract violation", error.line, error.cause);
      return { kind: "failed", error: PROTOCOL_ERROR };
    }
    // The connection dropped mid-stream. With no terminal event the answer is "interrupted".
    return { kind: "ended" };
  }
}
