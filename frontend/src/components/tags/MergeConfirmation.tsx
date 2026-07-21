/**
 * MergeConfirmation Component (Feature 056)
 *
 * Confirmation step shown once at least one source tag and a target tag are
 * selected. Fetches an exact, read-only preview of the resulting alias and
 * video counts (FR-008, FR-008a) before allowing the user to confirm.
 *
 * Implements:
 * - T031: Source tags, target, exact preview counts, optional reason,
 *   confirm/cancel
 * - FR-008: Confirmation step showing source tags, target tag, and exact
 *   post-merge counts
 * - FR-013: Optional reason for the merge
 * - FR-018: WCAG 2.1 AA — loading/error states announced, confirm disabled
 *   until an exact preview is available
 *
 * Note: `entity_hint` is intentionally NOT shown here. Per the backend
 * contract (MergePreview schema), the preview endpoint does not return
 * entity_hint — only the post-merge MergeResult does. FR-016's entity hint
 * is surfaced in MergeResultBanner after the merge actually executes.
 */

import { useEffect, useRef } from "react";

import { useMergePreview } from "../../hooks/useMergePreview";
import type { SelectedMergeTag } from "../../types/canonical-tags";
import { isApiError } from "../../api/config";

/** Max length for the optional reason field, matching the backend schema. */
const REASON_MAX_LENGTH = 1000;

export interface MergeConfirmationProps {
  /** Selected source tags (at least one, per FR-006). */
  sources: SelectedMergeTag[];
  /** The designated target tag. */
  target: SelectedMergeTag;
  /** Current value of the optional reason field. */
  reason: string;
  /** Called when the reason field changes. */
  onReasonChange: (reason: string) => void;
  /** Called when the user confirms the merge. */
  onConfirm: () => void;
  /** Called when the user cancels (clears the current selection). */
  onCancel: () => void;
  /** Whether the merge mutation is currently in flight. */
  isMerging: boolean;
}

export function MergeConfirmation({
  sources,
  target,
  reason,
  onReasonChange,
  onConfirm,
  onCancel,
  isMerging,
}: MergeConfirmationProps) {
  const preview = useMergePreview();

  // Re-fetch the preview whenever the exact source/target combination
  // changes. A ref tracks the last requested combination so we don't
  // re-fire on every render (e.g. while typing in the reason textarea).
  const sourceKey = sources
    .map((s) => s.normalized_form)
    .sort()
    .join(",");
  const requestKey = `${sourceKey}::${target.normalized_form}`;
  const lastRequestKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (lastRequestKeyRef.current === requestKey) return;
    lastRequestKeyRef.current = requestKey;
    preview.mutate({
      source_normalized_forms: sources.map((s) => s.normalized_form),
      target_normalized_form: target.normalized_form,
    });
    // preview.mutate is stable across renders (TanStack Query mutation
    // object identity); only the request key should retrigger the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const canConfirm = preview.isSuccess && !isMerging;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-5 space-y-4">
      <h2 className="text-base font-semibold text-slate-800">Confirm merge</h2>

      {/* Summary */}
      <div className="text-sm text-slate-700 space-y-1">
        <p>
          <span className="font-medium">
            {sources.length} source tag{sources.length === 1 ? "" : "s"}
          </span>{" "}
          will merge into{" "}
          <span className="font-medium text-green-700">{target.canonical_form}</span>
          :
        </p>
        <ul className="list-disc list-inside text-slate-600">
          {sources.map((s) => (
            <li key={s.normalized_form}>{s.canonical_form}</li>
          ))}
        </ul>
      </div>

      {/* Preview loading state */}
      {preview.isPending && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 text-sm text-slate-500"
        >
          <div
            className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
            aria-hidden="true"
          />
          Calculating exact resulting counts…
        </div>
      )}

      {/* Preview error state */}
      {preview.isError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg" role="alert">
          <p className="text-sm text-red-800">
            {isApiError(preview.error) && preview.error.type === "timeout"
              ? "Preview request timed out."
              : preview.error.message || "Could not preview this merge."}
          </p>
          <button
            type="button"
            onClick={() => {
              lastRequestKeyRef.current = null;
              preview.mutate({
                source_normalized_forms: sources.map((s) => s.normalized_form),
                target_normalized_form: target.normalized_form,
              });
              lastRequestKeyRef.current = requestKey;
            }}
            className="mt-2 text-sm font-medium text-red-700 hover:text-red-900 underline focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 rounded"
          >
            Retry preview
          </button>
        </div>
      )}

      {/* Exact preview counts (FR-008, FR-008a) */}
      {preview.isSuccess && preview.data && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-slate-100 bg-slate-50 p-4 grid grid-cols-2 gap-4"
        >
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Resulting aliases
            </p>
            <p className="text-xl font-bold text-slate-800 tabular-nums">
              {preview.data.resulting_alias_count}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Resulting videos
            </p>
            <p className="text-xl font-bold text-slate-800 tabular-nums">
              {preview.data.resulting_video_count}
            </p>
          </div>
        </div>
      )}

      {/* Optional reason */}
      <div>
        <label
          htmlFor="merge-reason"
          className="block text-sm font-medium text-slate-900"
        >
          Reason <span className="font-normal text-slate-500">(optional)</span>
        </label>
        <textarea
          id="merge-reason"
          value={reason}
          onChange={(e) => onReasonChange(e.target.value)}
          disabled={isMerging}
          maxLength={REASON_MAX_LENGTH}
          rows={2}
          placeholder="e.g. Same person, title variant"
          className="mt-1 w-full px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:bg-slate-100 disabled:cursor-not-allowed"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onConfirm}
          disabled={!canConfirm}
          className="inline-flex items-center gap-2 px-4 py-2 min-h-[44px] rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isMerging && (
            <div
              className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"
              aria-hidden="true"
            />
          )}
          {isMerging ? "Merging…" : "Confirm merge"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={isMerging}
          className="px-4 py-2 min-h-[44px] rounded-md text-sm font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
