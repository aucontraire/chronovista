/**
 * TranscriptSegments component for displaying transcript segments with infinite scroll.
 *
 * Implements:
 * - FR-018: Timestamped segments with timestamp on left, text on right
 * - FR-020c-f: Infinite scroll with trigger 200px from bottom
 * - FR-020d: 3 skeleton segments during loading
 * - FR-020e: "End of transcript" indicator
 * - FR-020f: User can scroll during loading
 * - FR-025a-d: Error handling with retry and segment preservation
 * - NFR-A11-A15: Keyboard scrolling and accessibility
 * - NFR-P12-P16: Virtualization for 500+ segments
 * - NFR-R06: Responsive text sizing
 * - Feature 035 (T023): Inline correction edit mode
 *   - US-4: Inline editing with validation
 *   - US-8: Screen reader announcements for correction state
 *   - US-10: Optimistic update feedback
 *   - NFR-003: Virtualizer height notification on edit mode toggle
 *   - NFR-004: Motion preferences for transition animations
 *
 * @module components/transcript/TranscriptSegments
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import { useTranscriptSegments } from "../../hooks/useTranscriptSegments";
import { useCorrectSegment } from "../../hooks/useCorrectSegment";
import { useRevertSegment } from "../../hooks/useRevertSegment";
import { useSegmentCorrectionHistory } from "../../hooks/useSegmentCorrectionHistory";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { formatTimestamp } from "../../utils/formatTimestamp";
import {
  INFINITE_SCROLL_CONFIG,
  VIRTUALIZATION_CONFIG,
  RESPONSIVE_CONFIG,
  CONTRAST_SAFE_COLORS,
} from "../../styles/tokens";
import type { TranscriptSegment } from "../../types/transcript";
import type {
  SegmentEditState,
  CorrectionType,
  CorrectionAuditRecord,
} from "../../types/corrections";
import {
  CorrectionBadge,
  SegmentEditForm,
  RevertConfirmation,
  CorrectionHistoryPanel,
} from "./corrections";

/**
 * Props for the TranscriptSegments component.
 */
export interface TranscriptSegmentsProps {
  /** The YouTube video ID */
  videoId: string;
  /** BCP-47 language code for the transcript */
  languageCode: string;
  /** Callback when scroll position resets (e.g., on view mode change) */
  onScrollPositionReset?: () => void;
  /** Segment ID to scroll to and highlight (FR-005) */
  targetSegmentId?: number | undefined;
  /** Timestamp fallback for scroll in seconds (FR-006) */
  targetTimestamp?: number | undefined;
  /** Callback when deep link navigation completes (FR-011) */
  onDeepLinkComplete?: (() => void) | undefined;
  /** Whether the parent panel is expanded (for deep link abort on collapse) */
  isExpanded?: boolean | undefined;
}

/**
 * Shared edit mode props threaded through SegmentItem, StandardSegmentList, and VirtualizedSegmentList.
 */
interface EditModeProps {
  editState: SegmentEditState;
  isPending: boolean;
  correctionError: string | null;
  onEdit: (segmentId: number) => void;
  onSave: (data: {
    corrected_text: string;
    correction_type: CorrectionType;
    correction_note: string | null;
  }) => void;
  onCancel: () => void;
  editButtonRef: React.RefObject<HTMLButtonElement | null>;
  // Revert workflow props (T026)
  revertIsPending: boolean;
  onRevert: (segmentId: number) => void;
  onRevertConfirm: () => void;
  onRevertCancel: () => void;
  revertButtonRef: React.RefObject<HTMLButtonElement | null>;
  // History panel props (T027-T029)
  onHistory: (segmentId: number) => void;
  onHistoryClose: () => void;
  onHistoryLoadMore: () => void;
  historyRecords: CorrectionAuditRecord[];
  historyIsLoading: boolean;
  historyHasMore: boolean;
  historyButtonRef: React.RefObject<HTMLButtonElement | null>;
}

/**
 * SegmentItem component renders a single transcript segment.
 *
 * Supports optional highlight state for deep link navigation (FR-008, FR-009, FR-015).
 * Supports inline edit mode (Feature 035): shows SegmentEditForm when this segment is active.
 */
