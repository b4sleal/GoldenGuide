import { ThumbsDownIcon, ThumbsUpIcon } from "lucide-react";
import { type FormEvent, type ReactNode, useId, useState } from "react";

import type { Schemas } from "@/api/client";
import { useSubmitFeedback } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { FEEDBACK_REASON_LABELS } from "../labels";

type Rating = Schemas["FeedbackRating"];
type Reason = Schemas["FeedbackReason"];

const REASONS = Object.entries(FEEDBACK_REASON_LABELS) as [Reason, string][];
const COMMENT_MAX = 2000;

/** Thumbs up/down for a stored answer; thumbs down asks what was wrong. A new rating replaces the old. */
export function Feedback({ messageId, children }: { messageId: number; children?: ReactNode }) {
  const submit = useSubmitFeedback();
  const [rating, setRating] = useState<Rating | null>(null);
  const [askingWhy, setAskingWhy] = useState(false);
  const [reason, setReason] = useState<Reason | null>(null);
  const [comment, setComment] = useState("");
  const [thanked, setThanked] = useState(false);
  const commentId = useId();

  function send(feedback: Schemas["FeedbackRequest"]) {
    submit.mutate({ messageId, feedback }, { onSuccess: () => setThanked(true) });
  }

  function rate(next: Rating) {
    setRating(next);
    setThanked(false);
    setAskingWhy(next === "down");
    send({ rating: next });
  }

  function sendDetails(event: FormEvent) {
    event.preventDefault();
    send({ rating: "down", reason, comment: comment.trim() || null });
    setAskingWhy(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {(["up", "down"] as const).map((value) => {
          const Icon = value === "up" ? ThumbsUpIcon : ThumbsDownIcon;
          return (
            <Button
              key={value}
              size="icon-sm"
              variant="ghost"
              aria-label={value === "up" ? "Good answer" : "Bad answer"}
              aria-pressed={rating === value}
              disabled={submit.isPending}
              onClick={() => rate(value)}
              className={cn(rating === value && "bg-secondary text-secondary-foreground")}
            >
              <Icon />
            </Button>
          );
        })}
        {children}
        <span role="status" className="text-xs text-muted-foreground">
          {submit.isError ? "Feedback could not be sent." : thanked && !askingWhy ? "Thanks for the feedback." : ""}
        </span>
      </div>

      {askingWhy && (
        <form onSubmit={sendDetails} className="animate-in fade-in space-y-2 rounded-lg border p-3">
          <fieldset className="flex flex-wrap gap-2">
            <legend className="mb-2 text-sm font-medium">What was wrong?</legend>
            {REASONS.map(([value, label]) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={reason === value ? "default" : "outline"}
                aria-pressed={reason === value}
                onClick={() => setReason(reason === value ? null : value)}
              >
                {label}
              </Button>
            ))}
          </fieldset>
          <label htmlFor={commentId} className="sr-only">
            More details (optional)
          </label>
          <textarea
            id={commentId}
            value={comment}
            maxLength={COMMENT_MAX}
            onChange={(event) => setComment(event.target.value)}
            placeholder="More details (optional)"
            rows={2}
            className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setAskingWhy(false)}>
              Skip
            </Button>
            <Button type="submit" size="sm" disabled={submit.isPending}>
              Send
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
