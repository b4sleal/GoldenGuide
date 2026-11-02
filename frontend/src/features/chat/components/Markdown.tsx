import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

import { ANSWER_TABLE_LABEL } from "../labels";
import { CITATION_TITLE, parseCitationHref } from "../stream/citations";
import { isSegmentHighlighted, useAnswerSources } from "./answerSourcesContext";
import { CitationChip } from "./CitationChip";
import { rehypeCitationSegments, SEGMENT_PROP } from "./rehypeCitationSegments";
import { TableScroll } from "./TableScroll";

type MarkedProps = Record<string, unknown>;

/** The text a citation covers; lit while a source in that citation's card is hovered. */
function CitationSegment({ id, children }: { id: string; children: React.ReactNode }) {
  const { highlight } = useAnswerSources();
  const lit = isSegmentHighlighted(highlight, id);
  return (
    <span
      data-highlighted={lit ? "" : undefined}
      className={cn("rounded-sm transition-colors [box-decoration-break:clone]", lit && "bg-accent/30")}
    >
      {children}
    </span>
  );
}

/**
 * Answer Markdown. react-markdown builds React elements (no raw HTML is rendered) and its default
 * URL transform drops unsafe protocols such as `javascript:`, so model output cannot inject script.
 * Citation links become source chips and the text they cover is wrapped as a highlightable segment.
 */
const components: Components = {
  a({ href, title, children, node: _node, ...props }) {
    if (title === CITATION_TITLE) {
      const segment = String((props as MarkedProps)[SEGMENT_PROP] ?? href);
      return <CitationChip numbers={parseCitationHref(href)} segment={segment} />;
    }
    return (
      <a href={href} title={title} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  span({ children, node: _node, ...props }) {
    const marked = props as MarkedProps;
    const id = marked[SEGMENT_PROP];
    if (typeof id !== "string") return <span {...props}>{children}</span>;
    return <CitationSegment id={id}>{children}</CitationSegment>;
  },
  table({ children }) {
    return (
      <TableScroll label={ANSWER_TABLE_LABEL}>
        <table className="text-sm [&_td]:border-t [&_td]:px-3 [&_td]:py-1.5 [&_td]:align-top [&_th]:bg-muted [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold">
          {children}
        </table>
      </TableScroll>
    );
  },
};

/** `idPrefix` keeps citation ids unique across an answer's Markdown blocks. */
export const Markdown = memo(function Markdown({ markdown, idPrefix }: { markdown: string; idPrefix: string }) {
  const rehypePlugins = useMemo(() => [[rehypeCitationSegments, { idPrefix }] as [typeof rehypeCitationSegments, { idPrefix: string }]], [idPrefix]);
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={rehypePlugins} components={components}>
      {markdown}
    </ReactMarkdown>
  );
});