function SegmentItem({
  segment,
  isVirtualized,
  isHighlighted,
  highlightTransitionClass,
  editState,
  isPending,
  correctionError,
  onEdit,
  onSave,
  onCancel,
  editButtonRef,
  revertIsPending,
  onRevert,
  onRevertConfirm,
  onRevertCancel,
  revertButtonRef,
  onHistory,
  onHistoryClose,
  onHistoryLoadMore,
  historyRecords,
  historyIsLoading,
  historyHasMore,
  historyButtonRef,
}: {
  segment: TranscriptSegment;
  isVirtualized: boolean;
  isHighlighted?: boolean;
  highlightTransitionClass?: string;
} & EditModeProps) {
  const isEditing =
    editState.mode === "editing" && editState.segmentId === segment.id;
  const isConfirmingRevert =
    editState.mode === "confirming-revert" && editState.segmentId === segment.id;
  const isHistory =
    editState.mode === "history" && editState.segmentId === segment.id;

  // Highlight styles: yellow background with left border indicator (FR-008)
  const highlightClasses = isHighlighted
    ? "bg-yellow-100 border-l-4 border-yellow-400"
    : "border-l-4 border-transparent";

  return (
    <div>
      {/* Segment row */}
      <div
        className={`group flex gap-4 py-2 hover:bg-slate-50 ${isVirtualized ? "px-2" : ""} ${highlightClasses} ${highlightTransitionClass ?? ""}`}
        data-segment-id={segment.id}
        // FR-015: Make highlighted segment focusable for programmatic focus
        tabIndex={isHighlighted ? -1 : undefined}
        // US-10: Indicate when a mutation is in-flight on this segment
        aria-busy={
          (isEditing && isPending) || (isConfirmingRevert && revertIsPending)
            ? "true"
            : undefined
        }
      >
        {/* Timestamp - left side (NFR-A17, NFR-A18: text-gray-600 for 7.0:1 contrast) */}
        <span
          className={`flex-shrink-0 w-16 ${CONTRAST_SAFE_COLORS.timestamp} font-mono ${RESPONSIVE_CONFIG.segmentTextSize.mobile} lg:${RESPONSIVE_CONFIG.segmentTextSize.desktop}`}
        >
          {formatTimestamp(segment.start_time)}
        </span>

        {/* Content area: edit form, revert confirmation, or normal read view */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            /* Inline edit form when this segment is in edit mode */
            <SegmentEditForm
              initialText={segment.text}
              segmentId={segment.id}
              isPending={isPending}
              onSave={onSave}
              onCancel={onCancel}
              serverError={correctionError}
            />
          ) : isConfirmingRevert ? (
            /* Inline revert confirmation row — shown instead of text when confirming revert */
            <RevertConfirmation
              isPending={revertIsPending}
              onConfirm={onRevertConfirm}
              onCancel={onRevertCancel}
            />
          ) : (
            /* Normal read view */
            <div className="flex items-start gap-2">
              <p
                className={`flex-1 ${CONTRAST_SAFE_COLORS.bodyText} ${RESPONSIVE_CONFIG.segmentTextSize.mobile} lg:${RESPONSIVE_CONFIG.segmentTextSize.desktop}`}
              >
                {segment.text}
              </p>

              {/* Correction badge — renders only when segment has an active correction (Feature 035) */}
              <CorrectionBadge
                hasCorrection={segment.has_correction}
                correctionCount={segment.correction_count}
                correctedAt={segment.corrected_at}
              />
            </div>
          )}
        </div>

        {/* Action buttons — visible on hover/focus-within, hidden during edit or confirming-revert mode */}
        {!isEditing && !isConfirmingRevert && (
          <>
            {/* Edit button */}
            <button
              ref={editState.mode === "read" ? editButtonRef : undefined}
              type="button"
              onClick={() => onEdit(segment.id)}
              title="Edit segment"
              aria-label={`Edit segment ${segment.id}`}
              className="
                opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
                flex-shrink-0 p-1 text-slate-500 hover:text-slate-700 hover:bg-slate-100
                rounded focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:opacity-100
                transition-opacity
              "
            >
              {/* Pencil icon */}
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                />
              </svg>
            </button>

            {/* Revert button — only visible when the segment has an active correction */}
            {segment.has_correction && (
              <button
                ref={editState.mode === "read" ? revertButtonRef : undefined}
                type="button"
                onClick={() => onRevert(segment.id)}
                title="Revert to previous version"
                aria-label={`Revert correction for segment ${segment.id}`}
                className="
                  opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
                  flex-shrink-0 p-1 text-slate-500 hover:text-slate-700 hover:bg-slate-100
                  rounded focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:opacity-100
                  transition-opacity
                "
              >
                {/* Undo/revert arrow icon */}
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 10h10a5 5 0 0 1 0 10H9M3 10l4-4M3 10l4 4"
                  />
                </svg>
              </button>
            )}

            {/* History button — only visible when segment has recorded corrections */}
            {segment.correction_count > 0 && (
              <button
                ref={editState.mode === "read" ? historyButtonRef : undefined}
                type="button"
                onClick={() => onHistory(segment.id)}
                title="View correction history"
                aria-label={`View correction history for segment ${segment.id}`}
                className="
                  opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
                  flex-shrink-0 p-1 text-slate-500 hover:text-slate-700 hover:bg-slate-100
                  rounded focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:opacity-100
                  transition-opacity
                "
              >
                {/* Clock/history icon */}
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </button>
            )}
          </>
        )}
      </div>

      {/* History panel — renders below the segment row, segment text stays visible */}
      {isHistory && (
        <CorrectionHistoryPanel
          records={historyRecords}
          isLoading={historyIsLoading}
          hasMore={historyHasMore}
          onLoadMore={onHistoryLoadMore}
          onClose={onHistoryClose}
        />
      )}
    </div>
  );
}

