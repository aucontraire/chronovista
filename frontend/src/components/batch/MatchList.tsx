/**
 * MatchList Component
 *
 * Renders the full list of batch correction preview matches with all UI states:
 * loading skeletons, error banner, empty state, truncation banner, and the
 * scrollable match list.
 *
 * Implements:
 * - FR-004: Truncation banner when totalCount exceeds matches.length
 * - FR-008: Select all / Deselect all controls with aria-live selection count
 * - FR-015: Amber boundary connector between consecutive cross-segment pairs
 * - FR-023: Loading skeleton and error banner states
 * - FR-027: Empty state message when no matches are found
 * - NFR-003: Screen reader announcements for selection count changes
 *
 * @see T019, T023, T035 in batch corrections spec
 */

import { Fragment, useEffect, useRef, useState } from 'react';
import { MatchCard } from './MatchCard';
import type { BatchPreviewMatch } from '../../types/batchCorrections';

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface MatchListProps {
  /** Preview matches to display. */
  matches: BatchPreviewMatch[];
  /** Total match count from the server (may exceed matches.length). */
  totalCount: number;
  /** Whether the preview request is in flight. */
  isLoading: boolean;
  /** Error thrown by the preview request, if any. */
  error: Error | null;
  /** Set of segment IDs the user has selected for apply. */
  selectedIds: Set<number>;
  /** Fires when a match card's checkbox is toggled. */
  onToggleSelect: (segmentId: number) => void;
  /**
   * Optional post-apply status map (segment_id -> status).
   * Phase 4 will populate this after an apply operation completes.
   */
  statusMap?: Map<number, 'applied' | 'skipped' | 'failed'>;
  /** Select all callback — shown in the selection header (FR-008). */
  onSelectAll?: () => void;
  /** Deselect all callback — shown in the selection header (FR-008). */
  onDeselectAll?: () => void;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Animated skeleton placeholder for a single MatchCard.
 * The layout mirrors the real card: checkbox stub, meta header, and three
 * content rows of varying widths.
 */
function MatchCardSkeleton() {
  return (
    <div
      className="bg-white rounded-xl border border-gray-200 shadow-sm"
      aria-hidden="true"
    >
      <div className="flex gap-4 p-4 sm:p-5 animate-pulse">

        {/* Checkbox stub */}
        <div className="flex-shrink-0 pt-1">
          <div className="w-4 h-4 rounded bg-gray-200" />
        </div>

        {/* Body stubs */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* Meta header row */}
          <div className="flex items-center gap-3">
            <div className="h-4 bg-gray-200 rounded w-2/5" />
            <div className="h-4 bg-gray-200 rounded w-1/5" />
            <div className="h-5 bg-gray-200 rounded w-12" />
          </div>

          {/* Context before stub */}
          <div className="h-3 bg-gray-100 rounded w-3/4" />

          {/* Diff block stub */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 space-y-1.5">
              <div className="h-3 bg-gray-200 rounded w-16" />
              <div className="h-4 bg-gray-200 rounded w-full" />
            </div>
            <div className="flex-1 space-y-1.5">
              <div className="h-3 bg-gray-200 rounded w-16" />
              <div className="h-4 bg-gray-200 rounded w-full" />
            </div>
          </div>

          {/* Context after stub */}
          <div className="h-3 bg-gray-100 rounded w-1/2" />
        </div>
      </div>
    </div>
  );
}

/**
 * Red error banner shown when the preview request fails (FR-023).
 */
function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 p-4 rounded-lg border border-red-200 bg-red-50 text-red-800"
    >
      {/* Error icon */}
      <svg
        aria-hidden="true"
        className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-500"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01M10.293 5.293a1 1 0 011.414 0L21 14.586A1 1 0 0120 16H4a1 1 0 01-.707-1.707L10.293 5.293z"
        />
      </svg>

      <div className="min-w-0">
        <p className="text-sm font-medium">Preview failed</p>
        <p className="mt-0.5 text-sm text-red-700 break-words">{message}</p>
      </div>
    </div>
  );
}

