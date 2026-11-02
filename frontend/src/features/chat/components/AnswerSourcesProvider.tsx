import { type ReactNode, useCallback, useMemo, useState } from "react";

import type { Source } from "../stream/events";
import { AnswerSourcesContext, type Highlight, NO_HIGHLIGHT } from "./answerSourcesContext";

/** Shares one answer's sources and hover highlight between its citation chips and its source list. */
export function AnswerSourcesProvider({ sources, children }: { sources: readonly Source[]; children: ReactNode }) {
  const [highlight, setHighlight] = useState<Highlight>(NO_HIGHLIGHT);
  const clearHighlight = useCallback(() => setHighlight(NO_HIGHLIGHT), []);
  const value = useMemo(
    () => ({ sources, highlight, setHighlight, clearHighlight }),
    [sources, highlight, clearHighlight],
  );
  return <AnswerSourcesContext.Provider value={value}>{children}</AnswerSourcesContext.Provider>;
}
