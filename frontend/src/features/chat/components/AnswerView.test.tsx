import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { pendingAnswer } from "../stream/answer";
import { AnswerView } from "./AnswerView";

describe("AnswerView progress", () => {
  it("shows source-specific progress with decorative dots, then removes it when content arrives", () => {
    const answer = { ...pendingAnswer, status: { stage: "searching" as const, source: "courses" as const } };
    const { rerender } = render(<AnswerView answer={answer} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Searching Academic Calendar courses");
    expect(status.querySelector('[aria-hidden="true"]')?.children).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Copy answer" })).not.toBeInTheDocument();

    const blocks = [{ kind: "markdown" as const, markdown: "A partial answer" }];
    rerender(<AnswerView answer={{ ...answer, phase: "streaming", blocks }} />);
    expect(screen.queryByText(/Searching Academic Calendar courses/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy answer" })).not.toBeInTheDocument();

    rerender(<AnswerView answer={{ ...answer, phase: "interrupted", blocks }} />);
    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
    expect(screen.getByText(/cut off before it finished/)).toBeInTheDocument();
    expect(screen.queryByText("Answer ready.")).not.toBeInTheDocument();
  });
});
