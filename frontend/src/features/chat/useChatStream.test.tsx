import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HttpResponse, http, lines, ndjsonResponse, server, streamUrl } from "@/test/server";

import { useChatStream } from "./useChatStream";

const CONVERSATION = "22222222-2222-4222-8222-222222222222";

function setup() {
  const onConversationCreated = vi.fn();
  const onTurnSettled = vi.fn();
  const hook = renderHook(() => useChatStream({ onConversationCreated, onTurnSettled }));
  const answer = () => hook.result.current.turns.at(-1)!.answer;
  const settled = () => waitFor(() => expect(onTurnSettled).toHaveBeenCalled());
  return { hook, answer, settled, onConversationCreated, onTurnSettled };
}

describe("useChatStream", () => {
  it("completes an answer that ends with ok and reports the new conversation", async () => {
    server.use(
      http.post(streamUrl, () =>
        ndjsonResponse(
          lines(
            { type: "status", stage: "understanding" },
            { type: "text", text: "CP264 needs CP164." },
            { type: "sources", sources: [{ title: "CP264", url: "https://wlu.ca/cp264" }] },
            { type: "ok" },
          ),
          { conversationId: CONVERSATION },
        ),
      ),
    );
    const { hook, answer, settled, onConversationCreated } = setup();

    act(() => hook.result.current.send("  Prereqs for CP264?  "));
    expect(hook.result.current.turns[0]!.question).toBe("Prereqs for CP264?");
    expect(answer().phase).toBe("pending");
    await settled();

    expect(answer().phase).toBe("complete");
    expect(answer().sources).toHaveLength(1);
    expect(hook.result.current.conversationId).toBe(CONVERSATION);
    expect(hook.result.current.startedHere).toBe(true);
    expect(onConversationCreated).toHaveBeenCalledWith(CONVERSATION);
    expect(hook.result.current.isStreaming).toBe(false);
  });

  it("sends the conversation ID with the next question", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(streamUrl, async ({ request }) => {
        bodies.push(await request.json());
        return ndjsonResponse(lines({ type: "ok" }), { conversationId: CONVERSATION });
      }),
    );
    const { hook, onTurnSettled } = setup();

    act(() => hook.result.current.send("first"));
    await waitFor(() => expect(onTurnSettled).toHaveBeenCalledTimes(1));
    act(() => hook.result.current.send("second"));
    await waitFor(() => expect(onTurnSettled).toHaveBeenCalledTimes(2));

    expect(bodies).toEqual([
      { query: "first", conversation_id: null },
      { query: "second", conversation_id: CONVERSATION },
    ]);
  });

  it("shows the server error and keeps partial text when the stream ends with error", async () => {
    const error = { code: "provider_failed", message: "The answer service is unavailable.", request_id: "req-9" };
    server.use(http.post(streamUrl, () => ndjsonResponse(lines({ type: "text", text: "Partial" }, { type: "error", error }))));
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();

    expect(answer().phase).toBe("error");
    expect(answer().error).toEqual(error);
    expect(answer().blocks).toEqual([{ kind: "markdown", markdown: "Partial" }]);
  });

  it("is interrupted when the stream closes without a terminal event", async () => {
    server.use(http.post(streamUrl, () => ndjsonResponse(lines({ type: "text", text: "Partial" }))));
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();

    expect(answer().phase).toBe("interrupted");
  });

  it("is interrupted when the connection drops mid-stream", async () => {
    const connection = new AbortController();
    server.use(http.post(streamUrl, () => ndjsonResponse(lines({ type: "text", text: "Partial" }), { disconnect: connection.signal })));
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    // Establish that the stream started before simulating a network failure, without a timer.
    await waitFor(() => expect(answer().blocks).toEqual([{ kind: "markdown", markdown: "Partial" }]));
    expect(answer().phase).toBe("streaming");
    act(() => connection.abort());
    await settled();

    expect(answer().phase).toBe("interrupted");
    expect(answer().blocks).toEqual([{ kind: "markdown", markdown: "Partial" }]);
    expect(answer().error).toBeNull();
    expect(hook.result.current.isStreaming).toBe(false);
  });

  it("reports a connection failure before the response as a network error", async () => {
    server.use(http.post(streamUrl, () => HttpResponse.error()));
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();

    // A request that never reached a stream is distinct from an interrupted partial answer.
    expect(answer().phase).toBe("error");
    expect(answer().error?.code).toBe("network_error");
    expect(answer().blocks).toEqual([]);
  });

  it("is stopped when the student aborts", async () => {
    // A response that never sends anything until aborted.
    server.use(
      http.post(streamUrl, ({ request }) => {
        const body = new ReadableStream({
          start(controller) {
            request.signal.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")));
          },
        });
        return new HttpResponse(body, { headers: { "Content-Type": "application/x-ndjson" } });
      }),
    );
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await waitFor(() => expect(hook.result.current.isStreaming).toBe(true));
    act(() => hook.result.current.stop());
    await settled();

    expect(answer().phase).toBe("stopped");
  });

  it("shows the HTTP error envelope for a failure before the stream starts", async () => {
    server.use(
      http.post(streamUrl, () =>
        HttpResponse.json({ error: { code: "rate_limited", message: "Too many questions. Wait a minute.", request_id: "req-1" } }, { status: 429 }),
      ),
    );
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();

    expect(answer().phase).toBe("error");
    expect(answer().error?.code).toBe("rate_limited");
  });

  it("reports an unreadable stream as an error, not as an answer", async () => {
    server.use(http.post(streamUrl, () => ndjsonResponse(['{"type": "text", "text": 1}\n'])));
    const { hook, answer, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();

    expect(answer().phase).toBe("error");
    expect(answer().error?.code).toBe("unexpected_response");
  });

  it("retries the last question in place", async () => {
    let calls = 0;
    server.use(
      http.post(streamUrl, () => {
        calls += 1;
        return ndjsonResponse(lines(calls === 1 ? { type: "text", text: "cut" } : { type: "ok" }));
      }),
    );
    const { hook, answer, onTurnSettled } = setup();

    act(() => hook.result.current.send("q"));
    await waitFor(() => expect(onTurnSettled).toHaveBeenCalledTimes(1));
    expect(answer().phase).toBe("interrupted");

    act(() => hook.result.current.retry(hook.result.current.turns[0]!.id));
    await waitFor(() => expect(onTurnSettled).toHaveBeenCalledTimes(2));

    expect(hook.result.current.turns).toHaveLength(1);
    expect(answer().phase).toBe("complete");
  });

  it("clears live turns when switching conversation", async () => {
    server.use(http.post(streamUrl, () => ndjsonResponse(lines({ type: "ok" }))));
    const { hook, settled } = setup();

    act(() => hook.result.current.send("q"));
    await settled();
    act(() => hook.result.current.reset(CONVERSATION));

    expect(hook.result.current.turns).toEqual([]);
    expect(hook.result.current.conversationId).toBe(CONVERSATION);
    expect(hook.result.current.startedHere).toBe(false);
  });
});
