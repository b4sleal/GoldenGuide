import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { type PointerEvent, type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import { NEXT_SOURCES_LABEL, PREVIOUS_SOURCES_LABEL, SOURCE_LINKS_LABEL, SOURCES_LABEL } from "../labels";

/** Native touch/keyboard scrolling, plus mouse dragging, without a carousel dependency or autoplay. */
export function SourceCarousel({ children }: { children: ReactNode }) {
  const viewport = useRef<HTMLOListElement>(null);
  const drag = useRef<{ id: number; x: number; left: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [edges, setEdges] = useState({ start: true, end: true });
  const id = useId();

  const updateEdges = useCallback(() => {
    const element = viewport.current;
    if (!element) return;
    const next = { start: element.scrollLeft <= 1, end: element.scrollLeft + element.clientWidth >= element.scrollWidth - 1 };
    setEdges((previous) => previous.start === next.start && previous.end === next.end ? previous : next);
  }, []);

  useEffect(() => {
    updateEdges();
    if (!viewport.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateEdges);
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, [children, updateEdges]);

  function move(direction: number) {
    const element = viewport.current;
    if (!element) return;
    element.scrollBy({
      left: direction * element.clientWidth * 0.8,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  }

  function pointerDown(event: PointerEvent<HTMLOListElement>) {
    // Let touch gestures use the browser's scrolling/inertia. Links remain ordinary clicks until dragged.
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    suppressClick.current = false;
    drag.current = { id: event.pointerId, x: event.clientX, left: event.currentTarget.scrollLeft, moved: false };
  }

  function pointerMove(event: PointerEvent<HTMLOListElement>) {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    // A release outside the list can happen before the drag threshold captures the pointer.
    if ((event.buttons & 1) === 0) {
      drag.current = null;
      setDragging(false);
      return;
    }
    const delta = event.clientX - current.x;
    if (!current.moved && Math.abs(delta) < 6) return;
    if (!current.moved) {
      current.moved = true;
      suppressClick.current = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragging(true);
    }
    event.preventDefault();
    // No React updates per pixel: the browser owns the scrolling position.
    event.currentTarget.scrollLeft = current.left - delta;
  }

  function pointerEnd(event: PointerEvent<HTMLOListElement>) {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <div className="min-w-0">
      <div className="mb-1 flex h-8 items-center justify-between gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{SOURCES_LABEL}</h3>
        {!(edges.start && edges.end) && (
          <div className="flex gap-1">
            <Button size="icon-sm" variant="ghost" aria-label={PREVIOUS_SOURCES_LABEL} aria-controls={id} disabled={edges.start} onClick={() => move(-1)}>
              <ChevronLeftIcon />
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label={NEXT_SOURCES_LABEL} aria-controls={id} disabled={edges.end} onClick={() => move(1)}>
              <ChevronRightIcon />
            </Button>
          </div>
        )}
      </div>
      <ol
        id={id}
        ref={viewport}
        aria-label={SOURCE_LINKS_LABEL}
        tabIndex={0}
        data-dragging={dragging || undefined}
        className="source-carousel flex gap-2 overflow-x-auto overscroll-x-contain rounded-md p-1 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        onScroll={updateEdges}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerEnd}
        onPointerCancel={pointerEnd}
        onLostPointerCapture={pointerEnd}
        onDragStart={(event) => event.preventDefault()}
        onClickCapture={(event) => {
          // A drag must not open the card's link. Keyboard activation (detail=0) remains available.
          if (suppressClick.current && event.detail !== 0) {
            event.preventDefault();
            event.stopPropagation();
          }
          suppressClick.current = false;
        }}
      >
        {children}
      </ol>
    </div>
  );
}
