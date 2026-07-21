/**
 * MergeResultBanner Component (Feature 056)
 *
 * Displays the outcome of a completed tag merge: a success summary, the
 * copyable operation ID (FR-009), an optional entity-link hint (FR-016), and
 * a session-scoped undo action (FR-010).
 *
 * Implements:
 * - T032: Success message with copyable operation ID, error display
 * - T043: Session-scoped undo button wired via useUndoMerge in the parent
 * - FR-009: Operation ID displayed in a form the user can copy for later
 *   CLI use (`chronovista tags undo <operation_id>`)
 * - FR-010 / FR-010a: Undo affordance is session-scoped — it exists only for
 *   as long as the parent page keeps this component's `onUndo` prop wired
 *   (i.e. within the same, unrefreshed session). The operation ID remains
 *   visible as the documented CLI fallback regardless of whether undo is
 *   available. `onUndo` is intentionally optional: the parent omits it once
 *   the session-scoped affordance should no longer be offered (e.g. after a
 *   fresh mount that doesn't carry forward in-memory merge state).
 * - FR-016: entity_hint (post-merge) is surfaced here — see MergeConfirmation
 *   for why it cannot be shown at the preview stage.
 * - FR-018: WCAG 2.1 AA — role="status" for the success summary, role="alert"
 *   for undo errors, and a "Copied" announcement for the copy action.
 */

import { useState } from "react";

import type { MergeResult } from "../../types/canonical-tags";

export interface MergeResultBannerProps {
  /** The result of a successfully completed merge. */
  result: MergeResult;
  /**
   * Triggers the session-scoped undo. Omit this prop once the undo
   * affordance should no longer be offered (FR-010/FR-010a) — the banner
   * then falls back to the CLI-only instructions.
   */
  onUndo?: () => void;
  /** Whether the undo mutation is currently in flight. */
  isUndoing?: boolean;
  /** Whether the undo mutation has already completed successfully. */
  undoSuccess?: boolean;
  /** Error from a failed undo attempt, if any. */
  undoError?: unknown;
}

/** Extracts a readable message from an unknown error value. */
function undoErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Could not undo this merge. Please try again.";
}

export function MergeResultBanner({
  result,
  onUndo,
  isUndoing = false,
  undoSuccess = false,
  undoError,
}: MergeResultBannerProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopyOperationId() {
    try {
      await navigator.clipboard.writeText(result.operation_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access denied or unavailable — the operation ID remains
      // visible and selectable as a fallback, so this is a silent no-op.
    }
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Merge result"
      className="rounded-xl border border-green-200 bg-green-50 shadow-sm p-5 space-y-4"
    >
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-green-900">Merge complete</h2>
        <p className="mt-0.5 text-sm text-green-800">
          {result.source_tags.join(", ")} merged into{" "}
          <span className="font-medium">{result.target_tag}</span>.
        </p>
      </div>

      {/* Stats */}
      <div className="flex items-stretch divide-x divide-green-200 bg-white rounded-lg border border-green-100">
        <div className="flex flex-col items-center gap-0.5 px-4 py-3 flex-1">
          <span className="text-xl font-bold text-slate-800 tabular-nums">
            {result.aliases_moved}
          </span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            Aliases moved
          </span>
        </div>
        <div className="flex flex-col items-center gap-0.5 px-4 py-3 flex-1">
          <span className="text-xl font-bold text-slate-800 tabular-nums">
            {result.new_alias_count}
          </span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            Total aliases
          </span>
        </div>
        <div className="flex flex-col items-center gap-0.5 px-4 py-3 flex-1">
          <span className="text-xl font-bold text-slate-800 tabular-nums">
            {result.new_video_count}
          </span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            Total videos
          </span>
        </div>
      </div>

      {/* Entity hint (FR-016) */}
      {result.entity_hint && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800">{result.entity_hint}</p>
        </div>
      )}

      {/* Operation ID (FR-009) */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-slate-600">Operation ID:</span>
        <code className="px-2 py-1 text-xs font-mono bg-white border border-slate-200 rounded text-slate-800">
          {result.operation_id}
        </code>
        <button
          type="button"
          onClick={() => void handleCopyOperationId()}
          aria-label="Copy operation ID to clipboard"
          className="inline-flex items-center gap-1 px-2 py-1 min-h-[32px] text-xs font-medium rounded-md border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <p className="text-xs text-slate-500">
        Use this ID to reverse the merge later via the CLI:{" "}
        <code className="font-mono">
          chronovista tags undo {result.operation_id}
        </code>
      </p>

      {/* Session-scoped undo (FR-010, FR-010a) */}
      {onUndo && !undoSuccess && (
        <div>
          <button
            type="button"
            onClick={onUndo}
            disabled={isUndoing}
            className="inline-flex items-center gap-2 px-4 py-2 min-h-[44px] rounded-md text-sm font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isUndoing && (
              <div
                className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin"
                aria-hidden="true"
              />
            )}
            {isUndoing ? "Undoing…" : "Undo this merge"}
          </button>
          {undoError !== undefined && undoError !== null && (
            <p role="alert" className="mt-2 text-sm text-red-700">
              {undoErrorMessage(undoError)}
            </p>
          )}
        </div>
      )}

      {undoSuccess && (
        <p role="status" className="text-sm font-medium text-green-800">
          Merge undone. Source tags and their video associations were restored.
        </p>
      )}
    </div>
  );
}