/**
 * Amber truncation banner shown when the server returned more matches than are
 * being displayed (FR-004).
 */
function TruncationBanner({
  shown,
  total,
}: {
  shown: number;
  total: number;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 px-4 py-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-800"
    >
      <svg
        aria-hidden="true"
        className="w-4 h-4 flex-shrink-0 text-amber-500"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <p className="text-sm">
        Showing{' '}
        <span className="font-semibold">{shown}</span> of{' '}
        <span className="font-semibold">{total}</span> matches — refine your
        pattern to narrow results.
      </p>
    </div>
  );
}

/**
 * Neutral empty state message shown when the preview returns zero matches
 * (FR-027).
 */
function EmptyState() {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center py-16 text-center"
    >
      {/* Magnifying glass illustration */}
      <svg
        aria-hidden="true"
        className="w-10 h-10 mb-3 text-gray-300"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z"
        />
      </svg>
      <p className="text-sm font-medium text-gray-600">No matches found.</p>
      <p className="mt-1 text-sm text-gray-500">
        Try adjusting your pattern or filters.
      </p>
    </div>
  );
}

/**
 * Compact header row above the match cards when results are present (T023).
 *
 * - "Select all" / "Deselect all" buttons implement FR-008.
 * - The `<div role="status" aria-live="polite">` region announces selection
 *   count changes to screen readers. To avoid chatty announcements the live
 *   text is debounced by 300 ms (NFR-003).
 */
