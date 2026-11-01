import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { router as appRouter } from "@/router";
import { HttpResponse, http, lines, ndjsonResponse, server, streamUrl } from "@/test/server";

const CONVERSATION = "33333333-3333-4333-8333-333333333333";

function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({ routeTree: appRouter.routeTree, history: createMemoryHistory({ initialEntries: [path] }) });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("ChatPage", () => {
  it("streams an answer with status, citation, table and sources, then moves to the conversation URL", async () => {
    server.use(
      http.post(streamUrl, () =>
        ndjsonResponse(
          lines(
            { type: "status", stage: "understanding" },
            { type: "status", stage: "searching", source: "course_terms" },
            { type: "text", text: "CP264 requires CP164" },
            { type: "citation", source_nums: [1], urls: ["https://academic-calendar.wlu.ca/cp264"] },
            { type: "text", text: "." },
            { type: "table", title: "CP264 sections", columns: ["Section", "Days"], rows: [["A", "Mon/Wed"]] },
            { type: "sources", sources: [{ title: "CP264 Data Structures", url: "https://academic-calendar.wlu.ca/cp264" }] },
            { type: "ok" },
          ),
          { conversationId: CONVERSATION },
        ),
      ),
    );
    const user = userEvent.setup();
    const router = renderApp();

    const composer = await screen.findByLabelText(/ask about laurier/i);
    await user.type(composer, "Prereqs for CP264?{Enter}");

    expect(screen.getByText("Prereqs for CP264?")).toBeInTheDocument();
    // The shared route keeps the composer mounted while the URL gains the new conversation ID.
    await waitFor(() => expect(router.state.location.pathname).toBe(`/c/${CONVERSATION}`));
    expect(await screen.findByText("Answer ready.")).toBeInTheDocument();
    const answer = screen.getByRole("article", { name: /goldenguide answer/i });
    expect(within(answer).getByText(/CP264 requires CP164/)).toBeInTheDocument();
    expect(within(answer).getByRole("link", { name: /source 1/i })).toHaveAttribute("href", "https://academic-calendar.wlu.ca/cp264");
    expect(within(answer).getByRole("cell", { name: "Mon/Wed" })).toBeInTheDocument();
    expect(within(answer).getByRole("region", { name: "Sources" })).toHaveTextContent("CP264 Data Structures");
    expect(await screen.findByText("Answer ready.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/c/${CONVERSATION}`);
    expect(screen.getByLabelText(/ask about laurier/i)).toBe(composer);
    expect(composer).toHaveFocus();
    expect(within(answer).getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
  });

  it("marks an interrupted answer as incomplete and offers a retry", async () => {
    server.use(http.post(streamUrl, () => ndjsonResponse(lines({ type: "text", text: "Partial answer" }))));
    const user = userEvent.setup();
    renderApp();

    await user.type(await screen.findByLabelText(/ask about laurier/i), "q{Enter}");

    expect(await screen.findByText(/cut off before it finished/i)).toBeInTheDocument();
    expect(screen.getByText("Partial answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("returns to the centered new-chat state with a fresh draft and the same composer", async () => {
    server.use(http.post(streamUrl, () => ndjsonResponse(
      lines({ type: "text", text: "A completed answer" }, { type: "ok" }),
      { conversationId: CONVERSATION },
    )));
    const user = userEvent.setup();
    const router = renderApp();
    const composer = await screen.findByLabelText(/ask about laurier/i);
    await user.type(composer, "Question{Enter}");
    await screen.findByText("Answer ready.");
    await waitFor(() => expect(router.state.location.pathname).toBe(`/c/${CONVERSATION}`));
    await user.type(composer, "Unsent follow-up");
    await user.click(screen.getByRole("link", { name: "New chat" }));

    await screen.findByRole("heading", { name: "What can I help you find?" });
    expect(router.state.location.pathname).toBe("/");
    expect(screen.getByLabelText(/ask about laurier/i)).toBe(composer);
    expect(composer).toHaveValue("");
    expect(screen.queryByText("A completed answer")).not.toBeInTheDocument();
  });

  it("keeps a partial answer through navigation and marks a later connection drop as interrupted", async () => {
    const connection = new AbortController();
    const loadMessages = vi.fn(() => HttpResponse.json([]));
    server.use(
      http.post(streamUrl, () =>
        ndjsonResponse(lines({ type: "text", text: "Partial answer" }), {
          conversationId: CONVERSATION,
          disconnect: connection.signal,
        }),
      ),
      http.get(`*/api/v1/chat/conversations/${CONVERSATION}/messages`, loadMessages),
    );
    const user = userEvent.setup();
    const router = renderApp();

    await user.type(await screen.findByLabelText(/ask about laurier/i), "q{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe(`/c/${CONVERSATION}`));
    expect(await screen.findByText("Partial answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();

    // The provider must retain this live answer when the new conversation gets its URL.
    act(() => connection.abort());

    expect(await screen.findByText(/cut off before it finished/i)).toBeInTheDocument();
    expect(screen.getAllByText("Partial answer")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByText("Answer ready.")).not.toBeInTheDocument();
    expect(loadMessages).not.toHaveBeenCalled();
  });

  it("loads a stored conversation with feedback on its answers", async () => {
    server.use(
      http.get(`*/api/v1/chat/conversations/${CONVERSATION}/messages`, () =>
        HttpResponse.json([
          { id: 1, position: 1, role: "user", content: "Is CP264 offered in winter?", status: "complete", created_at: "2026-11-01T00:00:00Z" },
          { id: 2, position: 2, role: "assistant", content: "Yes, in **Winter 2027**.", status: "complete", created_at: "2026-11-01T00:00:01Z" },
        ]),
      ),
    );
    renderApp(`/c/${CONVERSATION}`);

    expect(await screen.findByText("Is CP264 offered in winter?")).toBeInTheDocument();
    expect(screen.getByText("Winter 2027")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Good answer" })).toBeInTheDocument();
  });

  it.each(["complete", "error", "interrupted"] as const)("restores saved evidence for a %s answer", async (status) => {
    server.use(http.get(`*/api/v1/chat/conversations/${CONVERSATION}/messages`, () => HttpResponse.json([{
      id: 2, position: 2, role: "assistant", content: "Memory-only fallback", status,
      created_at: "2026-11-01T00:00:01Z",
      answer_content: { version: 1, blocks: [
        { type: "text", text: "Saved sections" },
        { type: "citation", source_nums: [1], urls: ["https://loris.wlu.ca"] },
        { type: "table", title: "CP264 sections", columns: ["Section", "Days"], rows: [["A", "Mon/Wed"]] },
      ] },
      sources: [{ title: "LORIS registration", url: "https://loris.wlu.ca" }],
    }])));
    renderApp(`/c/${CONVERSATION}`);

    const answer = await screen.findByRole("article", { name: /goldenguide answer/i });
    expect(within(answer).getByText("Saved sections")).toBeInTheDocument();
    expect(within(answer).getByRole("link", { name: /source 1/i })).toHaveAttribute("href", "https://loris.wlu.ca");
    expect(within(answer).getByRole("cell", { name: "Mon/Wed" })).toBeInTheDocument();
    expect(within(answer).getByRole("region", { name: "Sources" })).toHaveTextContent("LORIS registration");
    expect(within(answer).getByRole("button", { name: "Good answer" })).toBeInTheDocument();
    expect(screen.queryByText("Memory-only fallback")).not.toBeInTheDocument();
    if (status === "error") expect(within(answer).getByText(/this answer failed/i)).toBeInTheDocument();
    if (status === "interrupted") expect(within(answer).getByText(/cut off before it finished/i)).toBeInTheDocument();
  });

  it("explains a conversation that does not exist on this device", async () => {
    server.use(
      http.get(`*/api/v1/chat/conversations/${CONVERSATION}/messages`, () =>
        HttpResponse.json({ error: { code: "not_found", message: "Conversation not found" } }, { status: 404 }),
      ),
    );
    renderApp(`/c/${CONVERSATION}`);

    expect(await screen.findByText(/doesn't exist on this device/i)).toBeInTheDocument();
  });

  it("sends thumbs-down feedback with a reason", async () => {
    const feedback: unknown[] = [];
    server.use(
      http.get(`*/api/v1/chat/conversations/${CONVERSATION}/messages`, () =>
        HttpResponse.json([{ id: 7, position: 2, role: "assistant", content: "Answer", status: "complete", created_at: "2026-11-01T00:00:00Z" }]),
      ),
      http.put("*/api/v1/chat/messages/7/feedback", async ({ request }) => {
        feedback.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp(`/c/${CONVERSATION}`);

    await user.click(await screen.findByRole("button", { name: "Bad answer" }));
    await user.click(screen.getByRole("button", { name: "Out of date" }));
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Thanks for the feedback.");
    expect(feedback).toEqual([{ rating: "down" }, { rating: "down", reason: "outdated", comment: null }]);
  });
});
