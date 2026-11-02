/**
 * One assistant answer, built event by event. Pure functions so every terminal case is unit tested
 * without a network or React.
 */
import { citationMarkdown } from "./citations";
import type { ApiErrorBody, Source, StatusEvent, StreamEvent, TableEvent } from "./events";

/**
 * How an answer ended. Only `complete` is a full answer (the stream's last event was `ok`).
 * - error:       the server reported a failure; any partial text is kept and marked incomplete.
 * - interrupted: the stream ended with neither `ok` nor `error` (dropped connection, proxy timeout).
 * - stopped:     the student pressed Stop.
 */
export type AnswerPhase = "pending" | "streaming" | "complete" | "error" | "interrupted" | "stopped";

export type AnswerBlock =
  | { kind: "markdown"; markdown: string }
  | { kind: "table"; table: Omit<TableEvent, "type"> };

export interface Answer {
  phase: AnswerPhase;
  /** Latest progress status; shown until the first text arrives. */
  status: Omit<StatusEvent, "type"> | null;
  blocks: AnswerBlock[];
  sources: Source[];
  error: ApiErrorBody | null;
  /** The stored answer's ID (from the `saved` event), needed to rate it. */
  messageId: number | null;
}

export const pendingAnswer: Answer = {
  phase: "pending",
  status: null,
  blocks: [],
  sources: [],
  error: null,
  messageId: null,
};

export function isFinished(answer: Answer): boolean {
  return answer.phase !== "pending" && answer.phase !== "streaming";
}

export function hasContent(answer: Answer): boolean {
  return answer.blocks.length > 0;
}

/** Apply one stream event. Events after a terminal one are ignored. */
export function applyEvent(answer: Answer, event: StreamEvent): Answer {
  if (isFinished(answer)) return answer;
  switch (event.type) {
    case "status":
      return { ...answer, status: { stage: event.stage, source: event.source } };
    case "text":
      return { ...answer, phase: "streaming", blocks: appendMarkdown(answer.blocks, event.text) };
    case "citation":
      return { ...answer, phase: "streaming", blocks: appendMarkdown(answer.blocks, citationMarkdown(event.source_nums)) };
    case "table": {
      const { type: _type, ...table } = event;
      return { ...answer, phase: "streaming", blocks: [...answer.blocks, { kind: "table", table }] };
    }
    case "sources":
      return { ...answer, sources: event.sources };
    case "saved":
      return { ...answer, messageId: event.message_id };
    case "error":
      return { ...answer, phase: "error", error: event.error };
    case "ok":
      return { ...answer, phase: "complete" };
  }
}

/** The stream closed or failed without a terminal event: the answer is not complete. */
export function endWithoutTerminal(answer: Answer, stopped: boolean): Answer {
  if (isFinished(answer)) return answer;
  return { ...answer, phase: stopped ? "stopped" : "interrupted" };
}

/** A failure reported before the stream started (HTTP error envelope, network error). */
export function failBeforeStream(answer: Answer, error: ApiErrorBody): Answer {
  return { ...answer, phase: "error", error };
}

function appendMarkdown(blocks: AnswerBlock[], text: string): AnswerBlock[] {
  const last = blocks.at(-1);
  if (last?.kind === "markdown") {
    return [...blocks.slice(0, -1), { kind: "markdown", markdown: last.markdown + text }];
  }
  return [...blocks, { kind: "markdown", markdown: text }];
}
