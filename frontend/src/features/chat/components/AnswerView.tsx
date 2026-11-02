import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

import { ANSWER_READY_LABEL, ENDED_NOTICES, SLOW_ANSWER_LABEL, SLOW_ANSWER_MS, statusLabel } from "../labels";
import { type Answer, hasContent, isFinished } from "../stream/answer";
import { AnswerActions } from "./AnswerActions";
import { AnswerSourcesProvider } from "./AnswerSourcesProvider";
import { AnswerBlocks } from "./AnswerBlocks";
import { Notice } from "./Notice";
import { SourceList } from "./SourceList";

/** True once an unfinished answer has been running longer than SLOW_ANSWER_MS. */
function useSlow(running: boolean): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!running) return;
    const timer = setTimeout(() => setSlow(true), SLOW_ANSWER_MS);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [running]);
  return slow;
}

/** A live answer: progress status, streamed text and tables, sources, and how it ended. */
export function AnswerView({ answer, onRetry }: { answer: Answer; onRetry?: () => void }) {
  const running = !isFinished(answer);
  const slow = useSlow(running);
  const showStatus = running && !hasContent(answer);
  const notice = answer.phase === "error" ? answer.error?.message : ENDED_NOTICES[answer.phase];

  return (
    <AnswerSourcesProvider sources={answer.sources}>
      <div className="space-y-3" aria-busy={running}>
        {showStatus && (
          // Real backend progress, announced politely to screen readers.
          <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-muted-foreground">
            {statusLabel(answer.status).replace(/…$/, "")}
            {/* Decorative dots never become repeated live-region announcements. */}
            <span className="loading-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </p>
        )}

        {hasContent(answer) && (
          <div className={cn("answer-prose", running && "streaming-caret")}>
            <AnswerBlocks blocks={answer.blocks} />
          </div>
        )}

        {running && slow && <p className="text-sm text-muted-foreground">{SLOW_ANSWER_LABEL}</p>}

        {notice && <Notice message={notice} reference={answer.error?.request_id} onRetry={onRetry} />}

        {/* Announcing every streamed token would flood a screen reader; announce completion instead. */}
        <p className="sr-only" aria-live="polite">
          {answer.phase === "complete" ? ANSWER_READY_LABEL : ""}
        </p>

        {answer.phase !== "stopped" && <SourceList sources={answer.sources} />}
        {!running && <AnswerActions blocks={answer.blocks} sources={answer.sources} />}
      </div>
    </AnswerSourcesProvider>
  );
}
