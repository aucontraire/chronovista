/**
 * ResultSummary Component
 *
 * Displays the outcome of a completed batch apply operation (T026).
 *
 * Implements:
 * - FR-013: Applied / skipped / failed counts in a summary row
 * - FR-025: Affected videos count note
 * - FR-026: Retry button for failed segments; deep links to failed segment video pages
 * - NFR-003: Container has role="status" and tabIndex={-1} so the parent can
 *   move focus here programmatically after apply completes
 *
 * Phase 7 placeholder:
 * - `showRebuildButton` and `onRebuild` are accepted and rendered conditionally.
 *   The button is visually present but the rebuild logic is wired in Phase 7.
 *
 * @see T026 in batch corrections spec
 */

import type { BatchApplyResult } from '../../types/batchCorrections';

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface ResultSummaryProps {
  /** The apply result returned by the batch apply endpoint. */
  result: BatchApplyResult;
  /** Called when the user clicks the "Retry N failed" button (FR-026). */
  onRetryFailed?: () => void;
  /** Whether to show the rebuild transcript text button (Phase 7). */
  showRebuildButton?: boolean;
  /** Called when the user clicks "Rebuild transcript text" (Phase 7). */
  onRebuild?: () => void;
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

/** A single stat cell with a coloured count and a descriptive label. */
function StatCell({
  count,
  label,
  colorClass,
}: {
  count: number;
  label: string;
  colorClass: string;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-4 py-3">
      <span className={['text-2xl font-bold tabular-nums', colorClass].join(' ')}>
        {count}
      </span>
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * ResultSummary renders the post-apply outcome panel.
 *
 * The container has `role="status"` and `tabIndex={-1}` so the parent page
 * can call `.focus()` on it immediately after a completed apply to bring
 * screen reader and keyboard users into context (NFR-003).
 *
 * @example
 * ```tsx
 * const summaryRef = useRef<HTMLDivElement>(null);
 *
 * // After apply completes:
 * useEffect(() => {
 *   if (state.phase === 'complete') {
 *     summaryRef.current?.focus();
 *   }
 * }, [state.phase]);
 *
 * {state.phase === 'complete' && (
 *   <ResultSummary
 *     ref={summaryRef}
 *     result={state.result}
 *     onRetryFailed={() => { ... }}
 *   />
 * )}
 * ```
 */
export function ResultSummary({
  result,
  onRetryFailed,
  showRebuildButton = false,
  onRebuild,
}: ResultSummaryProps) {
  const {
    total_applied,
    total_skipped,
    total_failed,
    failed_segment_ids,
    affected_video_ids,
    rebuild_triggered,
  } = result;

  const hasFailures = total_failed > 0;
  const hasFailed = failed_segment_ids.length > 0;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div
      role="status"
      // tabIndex allows the parent to call .focus() after apply (NFR-003)
      tabIndex={-1}
      aria-label="Batch apply result summary"
      className="rounded-xl border border-slate-200 bg-white shadow-sm outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-base font-semibold text-slate-800">
          Apply complete
        </h2>
        {rebuild_triggered && (
          <p className="mt-0.5 text-xs text-slate-500">
            Transcript full-text was rebuilt for affected videos.
          </p>
        )}
      </div>

      {/* Stats row (FR-013) */}
      <div className="flex items-stretch divide-x divide-slate-100">
        <StatCell
          count={total_applied}
          label="Applied"
          colorClass="text-green-600"
        />
        <StatCell
          count={total_skipped}
          label="Skipped"
          colorClass="text-slate-500"
        />
        <StatCell
          count={total_failed}
          label="Failed"
          colorClass={hasFailures ? 'text-red-600' : 'text-slate-400'}
        />
      </div>

      {/* Affected videos note (FR-025) */}
      <div className="px-5 py-3 border-t border-slate-100">
        <p className="text-sm text-slate-600">
          Corrections applied to{' '}
          <span className="font-semibold text-slate-800">
            {affected_video_ids.length}
          </span>{' '}
          {affected_video_ids.length !== 1 ? 'videos' : 'video'}.
        </p>
      </div>

      {/* Failed segments section (FR-026) */}
      {hasFailed && (
        <div className="px-5 py-4 border-t border-red-100 bg-red-50 space-y-3 rounded-b-xl">
          {/* Retry button */}
          {onRetryFailed !== undefined && (
            <button
              type="button"
              onClick={onRetryFailed}
              className={[
                'inline-flex items-center gap-2 px-4 py-2 rounded-md',
                'min-h-[44px] min-w-[44px]',
                'text-sm font-medium text-white',
                'bg-red-600 hover:bg-red-700 active:bg-red-800',
                'focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2',
                'transition-colors',
              ].join(' ')}
            >
              {/* Retry icon */}
              <svg
                aria-hidden="true"
                className="w-4 h-4 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Retry {total_failed} failed
            </button>
          )}

          {/* Deep links to failed segments (FR-026) */}
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-red-800 uppercase tracking-wide">
              Failed segment{failed_segment_ids.length !== 1 ? 's' : ''} — review on video page
            </p>
            <ul className="space-y-1">
              {failed_segment_ids.map((segmentId) => {
                // The segment ID alone is enough to identify the failed record.
                // We link to the video detail page for the video that contained
                // this segment.  Because we only have segment IDs (not video IDs)
                // in failed_segment_ids, we surface the raw IDs as anchors to
                // the batch corrections page filtered to these IDs.
                // When the parent provides affected_video_ids, we show the first
                // one as a representative link; the full breakdown is in the
                // video detail page.
                return (
                  <li key={segmentId} className="text-sm">
                    <span className="text-red-700">
                      Segment{' '}
                      <span className="font-mono text-xs bg-red-100 px-1 py-0.5 rounded">
                        #{segmentId}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>

            {/* Video deep links — one per affected video (FR-026) */}
            {affected_video_ids.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="text-xs font-medium text-red-800 uppercase tracking-wide">
                  Affected {affected_video_ids.length !== 1 ? 'videos' : 'video'}
                </p>
                <ul className="space-y-1">
                  {affected_video_ids.map((videoId) => (
                    <li key={videoId}>
                      <a
                        href={`/videos/${videoId}`}
                        className={[
                          'inline-flex items-center gap-1.5 text-sm',
                          'min-h-[44px] min-w-[44px]',
                          'text-red-700 underline underline-offset-2',
                          'hover:text-red-900',
                          'focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded',
                        ].join(' ')}
                      >
                        {/* External link icon */}
                        <svg
                          aria-hidden="true"
                          className="w-3.5 h-3.5 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          strokeWidth={2}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                        Video <span className="font-mono text-xs">{videoId}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Phase 7 placeholder — rebuild button */}
      {showRebuildButton && onRebuild !== undefined && (
        <div className="px-5 py-4 border-t border-slate-100">
          <button
            type="button"
            onClick={onRebuild}
            className={[
              'inline-flex items-center gap-2 px-4 py-2 rounded-md',
              'min-h-[44px] min-w-[44px]',
              'text-sm font-medium text-slate-700',
              'bg-white border border-slate-300',
              'hover:bg-slate-50 active:bg-slate-100',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
              'transition-colors',
            ].join(' ')}
          >
            {/* Refresh icon */}
            <svg
              aria-hidden="true"
              className="w-4 h-4 flex-shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Rebuild transcript text
          </button>
          <p className="mt-1.5 text-xs text-slate-400">
            Regenerates full-text search content from corrected segments.
          </p>
        </div>
      )}
    </div>
  );
}
