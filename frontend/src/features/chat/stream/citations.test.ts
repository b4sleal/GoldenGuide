import { describe, expect, it } from "vitest";

import { CITATION_TITLE, citationMarkdown, parseCitationHref, stripCitations } from "./citations";

describe("citation links", () => {
  it("encode one link per citation, with every source number in the href", () => {
    expect(citationMarkdown([1, 2])).toBe(`[1,2](#gg-cite-1-2 "${CITATION_TITLE}")`);
  });

  it("read the source numbers back and ignore any other link", () => {
    expect(parseCitationHref("#gg-cite-3-12")).toEqual([3, 12]);
    expect(parseCitationHref("https://www.wlu.ca")).toEqual([]);
    expect(parseCitationHref("#gg-cite-x-0")).toEqual([]);
    expect(parseCitationHref(undefined)).toEqual([]);
  });

  it("are stripped from copied text together with the space before them", () => {
    const text = `Requires CP164 ${citationMarkdown([1])}. Also CP104${citationMarkdown([2, 3])}.`;
    expect(stripCitations(text)).toBe("Requires CP164. Also CP104.");
  });

  it("leave ordinary links alone when stripping", () => {
    const link = "[CP264](https://academic-calendar.wlu.ca/cp264)";
    expect(stripCitations(link)).toBe(link);
  });
});
