/**
 * Typed access to the GoldenGuide API. Paths and bodies come from `schema.gen.ts`, generated from
 * FastAPI's OpenAPI document (`pnpm gen:api`), so a backend contract change fails `pnpm typecheck`.
 */
import createClient from "openapi-fetch";

import { ApiErrorBody } from "@/features/chat/stream/events";

import type { components, paths } from "./schema.gen";

export type Schemas = components["schemas"];

/** Same origin as the page: the session/device cookies and the backend's same-origin check apply. */
export const api = createClient<paths>({
  baseUrl: apiUrl(""),
  credentials: "same-origin",
  // Resolve fetch at request time: MSW installs its interceptor after this module is imported.
  fetch: (request) => globalThis.fetch(request),
});

/** Absolute same-origin URL: `Request` outside a browser page (tests) cannot resolve relative ones. */
export function apiUrl(path: string): string {
  return new URL(path, window.location.origin).href.replace(/\/$/, "");
}

/** A failed API call, carrying the server's public error envelope. */
export class ApiError extends Error {
  constructor(readonly status: number, readonly body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
  }
}

const UNREADABLE_ERROR: Omit<ApiErrorBody, "request_id" | "trace_id"> = {
  code: "unexpected_response",
  message: "The server returned an unexpected response.",
};

export const NETWORK_ERROR: ApiErrorBody = {
  code: "network_error",
  message: "Could not reach GoldenGuide. Check your connection and try again.",
};

/** Read the `{"error": {...}}` envelope from an error response, whatever its body actually holds. */
export function toApiError(status: number, body: unknown): ApiError {
  const parsed = ApiErrorBody.safeParse((body as { error?: unknown } | null)?.error);
  return new ApiError(status, parsed.success ? parsed.data : UNREADABLE_ERROR);
}

/** Unwrap an openapi-fetch result: the data, or an ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok) throw toApiError(result.response.status, result.error);
  return result.data as T;
}
