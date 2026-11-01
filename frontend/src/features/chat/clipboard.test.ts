import { describe, expect, it } from "vitest";

import { answerClipboardText } from "./clipboard";
import { type AnswerBlock, CITATION_TITLE } from "./stream/answer";

describe("answerClipboardText", () => {
  it("preserves ordered prose, table values and source URLs without private citation hints", () => {
    const blocks: AnswerBlock[] = [
      { kind: "markdown", markdown: `Requires **CP164** [1](https://wlu.ca/cp264 "${CITATION_TITLE}")` },
      { kind: "table", table: {
        title: "Sections", columns: ["Section", "Meetings"], rows: [["A | <lab>", "Monday\nWednesday"], ["B", "Friday"]],
      } },
      { kind: "markdown", markdown: "Check availability." },
    ];
    expect(answerClipboardText(blocks, [{ title: "LORIS", url: "https://loris.wlu.ca" }])).toBe([
      "Requires **CP164** [1](https://wlu.ca/cp264)",
      'Sections\nSection\tMeetings\nA | <lab>\t"Monday\nWednesday"\nB\tFriday',
      "Check availability.",
      "Sources\n[1] LORIS: https://loris.wlu.ca",
    ].join("\n\n"));
  });

  it("handles empty answers and sources without URLs", () => {
    expect(answerClipboardText([], [])).toBe("");
    expect(answerClipboardText([{ kind: "markdown", markdown: "Answer" }], [{ title: "Calendar", url: null }]))
      .toBe("Answer\n\nSources\n[1] Calendar");
  });
});
