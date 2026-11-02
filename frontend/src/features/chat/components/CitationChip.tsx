import * as Popover from "@radix-ui/react-popover";
import { type MouseEvent, type PointerEvent, useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

import { citationChipLabel, sourceNumberLabel } from "../labels";
import { isChipHighlighted, useAnswerSources } from "./answerSourcesContext";
import { SourceCard } from "./SourceCard";

/** Hovering shows the card after a short pause and keeps it while the pointer travels into it. */
export const HOVER_OPEN_DELAY_MS = 150;
export const HOVER_CLOSE_DELAY_MS = 200;

/** The chip whose card is open. One card at a time: opening another (even by hover) closes a pinned one. */
let openChip: { owner: object; close: () => void } | null = null;

/**
 * An inline citation: the first source's title (and "+N" for more) as a chip. Hover shows a card with
 * every cited source; click, tap or Enter pins it open, since touch and keyboards cannot hover.
 * Hovering a source in the card highlights the text this citation covers; the chip alone highlights nothing.
 */
export function CitationChip({ numbers, segment }: { numbers: readonly number[]; segment: string }) {
  const { sources, highlight, clearHighlight } = useAnswerSources();
  const [open, setOpen] = useState(false);
  const pinned = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const cited = numbers.map((number) => ({ number, source: sources[number - 1] }));
  const titles = cited.map(({ number, source }) => source?.title ?? sourceNumberLabel(number));
  const lit = isChipHighlighted(highlight, numbers);

  // Identifies this chip in `openChip`.
  const [owner] = useState(() => ({}));

  const cancelTimer = () => clearTimeout(timer.current);

  const close = useCallback(() => {
    clearTimeout(timer.current);
    pinned.current = false;
    setOpen(false);
    clearHighlight();
    if (openChip?.owner === owner) openChip = null;
  }, [clearHighlight, owner]);

  useEffect(() => () => {
    clearTimeout(timer.current);
    if (openChip?.owner === owner) openChip = null;
  }, [owner]);

  function show() {
    if (openChip && openChip.owner !== owner) openChip.close();
    openChip = { owner, close };
    setOpen(true);
  }

  function enter(event: PointerEvent) {
    if (event.pointerType !== "mouse") return;
    cancelTimer();
    timer.current = setTimeout(show, HOVER_OPEN_DELAY_MS);
  }

  function leave(event: PointerEvent) {
    if (event.pointerType !== "mouse") return;
    cancelTimer();
    if (pinned.current) return;
    timer.current = setTimeout(close, HOVER_CLOSE_DELAY_MS);
  }

  function click(event: MouseEvent) {
    // Radix would toggle the card on click, undoing a hover that already opened it.
    event.preventDefault();
    cancelTimer();
    if (open && pinned.current) {
      close();
      return;
    }
    pinned.current = true;
    show();
  }

  return (
    <Popover.Root open={open} onOpenChange={(next) => (next ? show() : close())}>
      <Popover.Trigger asChild>
        <button
          type="button"
          data-citation=""
          data-highlighted={lit ? "" : undefined}
          aria-label={citationChipLabel(titles)}
          onClick={click}
          onPointerEnter={enter}
          onPointerLeave={leave}
          className={cn(
            "mx-0.5 inline-flex h-5 max-w-[14rem] items-center gap-1 rounded-full bg-secondary px-2 align-middle text-[0.7rem] font-medium text-secondary-foreground",
            "hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            lit && "bg-primary text-primary-foreground",
          )}
        >
          <span className="truncate">{titles[0]}</span>
          {titles.length > 1 && <span className="shrink-0">+{titles.length - 1}</span>}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          collisionPadding={12}
          onPointerEnter={cancelTimer}
          onPointerLeave={leave}
          // A hover-opened card must not take focus from the page; a click or Enter should.
          onOpenAutoFocus={(event) => {
            if (!pinned.current) event.preventDefault();
          }}
          className="z-50 w-[min(22rem,calc(100vw-2rem))] rounded-xl border bg-background p-1 text-foreground shadow-lg outline-none"
        >
          <SourceCard cited={cited} segment={segment} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
