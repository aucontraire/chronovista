/**
 * MergeTagsPage (Feature 056)
 *
 * Composes the tag merge workflow: TagMergeSelector (contains-mode search +
 * selection) -> MergeConfirmation (exact preview + confirm) -> MergeResultBanner
 * (success summary + session-scoped undo).
 *
 * Implements:
 * - T008: Page shell registered at /tags/merge
 * - T033: Workflow composition, loading indicators, disabled controls while
 *   a merge is in flight, empty-state prompt when no tags are selected
 * - FR-015: Reachable via the "Tags" sidebar nav group
 * - Edge case (spec ~L100-101): empty-state prompt before any selection, and
 *   a "no matches" indication surfaces from within TagMergeSelector itself
 */

import { useCallback, useEffect, useState } from "react";

import { MergeConfirmation } from "../components/tags/MergeConfirmation";
import { MergeResultBanner } from "../components/tags/MergeResultBanner";
import { TagMergeSelector } from "../components/tags/TagMergeSelector";
import { useMergeTags } from "../hooks/useMergeTags";
import { useUndoMerge } from "../hooks/useUndoMerge";
import type { MergeResult, SelectedMergeTag } from "../types/canonical-tags";
import { isApiError } from "../api/config";

/** Prompt shown before the user has selected any source or target tag. */
function EmptyStatePrompt() {
  return (
    <div
      role="note"
      className="flex flex-col items-center justify-center py-12 text-center border border-dashed border-slate-200 rounded-xl"
    >
      <div className="w-14 h-14 mb-4 rounded-full bg-blue-50 flex items-center justify-center">
        <svg
          aria-hidden="true"
          className="w-7 h-7 text-blue-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.83.699 2.529 0l4.318-4.318a1.79 1.79 0 0 0 0-2.529L10.507 3.659A2.25 2.25 0 0 0 9.568 3Z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-700 max-w-sm">
        Search for tags above, then add one or more source tags and designate a
        target to merge them into.
      </p>
      <p className="mt-2 text-xs text-slate-400 max-w-xs">
        Source tags are absorbed into the target; the target survives.
      </p>
    </div>
  );
}

export function MergeTagsPage() {
  const [sources, setSources] = useState<SelectedMergeTag[]>([]);
  const [target, setTarget] = useState<SelectedMergeTag | null>(null);
  const [reason, setReason] = useState("");
  const [completedResult, setCompletedResult] = useState<MergeResult | null>(null);
  const [undoSuccess, setUndoSuccess] = useState(false);

  const mergeMutation = useMergeTags();
  const undoMutation = useUndoMerge();

  useEffect(() => {
    document.title = "Merge Tags - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const handleAddSource = useCallback((tag: SelectedMergeTag) => {
    setSources((prev) => [...prev, tag]);
  }, []);

  const handleRemoveSource = useCallback((normalizedForm: string) => {
    setSources((prev) => prev.filter((s) => s.normalized_form !== normalizedForm));
  }, []);

  const handleSetTarget = useCallback((tag: SelectedMergeTag | null) => {
    setTarget(tag);
  }, []);

  const resetSelection = useCallback(() => {
    setSources([]);
    setTarget(null);
    setReason("");
  }, []);

  const handleCancel = useCallback(() => {
    resetSelection();
    mergeMutation.reset();
  }, [resetSelection, mergeMutation]);

  const handleConfirm = useCallback(() => {
    if (target === null || sources.length === 0) return;
    mergeMutation.mutate(
      {
        source_normalized_forms: sources.map((s) => s.normalized_form),
        target_normalized_form: target.normalized_form,
        ...(reason.trim() !== "" && { reason: reason.trim() }),
      },
      {
        onSuccess: (result) => {
          setCompletedResult(result);
          setUndoSuccess(false);
          undoMutation.reset();
          resetSelection();
        },
      }
    );
  }, [target, sources, reason, mergeMutation, undoMutation, resetSelection]);

  const handleUndo = useCallback(() => {
    if (completedResult === null) return;
    undoMutation.mutate(completedResult.operation_id, {
      onSuccess: () => setUndoSuccess(true),
    });
  }, [completedResult, undoMutation]);

  const isMerging = mergeMutation.isPending;
  const showEmptyState = sources.length === 0 && target === null;
  const showConfirmation = sources.length > 0 && target !== null;

  return (
    <main className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-slate-900">Merge Tags</h1>
        <p className="mt-1 text-sm text-slate-500">
          Search for tag variants, select one or more source tags, designate a
          target, and merge them into a single canonical tag.
        </p>
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-5">
          <TagMergeSelector
            sources={sources}
            target={target}
            onAddSource={handleAddSource}
            onRemoveSource={handleRemoveSource}
            onSetTarget={handleSetTarget}
            disabled={isMerging}
          />
        </div>

        {showEmptyState && <EmptyStatePrompt />}

        {showConfirmation && (
          <MergeConfirmation
            sources={sources}
            target={target}
            reason={reason}
            onReasonChange={setReason}
            onConfirm={handleConfirm}
            onCancel={handleCancel}
            isMerging={isMerging}
          />
        )}

        {mergeMutation.isError && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg" role="alert">
            <p className="text-sm text-red-800">
              {isApiError(mergeMutation.error) && mergeMutation.error.type === "timeout"
                ? "The merge request timed out. Please try again."
                : mergeMutation.error.message || "Could not complete the merge."}
            </p>
          </div>
        )}

        {completedResult && (
          <MergeResultBanner
            result={completedResult}
            onUndo={handleUndo}
            isUndoing={undoMutation.isPending}
            undoSuccess={undoSuccess}
            undoError={undoMutation.error}
          />
        )}
      </div>
    </main>
  );
}
