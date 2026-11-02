import { cn } from "@/lib/utils";

import { CITED_SOURCES_LABEL, sourceNumberLabel } from "../labels";
import type { Source } from "../stream/events";
import { useAnswerSources } from "./answerSourcesContext";
import { SourceIcon } from "./SourceIcon";
import { hostOf } from "./sourceDisplay";

export interface CitedSource {
  number: number;
  /** Undefined until the answer's source list has arrived. */
  source: Source | undefined;
}

const ENTRY = "block rounded-lg px-3 py-2";

/**
 * The sources one citation names: site, title and a two-line preview. Shows about two, scrolls the rest.
 * Hovering or focusing an entry highlights the text the citation (`segment`) covers.
 */
export function SourceCard({ cited, segment }: { cited: readonly CitedSource[]; segment: string }) {
  const { setHighlight, clearHighlight } = useAnswerSources();
  const show = () => setHighlight({ segment, source: null });
  return (
    <ul aria-label={CITED_SOURCES_LABEL} className="max-h-[12.5rem] space-y-0.5 overflow-y-auto overscroll-contain">
      {cited.map(({ number, source }) => (
        <li key={number} onPointerEnter={show} onPointerLeave={clearHighlight} onFocus={show} onBlur={clearHighlight}>
          <SourceEntry number={number} source={source} />
        </li>
      ))}
    </ul>
  );
}

function SourceEntry({ number, source }: CitedSource) {
  const host = source?.url ? hostOf(source.url) : null;
  const body = (
    <>
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <SourceIcon sourceType={source?.source_type} className="size-3.5 shrink-0" />
        <span className="truncate">{host ?? " "}</span>
      </span>
      <span className="block truncate text-sm font-medium">{source?.title ?? sourceNumberLabel(number)}</span>
      {source?.snippet && <span className="line-clamp-2 text-xs text-muted-foreground">{source.snippet}</span>}
    </>
  );
  if (!source?.url) return <div className={ENTRY}>{body}</div>;
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(ENTRY, "hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none")}
    >
      {body}
    </a>
  );
}
