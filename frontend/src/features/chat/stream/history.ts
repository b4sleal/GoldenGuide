import type { Schemas } from "@/api/client";

import { type Answer, applyEvent, pendingAnswer } from "./answer";

type StoredMessage = Pick<Schemas["ChatMessagePublic"], "content" | "answer_content" | "sources">;

/** Replay display blocks through the live reducer so citation numbering and table order agree.
 * Legacy messages (and a future snapshot version this client cannot read) retain their text view.
 */
export function storedAnswerContent(message: StoredMessage): Pick<Answer, "blocks" | "sources"> {
  const snapshot = message.answer_content;
  let answer = pendingAnswer;
  if (snapshot?.version === 1) {
    for (const block of snapshot.blocks ?? []) answer = applyEvent(answer, block);
  } else if (message.content) {
    answer = applyEvent(answer, { type: "text", text: message.content });
  }
  return { blocks: answer.blocks, sources: message.sources ?? [] };
}
