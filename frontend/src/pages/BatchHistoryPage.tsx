/**
 * BatchHistoryPage — displays the history of batch correction operations with
 * per-batch revert capability.
 *
 * Route: /corrections/batch/history
 *
 * Features (Feature 046, T009):
 * - Table of past BatchSummary items sorted most-recent-first (API default)
 * - Columns: Pattern, Replacement, Count, Actor, Timestamp, Actions
 * - "Load More" pagination (useBatchHistory infinite query)
 * - Confirmation dialog before reverting a batch (FR-027 focus trap)
 * - 404 / 409 error states in the confirmation dialog
 * - Empty state when no batches exist
 * - Loading skeleton on initial fetch
 */

import { useEffect, useRef, useState } from "react";

import { useBatchHistory, useRevertBatch } from "../hooks/useBatchHistory";
import { isApiError } from "../api/config";
import type { BatchSummary } from "../types/corrections";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO 8601 datetime string into a readable local date/time. */
function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Derive a human-readable error message from a revert failure. */
function getRevertErrorMessage(error: Error): string {
  if (isApiError(error)) {
    if (error.status === 404) return "Batch not found.";
    if (error.status === 409) return "This batch has already been reverted.";
  }
  return "Failed to revert batch. Please try again.";
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function BatchHistorySkeleton() {
  return (
    <div className="animate-pulse" aria-label="Loading batch history" role="status">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="bg-slate-100 px-6 py-3 flex gap-6">
          {[120, 120, 60, 100, 140].map((w, i) => (
            <div key={i} className={`h-4 w-${w} rounded bg-slate-300`} style={{ width: w }} />
          ))}
        </div>
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="border-t border-slate-100 px-6 py-4 flex gap-6 items-center">
            <div className="h-4 rounded bg-slate-200" style={{ width: 140 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 100 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 40 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 80 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 150 }} />
            <div className="h-8 rounded bg-slate-200" style={{ width: 70 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Revert confirmation dialog (FR-027 focus trap)
// ---------------------------------------------------------------------------

interface RevertDialogProps {
  /** The batch to revert */
  batch: BatchSummary;
  /** Whether the revert mutation is in progress */
  isPending: boolean;
  /** Error from a failed revert attempt */
  error: Error | null;
  /** Called when the user confirms the revert */
  onConfirm: () => void;
  /** Called when the user cancels or the dialog is closed */
  onCancel: () => void;
}

/**
 * Modal confirmation dialog for reverting a batch operation.
 *
 * Implements FR-027 focus management:
 * - Focus moves into the dialog when it mounts
 * - Tab cycles within the dialog only (Cancel → Confirm → Cancel → …)
 * - Escape dismisses the dialog
 * - Focus is returned to the trigger element by the parent via the triggerRef
 */
function RevertDialog({
  batch,
  isPending,
  error,
  onConfirm,
  onCancel,
}: RevertDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  // Move focus to the Cancel button when the dialog opens.
  useEffect(() => {
    cancelBtnRef.current?.focus();
  }, []);

  // Close on Escape key.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCancel();
        return;
      }
      // Focus trap: Tab / Shift+Tab cycles within the dialog.
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) return;

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  const errorMessage = error ? getRevertErrorMessage(error) : null;

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onClick={(e) => {
        // Dismiss if clicking the backdrop itself (not the dialog).
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="revert-dialog-title"
        aria-describedby="revert-dialog-desc"
        className="w-full max-w-md rounded-xl bg-white shadow-xl border border-slate-200 p-6"
      >
        <h2
          id="revert-dialog-title"
          className="text-lg font-semibold text-slate-900 mb-2"
        >
          Revert batch correction?
        </h2>

        <p id="revert-dialog-desc" className="text-sm text-slate-600 mb-4">
          This will undo all{" "}
          <strong>{batch.correction_count}</strong> correction
          {batch.correction_count === 1 ? "" : "s"} in this batch:
        </p>

        {/* Batch details */}
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 mb-4 space-y-1 text-sm">
          <div>
            <span className="text-slate-500">Pattern: </span>
            <code className="font-mono text-slate-800">{batch.pattern}</code>
          </div>
          <div>
            <span className="text-slate-500">Replacement: </span>
            <code className="font-mono text-slate-800">{batch.replacement}</code>
          </div>
          <div>
            <span className="text-slate-500">Applied: </span>
            <span className="text-slate-800">{formatTimestamp(batch.batch_timestamp)}</span>
          </div>
        </div>

        {/* Error feedback */}
        {errorMessage && (
          <p className="mb-4 text-sm text-red-600" role="alert">
            {errorMessage}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 justify-end">
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isPending ? "Reverting…" : "Confirm Revert"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

interface BatchRowProps {
  batch: BatchSummary;
  onRevert: (batch: BatchSummary, triggerEl: HTMLElement) => void;
}

function BatchRow({ batch, onRevert }: BatchRowProps) {
  const revertBtnRef = useRef<HTMLButtonElement>(null);

  return (
    <tr className="hover:bg-slate-50 transition-colors">
      <td className="px-4 py-3 text-sm">
        <code className="font-mono text-slate-800 break-all">{batch.pattern}</code>
      </td>
      <td className="px-4 py-3 text-sm">
        <code className="font-mono text-slate-800 break-all">{batch.replacement}</code>
      </td>
      <td className="px-4 py-3 text-sm text-slate-700 tabular-nums">
        {batch.correction_count.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-sm text-slate-600 max-w-[120px] truncate">
        {batch.corrected_by_user_id || <span className="text-slate-400 italic">unknown</span>}
      </td>
      <td className="px-4 py-3 text-sm text-slate-500 whitespace-nowrap">
        <time dateTime={batch.batch_timestamp}>
          {formatTimestamp(batch.batch_timestamp)}
        </time>
      </td>
      <td className="px-4 py-3 text-right">
        <button
          ref={revertBtnRef}
          type="button"
          onClick={() => {
            if (revertBtnRef.current) {
              onRevert(batch, revertBtnRef.current);
            }
          }}
          className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
          aria-label={`Revert batch: ${batch.pattern} → ${batch.replacement}`}
        >
          Revert
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

/**
 * BatchHistoryPage — table of past batch correction operations.
 *
 * Route: /corrections/batch/history
 */
export function BatchHistoryPage() {
  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------
  const {
    data,
    isLoading,
    isError,
    error: queryError,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useBatchHistory();

  const revertMutation = useRevertBatch();

  // -------------------------------------------------------------------------
  // Dialog state
  // -------------------------------------------------------------------------

  /** The batch currently pending revert confirmation, or null when dialog closed. */
  const [confirmingBatch, setConfirmingBatch] = useState<BatchSummary | null>(null);

  /** Ref to the Revert button that triggered the dialog (for focus return on close). */
  const triggerRef = useRef<HTMLElement | null>(null);

  // -------------------------------------------------------------------------
  // Page title
  // -------------------------------------------------------------------------
  useEffect(() => {
    document.title = "Batch History - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------
  const batches = data?.pages.flatMap((p) => p.data) ?? [];
  const isEmpty = !isLoading && batches.length === 0;

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  function handleOpenDialog(batch: BatchSummary, triggerEl: HTMLElement) {
    triggerRef.current = triggerEl;
    revertMutation.reset(); // clear any previous error
    setConfirmingBatch(batch);
  }

  function handleCloseDialog() {
    setConfirmingBatch(null);
    // Return focus to the Revert button that opened the dialog (FR-027).
    triggerRef.current?.focus();
    triggerRef.current = null;
  }

  function handleConfirmRevert() {
    if (!confirmingBatch) return;
    revertMutation.mutate(confirmingBatch.batch_id, {
      onSuccess: () => {
        setConfirmingBatch(null);
        // Return focus to the Revert button that opened the dialog so it is
        // not silently lost after a successful revert (FR-027).
        triggerRef.current?.focus();
        triggerRef.current = null;
      },
    });
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <main className="container mx-auto px-4 py-8">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Batch History</h1>
        <p className="mt-1 text-sm text-slate-500">
          Past batch find-and-replace operations. Revert any batch to undo all
          its corrections.
        </p>
      </div>

      {/* Loading state */}
      {isLoading && <BatchHistorySkeleton />}

      {/* Query error state */}
      {isError && !isLoading && (
        <div
          className="rounded-xl bg-red-50 border border-red-200 p-6 text-sm text-red-700"
          role="alert"
        >
          Failed to load batch history.{" "}
          {isApiError(queryError)
            ? queryError.message
            : "Please try refreshing the page."}
        </div>
      )}

      {/* Empty state */}
      {isEmpty && !isError && (
        <div className="rounded-xl bg-white border border-slate-200 p-12 text-center shadow-sm">
          <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
            <svg
              aria-hidden="true"
              className="w-6 h-6 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <p className="text-slate-600 font-medium">No batch operations found.</p>
          <p className="mt-1 text-sm text-slate-400">
            Apply a find-replace batch to see history here.
          </p>
        </div>
      )}

      {/* Batch table */}
      {batches.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-100">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Pattern
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Replacement
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Count
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Actor
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Timestamp
                  </th>
                  <th scope="col" className="relative px-4 py-3">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {batches.map((batch) => (
                  <BatchRow
                    key={batch.batch_id}
                    batch={batch}
                    onRevert={handleOpenDialog}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Load More footer */}
          {(hasNextPage || isFetchingNextPage) && (
            <div className="border-t border-slate-200 px-4 py-3 flex justify-center">
              <button
                type="button"
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
                className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-label="Load more batch operations"
              >
                {isFetchingNextPage ? "Loading…" : "Load More"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Confirmation dialog */}
      {confirmingBatch && (
        <RevertDialog
          batch={confirmingBatch}
          isPending={revertMutation.isPending}
          error={revertMutation.error}
          onConfirm={handleConfirmRevert}
          onCancel={handleCloseDialog}
        />
      )}
    </main>
  );
}