import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { CONVERSATION_HEADER, STREAM_PATH } from "@/features/chat/stream/streamChat";

/** Mock API for component and hook tests. Tests override handlers with `server.use(...)`. */
export const server = setupServer(
  http.get("*/api/v1/chat/conversations", () => HttpResponse.json([])),
);

const encoder = new TextEncoder();

/**
 * An NDJSON stream response built from raw chunks, so tests control exactly where the network splits
 * lines. A separate disconnect signal lets tests drop the connection after observing partial text.
 */
export function ndjsonResponse(
  chunks: string[],
  {
    conversationId = "11111111-1111-4111-8111-111111111111",
    disconnect,
  }: { conversationId?: string; disconnect?: AbortSignal } = {},
) {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (disconnect) {
        // Erroring in start() discards queued bytes. Wait for the test to confirm delivery first.
        // This is independent of the request's abort signal, which represents the student's Stop.
        const drop = () => controller.error(new TypeError("network error"));
        if (disconnect.aborted) drop();
        else disconnect.addEventListener("abort", drop, { once: true });
      } else controller.close();
    },
  });
  return new HttpResponse(body, {
    headers: { "Content-Type": "application/x-ndjson", [CONVERSATION_HEADER]: conversationId },
  });
}

/** One NDJSON line per event. */
export function lines(...events: object[]): string[] {
  return events.map((event) => `${JSON.stringify(event)}\n`);
}

export const streamUrl = `*${STREAM_PATH}`;
export { http, HttpResponse };
