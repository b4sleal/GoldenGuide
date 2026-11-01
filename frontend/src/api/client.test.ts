import { afterEach, describe, expect, it, vi } from "vitest";

import { api, unwrap } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("API client transport", () => {
  it("uses fetch installed after the client was imported and preserves same-origin credentials", async () => {
    // The singleton above already exists when a test server installs its fetch interceptor.
    const interceptedFetch = vi.fn(async (_request: Request) => Response.json([]));
    vi.stubGlobal("fetch", interceptedFetch);

    expect(unwrap(await api.GET("/api/v1/chat/conversations"))).toEqual([]);

    expect(interceptedFetch).toHaveBeenCalledTimes(1);
    const request = interceptedFetch.mock.calls[0]![0];
    expect(request).toBeInstanceOf(Request);
    expect(request.url).toBe(new URL("/api/v1/chat/conversations", window.location.origin).href);
    expect(request.credentials).toBe("same-origin");
  });

  it("uses the current fetch for later requests and preserves feedback bodies", async () => {
    const firstFetch = vi.fn(async (_request: Request) => Response.json([]));
    vi.stubGlobal("fetch", firstFetch);
    await api.GET("/api/v1/chat/conversations");

    const replacementFetch = vi.fn(async (_request: Request) => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", replacementFetch);
    const feedback = { rating: "down" as const, reason: "outdated" as const, comment: null };
    await api.PUT("/api/v1/chat/messages/{message_id}/feedback", {
      params: { path: { message_id: 7 } },
      body: feedback,
    });

    expect(firstFetch).toHaveBeenCalledTimes(1);
    expect(replacementFetch).toHaveBeenCalledTimes(1);
    const request = replacementFetch.mock.calls[0]![0];
    expect(request.method).toBe("PUT");
    expect(new URL(request.url).pathname).toBe("/api/v1/chat/messages/7/feedback");
    expect(request.headers.get("Content-Type")).toBe("application/json");
    expect(await request.json()).toEqual(feedback);
  });
});
