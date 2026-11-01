import type { ReactNode } from "react";

/** A focusable viewport keeps wide or long tables inside the answer instead of squeezing cells. */
export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className="table-scroll">
      {children}
    </div>
  );
}
