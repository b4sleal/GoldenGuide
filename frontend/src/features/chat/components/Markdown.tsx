import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { ANSWER_TABLE_LABEL } from "../labels";
import { CITATION_TITLE } from "../stream/answer";
import { TableScroll } from "./TableScroll";

/**
 * Answer Markdown. react-markdown builds React elements (no raw HTML is rendered) and its default
 * URL transform drops unsafe protocols such as `javascript:`, so model output cannot inject script.
 */
const components: Components = {
  a({ href, title, children }) {
    if (title === CITATION_TITLE) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          data-citation=""
          aria-label={`Source ${String(children)} (opens in a new tab)`}
          className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-full bg-secondary px-1.5 align-middle text-[0.7rem] font-semibold text-secondary-foreground no-underline hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {children}
        </a>
      );
    }
    return (
      <a href={href} title={title} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
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

export const Markdown = memo(function Markdown({ markdown }: { markdown: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </ReactMarkdown>
  );
});
