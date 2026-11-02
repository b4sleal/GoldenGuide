/**
 * Inline citations travel through the Markdown pipeline as links: one per citation event, titled
 * CITATION_TITLE, with the cited source numbers in a fragment-only href. A fragment passes
 * react-markdown's URL filter, and the renderer turns these links into source chips, so the answer
 * text itself never shows `[1]`. Live and restored answers use the same encoding.
 */
export const CITATION_TITLE = "gg-citation";
const HREF_PREFIX = "#gg-cite-";
const CITATION_LINK = new RegExp(` ?\\[[\\d,]+\\]\\(${HREF_PREFIX}[\\d-]+ "${CITATION_TITLE}"\\)`, "g");

/** One citation as Markdown, e.g. `[1,2](#gg-cite-1-2 "gg-citation")`. */
export function citationMarkdown(sourceNums: readonly number[]): string {
  return `[${sourceNums.join(",")}](${HREF_PREFIX}${sourceNums.join("-")} "${CITATION_TITLE}")`;
}

/** The source numbers of a citation link's href; empty when it is not one. */
export function parseCitationHref(href: string | undefined): number[] {
  if (!href?.startsWith(HREF_PREFIX)) return [];
  return href
    .slice(HREF_PREFIX.length)
    .split("-")
    .map(Number)
    .filter((number) => Number.isInteger(number) && number > 0);
}

/** Markdown without citation links, for copying: the source list is appended separately. */
export function stripCitations(markdown: string): string {
  return markdown.replace(CITATION_LINK, "");
}
