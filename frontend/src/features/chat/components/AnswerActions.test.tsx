import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AnswerBlock } from "../stream/answer";
import { AnswerActions } from "./AnswerActions";

const blocks: AnswerBlock[] = [{ kind: "markdown", markdown: "CP264 requires **CP164**." }];
afterEach(() => vi.restoreAllMocks());

describe("AnswerActions", () => {
  it("copies a live answer without requiring a saved message ID", async () => {
    const user = userEvent.setup();
    const write = vi.spyOn(navigator.clipboard, "writeText");
    render(<AnswerActions blocks={blocks} sources={[]} />);

    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(write).toHaveBeenCalledWith("CP264 requires **CP164**.");
    expect(await screen.findByRole("status")).toHaveTextContent("Copied");
    expect(screen.queryByRole("button", { name: "Good answer" })).not.toBeInTheDocument();
  });

  it("reports denied clipboard access and lets the student try again", async () => {
    const user = userEvent.setup();
    const write = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"));
    render(<AnswerActions blocks={blocks} sources={[]} />);

    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Could not copy");
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(write).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("status")).toHaveTextContent("Copied");
  });

  it("places Copy beside the existing feedback buttons for a stored answer", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AnswerActions blocks={blocks} sources={[]} messageId={7} />
      </QueryClientProvider>,
    );
    expect(screen.getAllByRole("button").map((button) => button.getAttribute("aria-label")))
      .toEqual(["Good answer", "Bad answer", "Copy answer"]);
  });

  it("does not offer Copy when there is no answer content", () => {
    render(<AnswerActions blocks={[]} sources={[]} />);
    expect(screen.queryByRole("button", { name: "Copy answer" })).not.toBeInTheDocument();
  });
});
