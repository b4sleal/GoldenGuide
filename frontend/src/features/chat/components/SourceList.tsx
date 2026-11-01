import { ExternalLinkIcon } from "lucide-react";

import type { Source } from "../stream/events";
import { SOURCES_LABEL } from "../labels";
import { SourceCarousel } from "./SourceCarousel";

function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

/** The answer's numbered sources; numbers match the inline citation chips. */
export function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <section aria-label={SOURCES_LABEL} className="animate-in fade-in min-w-0 border-t pt-3">
      <SourceCarousel>
        {sources.map((source, index) => {
          const host = source.url ? hostOf(source.url) : null;
          const body = (
            <>
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-secondary text-[0.7rem] font-semibold text-secondary-foreground">
                {index + 1}
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium">{source.title}</span>
                {host && <span className="block truncate text-xs text-muted-foreground">{host}</span>}
              </span>
              {source.url && <ExternalLinkIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />}
            </>
          );
          const chip = "flex w-full items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-sm";
          return (
            <li key={`${index}-${source.title}`} className="w-64 shrink-0">
              {source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
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