/**
 * SkeletonSegment component renders a loading placeholder segment.
 */
function SkeletonSegment() {
  return (
    <div className="flex gap-4 py-2 animate-pulse" aria-hidden="true">
      {/* Skeleton timestamp */}
      <div className="flex-shrink-0 w-16 h-5 bg-gray-200 rounded" />
      {/* Skeleton text (random width for visual variety) */}
      <div className="flex-1 h-5 bg-gray-200 rounded" style={{ width: "85%" }} />
    </div>
  );
}

/**
 * EndOfTranscript indicator shown when all segments are loaded.
 */
function EndOfTranscript() {
  return (
    <div
      className="flex justify-center py-4 text-sm text-gray-500"
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-2">
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
        End of transcript
      </span>
    </div>
  );
}

/**
 * ErrorRetry component for displaying inline retry option on partial failure.
 */
function ErrorRetry({
  onRetry,
  hasLoadedSegments,
}: {
  onRetry: () => void;
  hasLoadedSegments: boolean;
}) {
  return (
    <div
      className="flex flex-col items-center gap-3 py-4 px-4 bg-red-50 border border-red-200 rounded-lg mx-2"
      role="alert"
      aria-live="polite"
    >
      <p className="text-sm text-red-800">
        {hasLoadedSegments
          ? "Could not load more segments."
          : "Could not load transcript segments."}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="px-4 py-2 text-sm font-medium text-red-800 bg-white border border-red-300 rounded-md hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
      >
        Retry
      </button>
    </div>
  );
}

/**
 * VirtualizedSegmentList component for rendering 500+ segments efficiently.
 *
 * Uses @tanstack/react-virtual for windowed rendering (NFR-P12-P16).
 * When a segment enters/exits edit mode, the virtual item wrapper uses a ref callback
 * so the virtualizer can re-measure the item's height (NFR-003).
 */
