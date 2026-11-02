import { describe, expect, it } from "vitest";

import { type Answer, applyEvent, endWithoutTerminal, pendingAnswer } from "./answer";
import { CITATION_TITLE } from "./citations";
import type { StreamEvent } from "./events";

const apply = (...events: StreamEvent[]): Answer => events.reduce(applyEvent, pendingAnswer);
const error = { code: "provider_failed", message: "The answer service failed.", request_id: "req-1" };

describe("answer", () => {
  it("is complete only after ok", () => {
    const streaming = apply({ type: "text", text: "Hi" });
    expect(streaming.phase).toBe("streaming");
    expect(applyEvent(streaming, { type: "ok" }).phase).toBe("complete");
  });

  it("keeps the latest status until text arrives", () => {
    const answer = apply(
      { type: "status", stage: "understanding" },
      { type: "status", stage: "searching", source: "course_terms" },
    );
    expect(answer.phase).toBe("pending");
    expect(answer.status).toEqual({ stage: "searching", source: "course_terms" });
  });

  it("keeps partial text when the stream ends with error", () => {
    const answer = apply({ type: "text", text: "Partial" }, { type: "error", error });
    expect(answer.phase).toBe("error");
    expect(answer.error).toEqual(error);
    expect(answer.blocks).toEqual([{ kind: "markdown", markdown: "Partial" }]);
  });

  it("is interrupted when the stream ends without ok or error", () => {
    expect(endWithoutTerminal(apply({ type: "text", text: "Partial" }), false).phase).toBe("interrupted");
  });

  it("is stopped when the student aborts", () => {
    expect(endWithoutTerminal(apply({ type: "text", text: "Partial" }), true).phase).toBe("stopped");
  });

  it("does not change after a terminal event", () => {
    const done = apply({ type: "ok" });
    expect(applyEvent(done, { type: "text", text: "late" })).toBe(done);
    expect(endWithoutTerminal(done, false)).toBe(done);
  });

  it("inlines each citation as one marked link carrying all its source numbers", () => {
    const answer = apply(
      { type: "text", text: "Needs CP164" },
      { type: "citation", source_nums: [1, 2], urls: ["https://wlu.ca/a", null] },
      { type: "text", text: "." },
    );
    expect(answer.blocks).toEqual([
      { kind: "markdown", markdown: `Needs CP164[1,2](#gg-cite-1-2 "${CITATION_TITLE}").` },
    ]);
  });

  it("places tables between text blocks, in stream order", () => {
    const table = { title: "Sections", columns: ["Section"], rows: [["A"]] };
    const answer = apply({ type: "text", text: "Before" }, { type: "table", ...table }, { type: "text", text: "After" });
    expect(answer.blocks).toEqual([
      { kind: "markdown", markdown: "Before" },
      { kind: "table", table },
      { kind: "markdown", markdown: "After" },
    ]);
  });

  it("records sources", () => {
    const sources = [{ title: "CP264", url: "https://wlu.ca/cp264", source_type: "course" }];
    expect(apply({ type: "sources", sources }).sources).toEqual(sources);
  });
});
