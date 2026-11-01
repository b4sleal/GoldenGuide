import { CheckIcon, CopyIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import { answerClipboardText } from "../clipboard";
import { ANSWER_COPIED_LABEL, COPY_ANSWER_LABEL, COPY_FAILED_LABEL } from "../labels";
import type { AnswerBlock } from "../stream/answer";
import type { Source } from "../stream/events";
import { Feedback } from "./Feedback";

function CopyAnswer({ text }: { text: string }) {
  const [status, setStatus] = useState<"idle" | "copied" | "error">("idle");
  useEffect(() => {
    if (status !== "copied") return;
    const timer = setTimeout(() => setStatus("idle"), 2000);
    return () => clearTimeout(timer);
  }, [status]);

  async function copy() {
    try {
      // Clipboard access must happen inside a user gesture; permission failures stay local to Copy.
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      setStatus("error");
    }
  }

  return (
    <>
      <Button size="icon-sm" variant="ghost" aria-label={COPY_ANSWER_LABEL} title={COPY_ANSWER_LABEL} onClick={() => void copy()}>
        {status === "copied" ? <CheckIcon /> : <CopyIcon />}
      </Button>
      <span role="status" className="text-xs text-muted-foreground">
        {status === "copied" ? ANSWER_COPIED_LABEL : status === "error" ? COPY_FAILED_LABEL : ""}
      </span>
    </>
  );
}

/** Copy works without a saved message ID; rating still requires a persisted answer. */
export function AnswerActions({ blocks, sources, messageId }: {
  blocks: readonly AnswerBlock[];
  sources: readonly Source[];
  messageId?: number;
}) {
  const text = answerClipboardText(blocks, sources);
  const copy = blocks.length > 0 && text ? <CopyAnswer text={text} /> : null;
  if (messageId !== undefined) return <Feedback messageId={messageId}>{copy}</Feedback>;
  return copy ? <div className="flex items-center gap-1">{copy}</div> : null;
}
