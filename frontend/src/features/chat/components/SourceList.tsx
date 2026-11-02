import { ExternalLinkIcon } from "lucide-react";

import { SOURCES_LABEL } from "../labels";
import type { Source } from "../stream/events";
import { useAnswerSources } from "./answerSourcesContext";
import { SourceCarousel } from "./SourceCarousel";
import { SourceIcon } from "./SourceIcon";
import { hostOf } from "./sourceDisplay";

/**
 * Every source the answer used. Hovering or focusing one lights up the chips that cite it (not their
 * text, to keep the answer calm). Positions match the citation numbers, but none are shown.
 */
export function SourceList({ sources }: { sources: Source[] }) {
  const { setHighlight, clearHighlight } = useAnswerSources();
  if (sources.length === 0) return null;
  return (
    <section aria-label={SOURCES_LABEL} className="animate-in fade-in min-w-0 border-t pt-3">
      <SourceCarousel>
        {sources.map((source, index) => {
          const host = source.url ? hostOf(source.url) : null;
          const body = (
            <>
              <SourceIcon sourceType={source.source_type} className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0">
                <span className="block truncate font-medium">{source.title}</span>
                {host && <span className="block truncate text-xs text-muted-foreground">{host}</span>}
              </span>
              {source.url && <ExternalLinkIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />}
            </>
          );
          const chip = "flex w-full items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-sm";
          const hover = {
            onPointerEnter: () => setHighlight({ segment: null, source: index + 1 }),
            onPointerLeave: clearHighlight,
          };
          return (
            <li key={`${index}-${source.title}`} className="w-64 shrink-0" {...hover}>
              {source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onFocus={hover.onPointerEnter}
                  onBlur={clearHighlight}
                  className={`${chip} hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none`}
                >
                  {body}
                </a>
              ) : (
                <div className={chip}>{body}</div>
              )}
            </li>
          );
        })}
      </SourceCarousel>
    </section>
  );
}
