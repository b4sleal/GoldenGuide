import { describe, expect, it } from "vitest";

import { readNdjson, StreamProtocolError } from "./ndjson";

function bodyOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readNdjson(body)) events.push(event);
  return events;
}

describe("readNdjson", () => {
  it("parses a line split across chunks", async () => {
    const events = await collect(bodyOf('{"type": "te', 'xt", "text": "Hi"}\n{"type"', ': "ok"}\n'));
    expect(events).toEqual([{ type: "text", text: "Hi" }, { type: "ok" }]);
  });

  it("keeps a multi-byte character split across chunks", async () => {
    const bytes = new TextEncoder().encode('{"type": "text", "text": "é"}\n');
    const split = bytes.indexOf(0xc3) + 1; // between the two bytes of "é"
    const events = await collect(bodyOf(bytes.slice(0, split), bytes.slice(split)));
    expect(events).toEqual([{ type: "text", text: "é" }]);
  });

  it("ignores blank lines and drops an unterminated trailing fragment", async () => {
    const events = await collect(bodyOf('\n{"type": "text", "text": "a"}\n\n{"type": "o'));
    expect(events).toEqual([{ type: "text", text: "a" }]);
  });

  it("skips event types this client does not know", async () => {
    const events = await collect(bodyOf('{"type": "course_card", "code": "CP264"}\n{"type": "ok"}\n'));
    expect(events).toEqual([{ type: "ok" }]);
  });

  it("rejects a known event with the wrong shape", async () => {
    await expect(collect(bodyOf('{"type": "text", "text": 5}\n'))).rejects.toBeInstanceOf(StreamProtocolError);
  });

  it("rejects invalid JSON", async () => {
    await expect(collect(bodyOf("not json\n"))).rejects.toBeInstanceOf(StreamProtocolError);
  });
});
