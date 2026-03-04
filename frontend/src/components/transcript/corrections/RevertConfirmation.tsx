/**
 * RevertConfirmation component for inline revert workflow (Feature 035).
 *
 * Implements:
 * - US-6: Revert confirmation step before destructive action
 * - WCAG 2.5.8: Touch targets at minimum 44x44px for all interactive elements
 * - WCAG 2.4.3: Focus management — Confirm button receives focus on mount
 * - WCAG 4.1.3: Status messages via parent aria-live region
 * - Keyboard navigation: Escape cancels, stopPropagation prevents parent scroll intercept
 *
 * @module components/transcript/corrections/RevertConfirmation
 */

import { useEffect, useRef } from "react";

/**
 * Props for the RevertConfirmation component.
 */
export interface RevertConfirmationProps {
  /** Whether the revert mutation is in progress */
  isPending: boolean;
  /** Called when Confirm is clicked */
  onConfirm: () => void;
  /** Called when Cancel is clicked or Escape is pressed */
  onCancel: () => void;
}

/**
 * RevertConfirmation renders an inline horizontal confirmation row for reverting
 * a transcript segment correction.
 *
 * The Confirm button auto-focuses on mount (WCAG 2.4.3). Pressing Escape calls
 * onCancel. The container stops keydown propagation so the parent scroll handler
 * does not intercept arrow keys while the confirmation is open.
 *
 * @example
 * ```tsx
 * <RevertConfirmation
 *   isPending={revertMutation.isPending}
 *   onConfirm={handleRevertConfirm}
 *   onCancel={handleRevertCancel}
 * />
 * ```
 */
export function RevertConfirmation({
  isPending,
  onConfirm,
  onCancel,
}: RevertConfirmationProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // WCAG 2.4.3: Auto-focus Confirm button on mount so keyboard users can
  // confirm or cancel immediately without tabbing to the button.
  useEffect(() => {
    confirmButtonRef.current?.focus();
  }, []);

  /**
   * Stops propagation to prevent the parent transcript scroll handler from
   * consuming arrow/escape keys. Escape cancels the revert.
   */
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-md px-2 py-1"
      onKeyDown={handleKeyDown}
    >
      {/* Warning icon — amber triangle-exclamation, decorative */}
      <svg
        className="w-4 h-4 flex-shrink-0 text-amber-600"
        fill="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
          clipRule="evenodd"
        />
      </svg>

      {/* Confirmation label */}
      <span className="text-sm text-amber-900 flex-1">Revert to previous version?</span>

      {/* Confirm button — disabled and shows "Reverting..." when mutation is in-flight */}
      <button
        ref={confirmButtonRef}
        type="button"
        onClick={onConfirm}
        disabled={isPending}
        aria-busy={isPending ? "true" : undefined}
        className="
          min-h-[44px] min-w-[44px]
          px-3 py-1
          text-sm font-medium text-white
          bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400
          rounded-md
          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
          transition-colors
        "
      >
        {isPending ? "Reverting..." : "Confirm"}
      </button>

      {/* Cancel button — always enabled, even during pending mutation */}
      <button
        type="button"
        onClick={onCancel}
        className="
          min-h-[44px] min-w-[44px]
          px-3 py-1
          text-sm font-medium text-slate-700
          bg-white hover:bg-slate-50
          border border-slate-300
          rounded-md
          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
          transition-colors
        "
      >
        Cancel
      </button>
    </div>
  );
}
