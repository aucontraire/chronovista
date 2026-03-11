/**
 * MatchCard Component
 *
 * Renders a single batch correction preview match as a selectable card.
 * Displays video metadata, surrounding context, and the before/after diff
 * for one transcript segment match.
 *
 * Implements:
 * - FR-017: "Previously corrected" badge when has_existing_correction is true
 * - NFR-003: Accessible checkbox with descriptive aria-label
 *
 * @see T018 in batch corrections spec
 */

import { useState } from 'react';
import { HighlightedDiff } from '../shared/HighlightedDiff';
import { VideoMetaHeader } from '../shared/VideoMetaHeader';
import type { BatchPreviewMatch } from '../../types/batchCorrections';
import { formatTimestamp } from '../../utils/formatTimestamp';

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface MatchCardProps {
  /** The preview match data to render. */
  match: BatchPreviewMatch;
  /** Whether this match is currently selected for apply. */
  isSelected: boolean;
  /** Fires when the user toggles selection, passing the segment ID. */
  onToggleSelect: (segmentId: number) => void;
  /**
   * Optional post-apply status badge.
   * Phase 4 will populate this after an apply operation completes.
   */
  status?: 'applied' | 'skipped' | 'failed';
  /**
   * Override for the checkbox aria-label.
   * When omitted the label is generated from the video title and timestamp.
   */
  checkboxAriaLabel?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MAX_CONTEXT_LENGTH = 500;

/**
 * Truncates context text to MAX_CONTEXT_LENGTH characters, keeping the end
 * closest to the match region.
 *
 * - `'before'`: keep the tail (nearest to the match), truncate the head.
 * - `'after'`:  keep the head (nearest to the match), truncate the tail.
 */
function truncateContext(text: string, position: 'before' | 'after'): string {
  if (text.length <= MAX_CONTEXT_LENGTH) return text;
  if (position === 'before') {
    // Keep the end (closer to the match), truncate the start
    return '...' + text.slice(text.length - MAX_CONTEXT_LENGTH + 3);
  }
  // Keep the start (closer to the match), truncate the end
  return text.slice(0, MAX_CONTEXT_LENGTH - 3) + '...';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Colored status badge shown after an apply operation (Phase 4).
 */
function StatusBadge({ status }: { status: 'applied' | 'skipped' | 'failed' }) {
  const config = {
    applied: {
      label: 'Applied',
      className:
        'bg-green-100 text-green-800 border border-green-200',
    },
    skipped: {
      label: 'Skipped',
      className:
        'bg-gray-100 text-gray-700 border border-gray-200',
    },
    failed: {
      label: 'Failed',
      className:
        'bg-red-100 text-red-800 border border-red-200',
    },
  } as const;

  const { label, className } = config[status];

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${className}`}
      aria-label={`Correction status: ${label}`}
    >
      {label}
    </span>
  );
}

/**
 * Amber "Previously corrected" badge shown when the segment already has a
 * pending correction record (FR-017).
 */
function PreviouslyCorrectedBadge() {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200"
      aria-label="This segment has an existing correction"
    >
      Previously corrected
    </span>
  );
}

/**
 * A single line of muted context text surrounding the match.
 * Renders a placeholder in muted italic when the context is null (start/end of
 * transcript).
 */
function ContextLine({
  text,
  position,
}: {
  text: string | null;
  position: 'before' | 'after';
}) {
  if (text === null) {
    const placeholder =
      position === 'before' ? 'Start of transcript' : 'End of transcript';
    return (
      <p
        className="text-xs text-gray-400 italic select-none"
        aria-label={placeholder}
      >
        {placeholder}
      </p>
    );
  }

  const displayText = truncateContext(text, position);
  return (
    <p className="text-xs text-gray-500 leading-relaxed break-words">
      {displayText}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * MatchCard displays a single preview match with its video context, an
 * accessible selection checkbox, an optional "Previously corrected" badge,
 * surrounding context text, and the HighlightedDiff for the change preview.
 *
 * @example
 * ```tsx
 * <MatchCard
 *   match={previewMatch}
 *   isSelected={selectedIds.has(previewMatch.segment_id)}
 *   onToggleSelect={(id) => toggleSelection(id)}
 * />
 * ```
 */
export function MatchCard({
  match,
  isSelected,
  onToggleSelect,
  status,
  checkboxAriaLabel,
}: MatchCardProps) {
  const {
    segment_id,
    video_id,
    video_title,
    channel_title,
    start_time,
    current_text,
    proposed_text,
    match_start,
    match_end,
    context_before,
    context_after,
    has_existing_correction,
    deep_link_url,
  } = match;

  const [isDiffExpanded, setIsDiffExpanded] = useState(false);

  // Build the default aria-label from match data when none is supplied.
  const resolvedAriaLabel =
    checkboxAriaLabel ??
    `Select correction for ${video_title} at ${formatTimestamp(start_time)}`;

  return (
    <article
      className="bg-white rounded-xl border border-gray-200 shadow-sm transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2"
      aria-label={`Match in ${video_title}`}
    >
      <div className="flex gap-4 p-4 sm:p-5">

        {/* Checkbox column — the label wrapper expands the touch target to
            meet WCAG 2.5.8 (44×44 px minimum). The visible checkbox stays 4×4
            (16 px) but the entire label area is clickable and tabbable. */}
        <div className="flex-shrink-0 flex items-center">
          <label
            className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] cursor-pointer -m-2 p-2"
          >
            {/* aria-label on the input provides the accessible name; the label
                element expands the click/touch target to meet WCAG 2.5.8. */}
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelect(segment_id)}
              aria-label={resolvedAriaLabel}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 cursor-pointer"
            />
          </label>
        </div>

        {/* Card body */}
        <div className="flex-1 min-w-0 space-y-3">

          {/* Header row: video meta + badges */}
          <div className="flex flex-wrap items-start justify-between gap-2">
            <VideoMetaHeader
              videoId={video_id}
              videoTitle={video_title}
              channelTitle={channel_title}
              startTime={start_time}
              deepLinkUrl={deep_link_url}
              className="flex-1 min-w-0"
            />

            {/* Badge group — right-aligned */}
            <div className="flex flex-wrap items-center gap-1.5 flex-shrink-0">
              {has_existing_correction && <PreviouslyCorrectedBadge />}
              {status !== undefined && <StatusBadge status={status} />}
            </div>
          </div>

          {/* Context before */}
          <ContextLine text={context_before} position="before" />

          {/* Mobile diff toggle — hidden on desktop.
              min-h/min-w ensures WCAG 2.5.8 44×44 px touch target. */}
          <button
            type="button"
            onClick={() => setIsDiffExpanded(prev => !prev)}
            aria-expanded={isDiffExpanded}
            className="sm:hidden inline-flex items-center min-h-[44px] min-w-[44px] text-xs text-blue-600 font-medium hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-2"
          >
            {isDiffExpanded ? 'Hide changes' : 'Show changes'}
          </button>

          {/* Diff block — collapsed on mobile by default, always visible on desktop */}
          <div className={isDiffExpanded ? 'block' : 'hidden sm:block'}>
            <HighlightedDiff
              currentText={current_text}
              proposedText={proposed_text}
              matchStart={match_start}
              matchEnd={match_end}
            />
          </div>

          {/* Context after */}
          <ContextLine text={context_after} position="after" />
        </div>
      </div>
    </article>
  );
}
