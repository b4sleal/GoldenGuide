/**
 * The chat NDJSON stream contract (backend: src/backend/api/streaming.py).
 *
 * Every line is validated at runtime: the stream is not described by OpenAPI, so this schema is the
 * only thing that catches a backend change before it renders as a broken answer.
 */
import { z } from "zod";

export const TurnStage = z.enum(["understanding", "searching", "writing"]);
export type TurnStage = z.infer<typeof TurnStage>;

export const RetrievalSource = z.enum(["courses", "course_terms", "wlu_pages", "vector"]);
export type RetrievalSource = z.infer<typeof RetrievalSource>;

/** The standard error envelope, shared by JSON error responses and in-stream `error` events. */
export const ApiErrorBody = z.object({
  code: z.string(),
  message: z.string(),
  request_id: z.string().nullish(),
  trace_id: z.string().nullish(),
});
export type ApiErrorBody = z.infer<typeof ApiErrorBody>;

export const Source = z.object({
  title: z.string(),
  url: z.string().nullish(),
  source_type: z.string().nullish(),
  /** Start of the first passage the source contributed, for its preview card. Older answers have none. */
  snippet: z.string().nullish(),
});
export type Source = z.infer<typeof Source>;

export const StreamEvent = z.discriminatedUnion("type", [
  z.object({ type: z.literal("status"), stage: TurnStage, source: RetrievalSource.optional() }),
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({
    type: z.literal("citation"),
    source_nums: z.array(z.number().int().positive()),
    urls: z.array(z.string().nullable()),
  }),
  z.object({
    type: z.literal("table"),
    title: z.string(),
    columns: z.array(z.string()),
    rows: z.array(z.array(z.string())),
  }),
  z.object({ type: z.literal("sources"), sources: z.array(Source) }),
  /** The complete answer was stored under this ID, so it can be rated. Absent if history is unavailable. */
  z.object({ type: z.literal("saved"), message_id: z.number().int().positive() }),
  z.object({ type: z.literal("error"), error: ApiErrorBody }),
  z.object({ type: z.literal("ok") }),
]);
export type StreamEvent = z.infer<typeof StreamEvent>;

export type TableEvent = Extract<StreamEvent, { type: "table" }>;
export type StatusEvent = Extract<StreamEvent, { type: "status" }>;