function SelectionHeader({
  selectedCount,
  totalCount,
  onSelectAll,
  onDeselectAll,
}: {
  selectedCount: number;
  totalCount: number;
  onSelectAll: () => void;
  onDeselectAll: () => void;
}) {
  // Debounce the live region text so rapid checkbox changes don't spam readers.
  const [liveText, setLiveText] = useState(
    `${selectedCount} of ${totalCount} selected`,
  );
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setLiveText(`${selectedCount} of ${totalCount} selected`);
    }, 300);
    return () => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [selectedCount, totalCount]);

  const allSelected = selectedCount === totalCount;
  const noneSelected = selectedCount === 0;

  return (
    <div className="flex items-center justify-between gap-3 px-1 py-1">
      {/* Visible selection count */}
      <p className="text-sm text-slate-600" aria-hidden="true">
        <span className="font-semibold text-slate-800">{selectedCount}</span>
        {' of '}
        <span className="font-semibold text-slate-800">{totalCount}</span>
        {' '}
        {totalCount !== 1 ? 'matches' : 'match'} selected
      </p>

      {/* Screen reader live region — debounced to avoid chattiness (NFR-003) */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {liveText}
      </div>

      {/* Select / Deselect controls */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onSelectAll}
          disabled={allSelected}
          className={[
            'text-xs font-medium px-2.5 py-1.5 rounded-md border transition-colors',
            'min-h-[44px] min-w-[44px]',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
            allSelected
              ? 'text-slate-400 border-slate-200 cursor-not-allowed'
              : 'text-blue-600 border-blue-200 hover:bg-blue-50 hover:border-blue-300',
          ].join(' ')}
        >
          Select all
        </button>
        <button
          type="button"
          onClick={onDeselectAll}
          disabled={noneSelected}
          className={[
            'text-xs font-medium px-2.5 py-1.5 rounded-md border transition-colors',
            'min-h-[44px] min-w-[44px]',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
            noneSelected
              ? 'text-slate-400 border-slate-200 cursor-not-allowed'
              : 'text-slate-600 border-slate-300 hover:bg-slate-50',
          ].join(' ')}
        >
          Deselect all
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * MatchList handles all display states for the batch correction preview list.
 *
 * Rendering priority:
 * 1. Loading → 3 skeleton cards
 * 2. Error → error banner
 * 3. Empty → empty state message
 * 4. Results → optional truncation banner + list of MatchCards
 *
 * @example
 * ```tsx
 * <MatchList
 *   matches={previewResult.matches}
 *   totalCount={previewResult.total_count}
 *   isLoading={isPreviewLoading}
 *   error={previewError}
 *   selectedIds={selectedIds}
 *   onToggleSelect={(id) => toggleSelection(id)}
 * />
 * ```
 */
export function MatchList({
  matches,
  totalCount,
  isLoading,
  error,
  selectedIds,
  onToggleSelect,
  statusMap,
  onSelectAll,
  onDeselectAll,
}: MatchListProps) {
  // -------------------------------------------------------------------------
  // Loading state — show 3 skeleton cards (FR-023)
  // -------------------------------------------------------------------------
  if (isLoading) {
    return (
      <div
        role="status"
        aria-label="Loading preview matches"
        aria-busy={true}
        className="space-y-4"
      >
        <MatchCardSkeleton />
        <MatchCardSkeleton />
        <MatchCardSkeleton />
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Error state — red error banner (FR-023)
  // -------------------------------------------------------------------------
  if (error !== null) {
    return <ErrorBanner message={error.message} />;
  }

  // -------------------------------------------------------------------------
  // Empty state — no results (FR-027)
  // -------------------------------------------------------------------------
  if (matches.length === 0) {
    return <EmptyState />;
  }

  // -------------------------------------------------------------------------
  // Results list
  // -------------------------------------------------------------------------
  const isTruncated = totalCount > matches.length;

  return (
    <div className="space-y-4">
      {/* Selection header — only rendered when select/deselect callbacks are provided (T023) */}
      {onSelectAll !== undefined && onDeselectAll !== undefined && (
        <SelectionHeader
          selectedCount={selectedIds.size}
          totalCount={matches.length}
          onSelectAll={onSelectAll}
          onDeselectAll={onDeselectAll}
        />
      )}

      {/* Truncation warning banner (FR-004) */}
      {isTruncated && (
        <TruncationBanner shown={matches.length} total={totalCount} />
      )}

      {/* Match cards */}
      <fieldset className="border-0 p-0 m-0">
        <legend className="sr-only">
          Select segments to correct — {matches.length} match{matches.length !== 1 ? 'es' : ''} found
        </legend>
        <ul
          role="list"
          aria-label={`${matches.length} preview match${matches.length !== 1 ? 'es' : ''}`}
          className="space-y-3"
        >
          {matches.map((match, index) => {
            const matchStatus = statusMap?.get(match.segment_id);
            // FR-015: Detect whether the next match shares the same non-null pair_id.
            // If so, an amber connector is rendered after this card's <li>.
            const nextMatch = matches[index + 1];
            const showConnector =
              match.pair_id !== null &&
              nextMatch !== undefined &&
              nextMatch.pair_id === match.pair_id;
            return (
              // React.Fragment with key so React reconciles the pair (card + optional connector)
              // as a single keyed unit without introducing a wrapper DOM element.
              <Fragment key={match.segment_id}>
                <li>
                  <MatchCard
                    match={match}
                    isSelected={selectedIds.has(match.segment_id)}
                    onToggleSelect={onToggleSelect}
                    {...(matchStatus !== undefined && { status: matchStatus })}
                  />
                </li>
                {/* Amber cross-segment boundary connector (FR-015) */}
                {showConnector && (
                  <li aria-hidden="true" className="flex justify-center -my-1">
                    <div className="flex flex-col items-center">
                      <div className="w-px h-3 bg-amber-400" />
                      <span className="text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                        Cross-segment match
                      </span>
                      <div className="w-px h-3 bg-amber-400" />
                    </div>
                  </li>
                )}
              </Fragment>
            );
          })}
        </ul>
      </fieldset>
    </div>
  );
}
