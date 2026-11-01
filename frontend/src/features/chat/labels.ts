/**
 * All student-facing wording for chat states, in one place (easy to review and translate).
 * The backend sends codes only; see docs/frontend/ux.md "Status messages".
 */
import type { Schemas } from "@/api/client";

import type { AnswerPhase } from "./stream/answer";
import type { RetrievalSource, StatusEvent, TurnStage } from "./stream/events";

const STAGE_LABELS: Record<TurnStage, string> = {
  understanding: "Understanding your question…",
  searching: "Searching…",
  writing: "Writing answer…",
};

const SOURCE_LABELS: Record<RetrievalSource, string> = {
  courses: "Searching Academic Calendar courses…",
  course_terms: "Searching LORIS registration…",
  wlu_pages: "Searching Academic Calendar programs…",
  vector: "Searching WLU pages…",
};

export function statusLabel(status: Omit<StatusEvent, "type"> | null): string {
  if (!status) return "Sending…";
  if (status.stage === "searching" && status.source) return SOURCE_LABELS[status.source];
  return STAGE_LABELS[status.stage];
}

/** Shown when an answer is still running after this long (NN/g: attention is lost past ~10 s). */
export const SLOW_ANSWER_MS = 10_000;
export const SLOW_ANSWER_LABEL = "Still working, checking more sources…";

export const ANSWER_READY_LABEL = "Answer ready.";
export const ANSWER_TABLE_LABEL = "Answer table";
export const COPY_ANSWER_LABEL = "Copy answer";
export const ANSWER_COPIED_LABEL = "Copied";
export const COPY_FAILED_LABEL = "Could not copy. Try again or select the answer text.";
export const COPIED_SOURCES_LABEL = "Sources";
export const SOURCES_LABEL = "Sources";
export const SOURCE_LINKS_LABEL = "Source links";
export const PREVIOUS_SOURCES_LABEL = "Previous sources";
export const NEXT_SOURCES_LABEL = "Next sources";

/** Notice under an unfinished answer. Errors use the server's own message instead. */
export const ENDED_NOTICES: Partial<Record<AnswerPhase, string>> = {
  interrupted: "The answer was cut off before it finished. This is not a complete answer.",
  stopped: "You stopped this answer. It may be incomplete.",
};

/** Notice for a stored answer that did not complete (from history). */
export const STORED_STATUS_NOTICES: Partial<Record<Schemas["MessageStatus"], string>> = {
  error: "This answer failed before it finished. It may be incomplete.",
  interrupted: "This answer was cut off before it finished. It may be incomplete.",
};

export const FEEDBACK_REASON_LABELS: Record<Schemas["FeedbackReason"], string> = {
  wrong_information: "Wrong information",
  outdated: "Out of date",
  missing_source: "Missing or wrong source",
  did_not_answer: "Didn't answer my question",
  other: "Something else",
};

export const SUGGESTED_QUESTIONS = [
  "What are the prerequisites for CP264?",
  "Is CP414, CP468, or CP470 offered in winter?",
  "Course requirements for comp sci & psych",
  "What does the Computer Science BSc program require?",
] as const;
