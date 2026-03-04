/**
 * CorrectionHistoryPanel component for displaying the audit trail of corrections
 * applied to a transcript segment (Feature 035, T027).
 *
 * Implements:
 * - FR-035c: Correction history display with newest-first ordering
 * - WCAG 2.1 AA: role="region", aria-label, keyboard dismiss via Escape
 * - NFR-010: Focus-visible ring on interactive elements
 * - Paginated "Load more" via onLoadMore callback
 *
 * @module components/transcript/corrections/CorrectionHistoryPanel
 */

import type React from "react";
import type { CorrectionAuditRecord, CorrectionType } from "../../../types/corrections";
import { CORRECTION_TYPE_LABELS } from "../../../types/corrections";

/**
 * Props for the CorrectionHistoryPanel component.
 */
export interface CorrectionHistoryPanelProps {
  /** Audit records to display, ordered newest-first */
  records: CorrectionAuditRecord[];
  /** Whether the history query is currently loading */
  isLoading: boolean;
  /** Whether there are more records available to load */
  hasMore: boolean;
  /** Called when the "Load more" button is clicked */
  onLoadMore: () => void;
  /** Called when the panel should be dismissed (Escape key) */
  onClose: () => void;
}

/**
 * Returns the human-readable label for a correction type.
 * Uses CORRECTION_TYPE_LABELS for known CorrectionType values and
 * returns "Revert" for the "revert" sentinel value.
 */
function getCorrectionTypeLabel(type: CorrectionType | "revert"): string {
  if (type === "revert") return "Revert";
  return CORRECTION_TYPE_LABELS[type];
}

/**
 * HistoryRecordRow renders a single CorrectionAuditRecord row.
 */
function HistoryRecordRow({ record }: { record: CorrectionAuditRecord }) {
  const label = getCorrectionTypeLabel(record.correction_type);
  const formattedDate = new Date(record.corrected_at).toLocaleDateString();

  return (
    <div className="py-2 border-b border-slate-100 last:border-b-0">
      {/* Header row: timestamp + version + type badge */}
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-gray-500">
          {formattedDate} · v{record.version_number}
        </span>
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
          {label}
        </span>
      </div>

      {/* Original text with line-through */}
      <p className="text-sm text-gray-500 line-through">{record.original_text}</p>

      {/* Corrected text */}
      <p className="text-sm text-gray-900">{record.corrected_text}</p>

      {/* Correction note — only shown when present */}
      {record.correction_note !== null && (
        <p className="text-xs text-gray-600 italic mt-0.5">{record.correction_note}</p>
      )}
    </div>
  );
}

/**
 * SkeletonRow renders a loading placeholder for a history record.
 */
function SkeletonRow() {
  return (
    <div className="py-2 border-b border-slate-100 last:border-b-0 animate-pulse" aria-hidden="true">
      <div className="flex items-center gap-2 mb-1">
        <div className="h-3 w-24 bg-gray-200 rounded" />
        <div className="h-3 w-16 bg-gray-200 rounded" />
      </div>
      <div className="h-4 w-full bg-gray-200 rounded mb-1" />
      <div className="h-4 w-3/4 bg-gray-200 rounded" />
    </div>
  );
}

/**
 * CorrectionHistoryPanel renders the correction audit trail for a single segment.
 *
 * The panel is an inline bordered card that appears below the segment row.
 * Pressing Escape dismisses it by calling onClose.
 * When more records are available, a "Load more" button is shown at the bottom.
 *
 * @example
 * ```tsx
 * <CorrectionHistoryPanel
 *   records={historyData.data}
 *   isLoading={isLoading}
 *   hasMore={historyData.pagination.has_more}
 *   onLoadMore={handleLoadMore}
 *   onClose={handleHistoryClose}
 * />
 * ```
 */
export function CorrectionHistoryPanel({
  records,
  isLoading,
  hasMore,
  onLoadMore,
  onClose,
}: CorrectionHistoryPanelProps) {
  /**
   * Handles keydown events on the panel container.
   * Escape dismisses the panel; stopPropagation prevents the parent
   * transcript scroll handler from consuming the key.
   */
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      onClose();
    }
  };

  const showLoadingSkeleton = isLoading && records.length === 0;
  const showEmptyState = !isLoading && records.length === 0;

  return (
    <div
      role="region"
      aria-label="Correction history"
      className="bg-white border border-slate-200 rounded-md p-3 mt-1 max-h-64 overflow-y-auto"
      onKeyDown={handleKeyDown}
    >
      {/* Loading skeleton — 3 placeholder rows */}
      {showLoadingSkeleton && (
        <div role="status" aria-label="Loading correction history">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      )}

      {/* Empty state */}
      {showEmptyState && (
        <p className="text-sm text-gray-500 text-center py-2">
          No corrections recorded for this segment.
        </p>
      )}

      {/* Record list */}
      {records.length > 0 && (
        <>
          {records.map((record) => (
            <HistoryRecordRow key={record.id} record={record} />
          ))}

          {/* Load more button — shown when more pages are available */}
          {hasMore && (
            <div className="pt-2 flex justify-center">
              <button
                type="button"
                onClick={onLoadMore}
                className="
                  text-sm text-blue-600 hover:text-blue-800
                  px-3 py-1 rounded
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                  transition-colors
                "
              >
                Load more
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
