import { describe, expect, it } from "vitest";

import { answerClipboardText } from "./clipboard";
import { type AnswerBlock } from "./stream/answer";
import { citationMarkdown } from "./stream/citations";

describe("answerClipboardText", () => {
  it("preserves ordered prose, table values and source URLs without citation markup", () => {
    const blocks: AnswerBlock[] = [
      { kind: "markdown", markdown: `Requires **CP164** ${citationMarkdown([1])}` },
      { kind: "table", table: {
        title: "Sections", columns: ["Section", "Meetings"], rows: [["A | <lab>", "Monday\nWednesday"], ["B", "Friday"]],
      } },
      { kind: "markdown", markdown: "Check availability." },
    ];
    expect(answerClipboardText(blocks, [{ title: "LORIS", url: "https://loris.wlu.ca" }])).toBe([
      "Requires **CP164**",
      'Sections\nSection\tMeetings\nA | <lab>\t"Monday\nWednesday"\nB\tFriday',
      "Check availability.",
      "Sources\n- LORIS: https://loris.wlu.ca",
    ].join("\n\n"));
  });

  it("handles empty answers and sources without URLs", () => {
    expect(answerClipboardText([], [])).toBe("");
    expect(answerClipboardText([{ kind: "markdown", markdown: "Answer" }], [{ title: "Calendar", url: null }]))
      .toBe("Answer\n\nSources\n- Calendar");
  });
});
