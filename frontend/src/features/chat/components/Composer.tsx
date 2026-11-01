import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/** Matches the backend's ChatRequest.query max_length. */
export const QUESTION_MAX_LENGTH = 4000;

/** Question input. Enter sends, Shift+Enter adds a line; while an answer streams, Stop replaces Send. */
export function Composer({
  streaming,
  onSend,
  onStop,
  conversationId = null,
  preserveDraft = false,
}: {
  streaming: boolean;
  onSend: (question: string) => void;
  onStop: () => void;
  conversationId?: string | null;
  preserveDraft?: boolean;
}) {
  const [draft, setDraft] = useState({ conversationId, value: "" });
  // A newly assigned server ID belongs to the same chat. Explicit switches start a fresh draft.
  if (draft.conversationId !== conversationId) {
    setDraft({ conversationId, value: preserveDraft ? draft.value : "" });
  }
  const value = draft.value;
  const setValue = (next: string) => setDraft({ conversationId, value: next });
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Suggested-question buttons disappear after sending; move their focus to the surviving input.
    if (streaming) input.current?.focus({ preventScroll: true });
  }, [streaming]);

  // Grow with the text up to the CSS max height.
  useEffect(() => {
    const element = input.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (streaming || !value.trim()) return;
    onSend(value);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2 rounded-2xl border bg-background p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
      <label htmlFor="question" className="sr-only">
        Ask about Laurier courses, programs and policies
      </label>
      <textarea
        id="question"
        ref={input}
        autoFocus
        rows={1}
        value={value}
        maxLength={QUESTION_MAX_LENGTH}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about courses, programs, deadlines…"
        className="max-h-48 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-muted-foreground"
      />
      {streaming ? (
        <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop answer">
          <SquareIcon className="fill-current" />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!value.trim()} aria-label="Send question">
          <ArrowUpIcon />
        </Button>
      )}
    </form>
  );
}
