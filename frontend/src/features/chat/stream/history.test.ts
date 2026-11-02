import { describe, expect, it } from "vitest";

import { storedAnswerContent } from "./history";

describe("stored answer content", () => {
  it("restores ordered text, citation links, tables and the original source numbering", () => {
    const table = { title: "Sections", columns: ["Section"], rows: [["A"], ["B"]] };
    const sources = [{ title: "CP264", url: "https://wlu.ca/cp264" }, { title: "LORIS", url: "https://loris.wlu.ca" }];
    const answer = storedAnswerContent({
      content: "Plain text retained for memory",
      answer_content: { version: 1, blocks: [
        { type: "text", text: "Sections" },
        { type: "citation", source_nums: [2], urls: ["https://loris.wlu.ca"] },
        { type: "table", ...table },
        { type: "text", text: "Check availability." },
      ] },
      sources,
    });

    expect(answer.blocks).toEqual([
      { kind: "markdown", markdown: 'Sections[2](#gg-cite-2 "gg-citation")' },
      { kind: "table", table },
      { kind: "markdown", markdown: "Check availability." },
    ]);
    expect(answer.sources).toEqual(sources);
  });

  it("keeps text-only history from an older backend readable", () => {
    expect(storedAnswerContent({ content: "Old **answer**" })).toEqual({
      blocks: [{ kind: "markdown", markdown: "Old **answer**" }], sources: [],
    });
  });

  it("does not duplicate fallback text when a saved table is the whole answer", () => {
    expect(storedAnswerContent({ content: "fallback", answer_content: { version: 1, blocks: [
      { type: "table", title: "Sections", columns: ["Section"], rows: [["A"]] },
    ] } }).blocks).toEqual([
      { kind: "table", table: { title: "Sections", columns: ["Section"], rows: [["A"]] } },
    ]);
  });
});
