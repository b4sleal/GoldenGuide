import { StreamEvent } from "./events";

const KNOWN_TYPES: ReadonlySet<string> = new Set(StreamEvent.options.map((option) => option.shape.type.value));

/** A line that is not valid JSON or does not match the stream contract. */
export class StreamProtocolError extends Error {
  constructor(readonly line: string, cause: unknown) {
    super("Unexpected chat stream event", { cause });
    this.name = "StreamProtocolError";
  }
}

/**
 * Yield each validated event of an NDJSON body. Network chunks are arbitrary byte ranges, so a line
 * (or a multi-byte character) can be split across chunks; only complete lines are parsed.
 */
export async function* readNdjson(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  // `stream: true` keeps a multi-byte character split across chunks until its remaining bytes arrive.
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        const event = line ? parseLine(line) : null;
        if (event) yield event;
      }
    }
    // The server ends every line with "\n"; a trailing fragment means the connection was cut mid-line.
    // It is dropped, and the missing terminal event marks the answer as interrupted.
  } finally {
    reader.releaseLock();
  }
}

/** Parse one line; null for an event type this client does not know yet (newer backend). */
function parseLine(line: string): StreamEvent | null {
  let json: unknown;
  try {
    json = JSON.parse(line);
  } catch (error) {
    throw new StreamProtocolError(line, error);
  }
  // Additive contract changes (new event types) must not break deployed clients. A known type with
  // the wrong shape is still an error: rendering it would show a broken answer.
  const type = (json as { type?: unknown } | null)?.type;
  if (typeof type === "string" && !KNOWN_TYPES.has(type)) return null;
  const parsed = StreamEvent.safeParse(json);
  if (!parsed.success) throw new StreamProtocolError(line, parsed.error);
  return parsed.data;
}
