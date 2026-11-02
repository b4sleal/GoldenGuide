import { createContext, useContext } from "react";

import type { Source } from "../stream/events";

/**
 * What to highlight, kept to one thing at a time so the answer never lights up in several places:
 * - `segment`: a source entry in a chip's card is hovered, so that citation's text is highlighted.
 * - `source`: a source in the bottom list is hovered, so the chips citing it are highlighted.
 * Hovering a chip itself highlights nothing.
 */
export interface Highlight {
  segment: string | null;
  source: number | null;
}

export const NO_HIGHLIGHT: Highlight = { segment: null, source: null };

export interface AnswerSources {
  /** The answer's sources; citation number n is `sources[n - 1]`. */
  sources: readonly Source[];
  highlight: Highlight;
  setHighlight: (highlight: Highlight) => void;
  clearHighlight: () => void;
}

export const AnswerSourcesContext = createContext<AnswerSources>({
  sources: [],
  highlight: NO_HIGHLIGHT,
  setHighlight: () => {},
  clearHighlight: () => {},
});

export function useAnswerSources(): AnswerSources {
  return useContext(AnswerSourcesContext);
}

/** The text a citation covers is lit while one of its card's sources is hovered. */
export function isSegmentHighlighted(highlight: Highlight, segment: string): boolean {
  return highlight.segment === segment;
}

/** A chip is lit while a source it cites is hovered in the bottom list. */
export function isChipHighlighted(highlight: Highlight, numbers: readonly number[]): boolean {
  return highlight.source !== null && numbers.includes(highlight.source);
}