function VirtualizedSegmentList({
  segments,
  containerRef,
  onScroll,
  highlightedSegmentId,
  highlightTransitionClass,
  editModeProps,
}: {
  segments: TranscriptSegment[];
  containerRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  highlightedSegmentId: number | null;
  highlightTransitionClass: string;
  editModeProps: EditModeProps;
}) {
  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => VIRTUALIZATION_CONFIG.estimatedHeight, // NFR-P15: 48px
    overscan: VIRTUALIZATION_CONFIG.overscan, // NFR-P14: 5 segments
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      style={{
        height: `${virtualizer.getTotalSize()}px`,
        width: "100%",
        position: "relative",
      }}
      onScroll={onScroll}
    >
      {virtualItems.map((virtualItem) => {
        const segment = segments[virtualItem.index];
        if (!segment) return null;

        const isHighlighted = segment.id === highlightedSegmentId;

        return (
          <div
            key={virtualItem.key}
            // NFR-003: ref callback so the virtualizer re-measures on edit mode toggle
            ref={(el) => {
              if (el) virtualizer.measureElement(el);
            }}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${virtualItem.start}px)`,
            }}
          >
            <SegmentItem
              segment={segment}
              isVirtualized={true}
              isHighlighted={isHighlighted}
              highlightTransitionClass={isHighlighted ? highlightTransitionClass : ""}
              {...editModeProps}
            />
          </div>
        );
      })}
    </div>
  );
}

/**
 * StandardSegmentList component for rendering segments without virtualization.
 */
function StandardSegmentList({
  segments,
  highlightedSegmentId,
  highlightTransitionClass,
  editModeProps,
}: {
  segments: TranscriptSegment[];
  highlightedSegmentId: number | null;
  highlightTransitionClass: string;
  editModeProps: EditModeProps;
}) {
  return (
    <>
      {segments.map((segment) => {
        const isHighlighted = segment.id === highlightedSegmentId;
        return (
          <SegmentItem
            key={segment.id}
            segment={segment}
            isVirtualized={false}
            isHighlighted={isHighlighted}
            highlightTransitionClass={isHighlighted ? highlightTransitionClass : ""}
            {...editModeProps}
          />
        );
      })}
    </>
  );
}

/**
 * Finds the index of the segment nearest to the target timestamp.
 * Returns the index of the segment with the smallest absolute start_time difference.
 *
 * @param segments - Array of transcript segments
 * @param targetTimestamp - Target timestamp in seconds
 * @returns Index of nearest segment, or null if no segments available
 */
function findNearestSegmentByTimestamp(
  segments: TranscriptSegment[],
  targetTimestamp: number
): number | null {
  if (segments.length === 0) return null;

  let nearestIndex = 0;
  const firstSegment = segments[0];
  if (!firstSegment) return null;

  let smallestDiff = Math.abs(firstSegment.start_time - targetTimestamp);

  for (let i = 1; i < segments.length; i++) {
    const segment = segments[i];
    if (!segment) continue;

    const diff = Math.abs(segment.start_time - targetTimestamp);
    if (diff < smallestDiff) {
      smallestDiff = diff;
      nearestIndex = i;
    }
  }

  return nearestIndex;
}

/**
 * TranscriptSegments displays transcript segments with infinite scroll and virtualization.
 *
 * Features:
 * - Timestamped display with timestamp on left, text on right (FR-018)
 * - Infinite scroll triggered 200px from bottom (FR-020c)
 * - 3 skeleton segments during loading (FR-020d)
 * - "End of transcript" indicator when all loaded (FR-020e)
 * - User can scroll during loading (FR-020f)
 * - Virtualization for 500+ segments using @tanstack/react-virtual (NFR-P12-P16)
 * - Keyboard scrolling: Arrow Up/Down, Page Up/Down, Home/End (NFR-A11-A14)
 * - Accessible container with tabindex, role, aria-label (NFR-A15)
 * - Responsive text sizing: text-sm mobile, text-base desktop (NFR-R06)
 * - Error handling with retry button and segment preservation (FR-025a-d)
 * - Inline correction editing with optimistic update (Feature 035)
 *
 * @example
 * ```tsx
 * <TranscriptSegments
 *   videoId="dQw4w9WgXcQ"
 *   languageCode="en"
 *   onScrollPositionReset={() => console.log('Scroll reset')}
 * />
 * ```
 */
export function TranscriptSegments({
  videoId,
  languageCode,
  onScrollPositionReset,
  targetSegmentId,
  targetTimestamp,
  onDeepLinkComplete,
  isExpanded = true,
}: TranscriptSegmentsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const previousLanguageRef = useRef<string>(languageCode);

  // Deep link highlight state (FR-008)
  const [highlightedSegmentId, setHighlightedSegmentId] = useState<number | null>(null);

  // Screen reader announcement for deep link navigation (FR-010)
  const [deepLinkAnnouncement, setDeepLinkAnnouncement] = useState("");

  // Track whether deep link scroll has been completed to prevent re-triggering
  const deepLinkCompletedRef = useRef(false);

  // Track fetch-until-found iteration count for deep link navigation (FR-006)
  const fetchIterationRef = useRef(0);

  // Track whether a targeted deep link seek has been attempted
  const deepLinkSeekAttemptedRef = useRef(false);

  // Track whether a targeted seek is currently in-flight
  const [deepLinkSeeking, setDeepLinkSeeking] = useState(false);

  // Reduced motion preference for highlight animation (FR-009) and segment transitions (NFR-004)
  const prefersReducedMotion = usePrefersReducedMotion();

  // --- Feature 035: Edit mode state ---

  /** Current edit state — controls which segment (if any) shows an inline form */
  const [editState, setEditState] = useState<SegmentEditState>({ mode: "read" });

  /** Screen reader announcement for correction submission (US-8) */
  const [correctionAnnouncement, setCorrectionAnnouncement] = useState("");

  /** Server-side error message to surface inside SegmentEditForm (US-4) */
  const [correctionError, setCorrectionError] = useState<string | null>(null);

  /** Ref to the edit button of the segment that most recently exited edit mode */
  const editButtonRef = useRef<HTMLButtonElement>(null);

  /** Ref to the revert button for focus restoration after revert cancel (T026) */
  const revertButtonRef = useRef<HTMLButtonElement>(null);

  /** Ref to the history button for focus restoration after history panel close (T029) */
  const historyButtonRef = useRef<HTMLButtonElement>(null);

  /** Pagination offset for the history panel (T029) */
  const [historyOffset, setHistoryOffset] = useState(0);

  /** Mutation hook for submitting corrections (Feature 035) */
  const correctSegment = useCorrectSegment(videoId, languageCode);

  /** Mutation hook for reverting corrections (T026) */
  const revertSegment = useRevertSegment(videoId, languageCode);

  /** Query hook for correction history panel (T029) */
  const historySegmentId =
    editState.mode === "history" ? editState.segmentId : 0;
  const historyQuery = useSegmentCorrectionHistory(
    videoId,
    languageCode,
    historySegmentId,
    {
      enabled: editState.mode === "history",
      offset: historyOffset,
    }
  );

  const {
    segments,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    isError,
    // error is available but not displayed; we use isError for conditional rendering
    fetchNextPage,
    retry,
    seekToTimestamp,
  } = useTranscriptSegments(videoId, languageCode);

  // Determine if virtualization should be used (NFR-P12)
  const useVirtualization = segments.length > VIRTUALIZATION_CONFIG.threshold;

  // Highlight transition: fade-out unless reduced motion (FR-009)
  const highlightTransitionClass = prefersReducedMotion
    ? ""
    : "transition-all duration-1000 ease-out";

  // Reset scroll position when language changes (FR-016a-c)
  useEffect(() => {
    if (previousLanguageRef.current !== languageCode) {
      if (containerRef.current) {
        containerRef.current.scrollTop = 0;
      }
      onScrollPositionReset?.();
      previousLanguageRef.current = languageCode;
    }
  }, [languageCode, onScrollPositionReset]);

  /**
   * Handles the deep link scroll, highlight, focus, and cleanup sequence.
   *
   * Flow: scroll to element -> highlight -> announce -> focus -> clear after 3s
   * (FR-005, FR-008, FR-010, FR-011, FR-015)
   */
  const handleDeepLinkScroll = useCallback(
    (targetIndex: number | null) => {
      if (deepLinkCompletedRef.current) return;
      deepLinkCompletedRef.current = true;

      if (targetIndex === null || segments.length === 0) {
        // No valid target -- clean up immediately
        onDeepLinkComplete?.();
        return;
      }

      const targetSegment = segments[targetIndex];
      if (!targetSegment) {
        onDeepLinkComplete?.();
        return;
      }

      const segmentId = targetSegment.id;

      // For virtualized lists, the target element may not exist in the DOM yet
      // because @tanstack/react-virtual only renders visible items. Pre-scroll
      // the container to the approximate position so the virtualizer renders
      // segments near the target, then refine with scrollIntoView.
      if (useVirtualization && containerRef.current) {
        containerRef.current.scrollTop =
          targetIndex * VIRTUALIZATION_CONFIG.estimatedHeight;
      }

      // Scroll to target using querySelector + scrollIntoView (FR-005, FR-013)
      // Use a longer delay for virtualized lists to allow re-render after pre-scroll
      const scrollDelay = useVirtualization ? 150 : 50;
      setTimeout(() => {
        const el = containerRef.current?.querySelector(
          `[data-segment-id="${segmentId}"]`
        );
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, scrollDelay);

      // Set highlight after scroll starts (FR-008)
      setHighlightedSegmentId(segmentId);

      // Screen reader announcement (FR-010)
      setDeepLinkAnnouncement(
        `Navigated to matched transcript segment at ${formatTimestamp(targetSegment.start_time)}`
      );

      // Focus management (FR-015) -- focus the highlighted element after scroll settles
      setTimeout(() => {
        const el = containerRef.current?.querySelector(
          `[data-segment-id="${segmentId}"]`
        ) as HTMLElement | null;
        el?.focus();
      }, 250);

      // Clear highlight after 3 seconds (FR-008, FR-009)
      setTimeout(() => {
        setHighlightedSegmentId(null);
        setDeepLinkAnnouncement("");
        onDeepLinkComplete?.(); // FR-011: triggers URL cleanup
      }, 3000);
    },
    [segments, useVirtualization, onDeepLinkComplete]
  );

  // Deep link scroll-to-segment with targeted seek and timestamp fallback (FR-005, FR-006, FR-007, FR-013)
  useEffect(() => {
    // Skip if already completed or still loading initial batch
    if (deepLinkCompletedRef.current || isLoading) return;
    // Skip if no deep link target at all
    if (!targetSegmentId && targetTimestamp == null) return;
    // Skip if no segments loaded yet
    if (segments.length === 0) return;
    // Skip if currently fetching a page — wait for it to complete
    if (isFetchingNextPage) return;
    // Skip if a targeted seek is in-flight — wait for it to complete
    if (deepLinkSeeking) return;

    // Step 1: Try to find by segment ID (if provided)
    if (targetSegmentId) {
      const targetIndex = segments.findIndex((s) => s.id === targetSegmentId);

      if (targetIndex !== -1) {
        // Found the segment — scroll to it
        handleDeepLinkScroll(targetIndex);
        return;
      }

      // Segment not found — try a few sequential pages first (FR-006)
      if (hasNextPage && fetchIterationRef.current < 3) {
        fetchIterationRef.current += 1;
        fetchNextPage();
        return;
      }

      // After 3 sequential pages, jump directly to the estimated position.
      // This avoids fetching 20+ pages sequentially for segments deep in long transcripts.
      // Only attempt seek when there are more pages available on the backend.
      if (!deepLinkSeekAttemptedRef.current && targetTimestamp != null && hasNextPage) {
        deepLinkSeekAttemptedRef.current = true;
        setDeepLinkSeeking(true);

        seekToTimestamp(targetTimestamp).finally(() => {
          setDeepLinkSeeking(false);
        });
        return;
      }

      // Seek completed or skipped — fall through to timestamp fallback
    }

    // Step 2: Timestamp fallback (FR-007)
    // Reached when: segment ID not found after seek, or only timestamp provided
    if (targetTimestamp != null) {
      const nearestIndex = findNearestSegmentByTimestamp(segments, targetTimestamp);
      if (nearestIndex !== null) {
        handleDeepLinkScroll(nearestIndex);
        return;
      }
    }

    // Step 3: No valid target — clean up
    handleDeepLinkScroll(null);
  }, [segments, targetSegmentId, targetTimestamp, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage, handleDeepLinkScroll, deepLinkSeeking, seekToTimestamp]);

  // Abort deep link on panel collapse (T017 — edge case from spec.md)
  useEffect(() => {
    if (!isExpanded && highlightedSegmentId !== null) {
      // Panel collapsed while highlight is active — abort immediately
      setHighlightedSegmentId(null);
      setDeepLinkAnnouncement("");
      deepLinkCompletedRef.current = true;
      onDeepLinkComplete?.();
    }
  }, [isExpanded, highlightedSegmentId, onDeepLinkComplete]);

  // Intersection Observer for infinite scroll (FR-020c)
  useEffect(() => {
    const loadMoreElement = loadMoreRef.current;
    if (!loadMoreElement || !hasNextPage || isFetchingNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          fetchNextPage();
        }
      },
      {
        root: containerRef.current,
        // FR-020c: Trigger 200px from bottom
        rootMargin: `0px 0px ${INFINITE_SCROLL_CONFIG.triggerDistance}px 0px`,
        threshold: 0,
      }
    );

    observer.observe(loadMoreElement);

    return () => {
      observer.disconnect();
    };
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Keyboard navigation handler (NFR-A11-A14)
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const container = containerRef.current;
      if (!container) return;

      const segmentHeight = VIRTUALIZATION_CONFIG.estimatedHeight; // ~48px
      const viewportHeight = container.clientHeight;

      switch (event.key) {
        case "ArrowUp":
          // NFR-A12: Scroll up by one segment
          event.preventDefault();
          container.scrollBy({ top: -segmentHeight, behavior: "smooth" });
          break;

        case "ArrowDown":
          // NFR-A12: Scroll down by one segment
          event.preventDefault();
          container.scrollBy({ top: segmentHeight, behavior: "smooth" });
          break;

        case "PageUp":
          // NFR-A13: Scroll up by viewport height
          event.preventDefault();
          container.scrollBy({ top: -viewportHeight, behavior: "smooth" });
          break;

        case "PageDown":
          // NFR-A13: Scroll down by viewport height
          event.preventDefault();
          container.scrollBy({ top: viewportHeight, behavior: "smooth" });
          break;

        case "Home":
          // NFR-A14: Scroll to beginning
          event.preventDefault();
          container.scrollTo({ top: 0, behavior: "smooth" });
          break;

        case "End":
          // NFR-A14: Scroll to end
          event.preventDefault();
          container.scrollTo({
            top: container.scrollHeight,
            behavior: "smooth",
          });
          break;
      }
    },
    []
  );

  // Handle scroll for manual infinite scroll trigger (fallback)
  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container || !hasNextPage || isFetchingNextPage) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    // FR-020c: Trigger 200px from bottom
    if (distanceFromBottom < INFINITE_SCROLL_CONFIG.triggerDistance) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // --- Feature 035: Edit mode handlers ---

  /**
   * Enters edit mode for a segment.
   * Single-edit constraint: setEditState replaces the entire state,
   * so entering edit on segment B automatically cancels segment A.
   */
  const handleEdit = useCallback((segmentId: number) => {
    setEditState({ mode: "editing", segmentId });
    setCorrectionError(null);
    // US-8: Announce edit mode entry to screen readers
    setCorrectionAnnouncement("Editing segment. Press Escape to cancel.");
    // Clear the announcement after 3s so the same message can be re-announced on next edit
    setTimeout(() => setCorrectionAnnouncement(""), 3000);
  }, []);

  /**
   * Submits a correction via the mutation hook.
   * On success: returns to read mode and focuses the edit button.
   * On error: surfaces the error message inside SegmentEditForm via correctionError state.
   */
  const handleSave = useCallback(
    (data: {
      corrected_text: string;
      correction_type: CorrectionType;
      correction_note: string | null;
    }) => {
      if (editState.mode !== "editing") return;

      correctSegment.mutate(
        { segmentId: editState.segmentId, ...data },
        {
          onSuccess: () => {
            setEditState({ mode: "read" });
            setCorrectionError(null);
            // US-8: Announce successful save
            setCorrectionAnnouncement("Correction saved.");
            setTimeout(() => setCorrectionAnnouncement(""), 3000);
            // Return focus to the edit button after state update settles
            setTimeout(() => editButtonRef.current?.focus(), 0);
          },
          onError: (error) => {
            const message =
              error instanceof Error
                ? error.message
                : "Failed to save correction.";
            setCorrectionError(message);
            // US-8: Announce the error assertively
            setCorrectionAnnouncement(message);
            setTimeout(() => setCorrectionAnnouncement(""), 3000);
          },
        }
      );
    },
    [editState, correctSegment]
  );

  /**
   * Cancels the current edit, returns to read mode, and restores focus to the edit button.
   */
  const handleCancel = useCallback(() => {
    setEditState({ mode: "read" });
    setCorrectionError(null);
    setCorrectionAnnouncement("");
    setTimeout(() => editButtonRef.current?.focus(), 0);
  }, []);

  // --- Feature 035 (T026): Revert workflow handlers ---

  /**
   * Enters confirming-revert mode for a segment.
   * Cancels any other active mode on any other segment (same single-action constraint).
   */
  const handleRevert = useCallback((segmentId: number) => {
    setEditState({ mode: "confirming-revert", segmentId });
    setCorrectionError(null);
    // US-8: Announce revert confirmation request to screen readers
    setCorrectionAnnouncement("Revert correction? Press Escape to cancel.");
    setTimeout(() => setCorrectionAnnouncement(""), 3000);
  }, []);

  /**
   * Executes the revert mutation after user confirms.
   * On success: returns to read mode, announces result, focuses edit button.
   * On error: announces error, auto-dismisses after 4 seconds (per spec).
   */
  const handleRevertConfirm = useCallback(() => {
    if (editState.mode !== "confirming-revert") return;
    const { segmentId } = editState;

    revertSegment.mutate(
      { segmentId },
      {
        onSuccess: () => {
          setEditState({ mode: "read" });
          setCorrectionError(null);
          // US-8: Announce successful revert
          setCorrectionAnnouncement("Correction reverted.");
          setTimeout(() => setCorrectionAnnouncement(""), 3000);
          // Focus edit button — revert button may no longer exist after revert clears has_correction
          setTimeout(() => editButtonRef.current?.focus(), 0);
        },
        onError: (error) => {
          const message =
            error instanceof Error
              ? error.message
              : "Failed to revert correction.";
          setCorrectionError(message);
          // US-8: Announce the error assertively
          setCorrectionAnnouncement(message);
          setTimeout(() => setCorrectionAnnouncement(""), 3000);
          // Auto-dismiss error and return to read after 4 seconds (per spec)
          setTimeout(() => {
            setCorrectionError(null);
            setEditState({ mode: "read" });
          }, 4000);
        },
      }
    );
  }, [editState, revertSegment]);

  /**
   * Cancels the revert confirmation, returns to read mode, and restores focus to the revert button.
   */
  const handleRevertCancel = useCallback(() => {
    setEditState({ mode: "read" });
    setCorrectionAnnouncement("");
    // Restore focus to the revert button so keyboard users don't lose their place
    setTimeout(() => revertButtonRef.current?.focus(), 0);
  }, []);

  // --- Feature 035 (T029): History panel handlers ---

  /**
   * Opens the correction history panel for the given segment.
   * Resets the pagination offset and announces the action to screen readers.
   */
  const handleHistory = useCallback((segmentId: number) => {
    setEditState({ mode: "history", segmentId });
    setHistoryOffset(0);
    // US-8: Announce history loading to screen readers
    setCorrectionAnnouncement("Loading correction history...");
    setTimeout(() => setCorrectionAnnouncement(""), 3000);
  }, []);

  /**
   * Closes the history panel and restores focus to the history button.
   */
  const handleHistoryClose = useCallback(() => {
    setEditState({ mode: "read" });
    setCorrectionAnnouncement("");
    setTimeout(() => historyButtonRef.current?.focus(), 0);
  }, []);

  /**
   * Loads the next page of history records by incrementing the offset.
   */
  const handleHistoryLoadMore = useCallback(() => {
    setHistoryOffset((prev) => prev + 50);
  }, []);

  // Announce history data when it loads (US-8)
  useEffect(() => {
    if (editState.mode !== "history") return;
    if (!historyQuery.data) return;

    const count = historyQuery.data.data.length;
    const noun = count === 1 ? "record" : "records";
    setCorrectionAnnouncement(
      `Correction history opened. ${count} ${noun}.`
    );
    setTimeout(() => setCorrectionAnnouncement(""), 3000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyQuery.data]);

  /** Bundle edit mode props to pass through list components to SegmentItem */
  const editModeProps: EditModeProps = {
    editState,
    isPending: correctSegment.isPending,
    correctionError,
    onEdit: handleEdit,
    onSave: handleSave,
    onCancel: handleCancel,
    editButtonRef,
    revertIsPending: revertSegment.isPending,
    onRevert: handleRevert,
    onRevertConfirm: handleRevertConfirm,
    onRevertCancel: handleRevertCancel,
    revertButtonRef,
    // History panel props (T029)
    onHistory: handleHistory,
    onHistoryClose: handleHistoryClose,
    onHistoryLoadMore: handleHistoryLoadMore,
    historyRecords: historyQuery.data?.data ?? [],
    historyIsLoading: historyQuery.isLoading,
    historyHasMore: historyQuery.data?.pagination.has_more ?? false,
    historyButtonRef,
  };

  // Initial loading state
  if (isLoading && segments.length === 0) {
    return (
      <div
        className="p-2"
        role="status"
        aria-label="Loading transcript segments"
      >
        {/* FR-020d: Show 3 skeleton segments */}
        {Array.from({ length: INFINITE_SCROLL_CONFIG.skeletonCount }).map(
          (_, index) => (
            <SkeletonSegment key={index} />
          )
        )}
        <span className="sr-only">Loading transcript segments...</span>
      </div>
    );
  }

  // Error state with no segments loaded (FR-025a)
  if (isError && segments.length === 0) {
    return (
      <ErrorRetry onRetry={retry} hasLoadedSegments={false} />
    );
  }

  // No segments available
  if (segments.length === 0 && !isLoading) {
    return (
      <div className="p-4 text-center text-sm text-gray-500" role="status">
        No transcript segments available for this language.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      // NFR-A11: Focusable container
      tabIndex={0}
      // NFR-A15: Accessible region
      role="region"
      aria-label="Transcript segments"
      onKeyDown={handleKeyDown}
      onScroll={handleScroll}
      className={`
        overflow-y-auto
        focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500
        max-h-[calc(40vh-100px)] sm:max-h-[calc(50vh-100px)] lg:max-h-[calc(60vh-100px)]
      `}
    >
      {/* Segment list - virtualized or standard based on count */}
      {useVirtualization ? (
        <VirtualizedSegmentList
          segments={segments}
          containerRef={containerRef}
          onScroll={handleScroll}
          highlightedSegmentId={highlightedSegmentId}
          highlightTransitionClass={highlightTransitionClass}
          editModeProps={editModeProps}
        />
      ) : (
        <StandardSegmentList
          segments={segments}
          highlightedSegmentId={highlightedSegmentId}
          highlightTransitionClass={highlightTransitionClass}
          editModeProps={editModeProps}
        />
      )}

      {/* Loading indicator for infinite scroll (FR-020d) */}
      {isFetchingNextPage && (
        <div role="status" aria-label="Loading more segments">
          {Array.from({ length: INFINITE_SCROLL_CONFIG.skeletonCount }).map(
            (_, index) => (
              <SkeletonSegment key={`loading-${index}`} />
            )
          )}
          <span className="sr-only">Loading more segments...</span>
        </div>
      )}

      {/* Error state with loaded segments (FR-025b, FR-025d) */}
      {isError && segments.length > 0 && (
        <ErrorRetry onRetry={retry} hasLoadedSegments={true} />
      )}

      {/* End of transcript indicator (FR-020e) */}
      {!hasNextPage && !isLoading && !isError && segments.length > 0 && (
        <EndOfTranscript />
      )}

      {/* Intersection observer target for infinite scroll */}
      {hasNextPage && !isFetchingNextPage && (
        <div
          ref={loadMoreRef}
          className="h-1"
          aria-hidden="true"
        />
      )}

      {/* Deep link navigation announcement for screen readers (FR-010) */}
      {deepLinkAnnouncement && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {deepLinkAnnouncement}
        </div>
      )}

      {/* Correction state announcement for screen readers (US-8) */}
      {correctionAnnouncement && (
        <div
          role="status"
          aria-live={correctionError ? "assertive" : "polite"}
          aria-atomic="true"
          className="sr-only"
          data-correction-announcement="true"
        >
          {correctionAnnouncement}
        </div>
      )}
    </div>
  );
}
