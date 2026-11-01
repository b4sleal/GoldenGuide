import { AlertTriangleIcon, RotateCcwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

/** A visible note under an incomplete or failed answer, with an optional retry. */
export function Notice({ message, reference, onRetry }: { message: string; reference?: string | null; onRetry?: () => void }) {
  return (
    <div role="status" className="flex flex-wrap items-start gap-3 rounded-lg bg-warning px-3 py-2 text-sm text-warning-foreground">
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1">
        {message}
        {/* Lets staff find the exact request in logs and traces from a screenshot. */}
        {reference && <span className="block text-xs opacity-80">Reference: {reference}</span>}
      </p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RotateCcwIcon /> Try again
        </Button>
      )}
    </div>
  );
}
