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
 *
 * @module components/transcript/TranscriptSegments
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import { useTranscriptSegments } from "../../hooks/useTranscriptSegments";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { formatTimestamp } from "../../utils/formatTimestamp";
import {
  INFINITE_SCROLL_CONFIG,
  VIRTUALIZATION_CONFIG,
  RESPONSIVE_CONFIG,
  CONTRAST_SAFE_COLORS,
} from "../../styles/tokens";
import type { TranscriptSegment } from "../../types/transcript";

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
 * SegmentItem component renders a single transcript segment.
 *
 * Supports optional highlight state for deep link navigation (FR-008, FR-009, FR-015).
 */
function SegmentItem({
  segment,
  isVirtualized,
  isHighlighted,
  highlightTransitionClass,
}: {
  segment: TranscriptSegment;
  isVirtualized: boolean;
  isHighlighted?: boolean;
  highlightTransitionClass?: string;
}) {
  // Highlight styles: yellow background with left border indicator (FR-008)
  const highlightClasses = isHighlighted
    ? "bg-yellow-100 border-l-4 border-yellow-400"
    : "border-l-4 border-transparent";

  return (
    <div
      className={`flex gap-4 py-2 ${isVirtualized ? "px-2" : ""} ${highlightClasses} ${highlightTransitionClass ?? ""}`}
      data-segment-id={segment.id}
      // FR-015: Make highlighted segment focusable for programmatic focus
      tabIndex={isHighlighted ? -1 : undefined}
    >
      {/* Timestamp - left side (NFR-A17, NFR-A18: text-gray-600 for 7.0:1 contrast) */}
      <span
        className={`flex-shrink-0 w-16 ${CONTRAST_SAFE_COLORS.timestamp} font-mono ${RESPONSIVE_CONFIG.segmentTextSize.mobile} lg:${RESPONSIVE_CONFIG.segmentTextSize.desktop}`}
      >
        {formatTimestamp(segment.start_time)}
      </span>

      {/* Segment text - right side (NFR-A16, NFR-A18: text-gray-900 for 16.6:1 contrast) */}
      <p
        className={`flex-1 ${CONTRAST_SAFE_COLORS.bodyText} ${RESPONSIVE_CONFIG.segmentTextSize.mobile} lg:${RESPONSIVE_CONFIG.segmentTextSize.desktop}`}
      >
        {segment.text}
      </p>
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
 */
function VirtualizedSegmentList({
  segments,
  containerRef,
  onScroll,
  highlightedSegmentId,
  highlightTransitionClass,
}: {
  segments: TranscriptSegment[];
  containerRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  highlightedSegmentId: number | null;
  highlightTransitionClass: string;
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
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: `${virtualItem.size}px`,
              transform: `translateY(${virtualItem.start}px)`,
            }}
          >
            <SegmentItem
              segment={segment}
              isVirtualized={true}
              isHighlighted={isHighlighted}
              highlightTransitionClass={isHighlighted ? highlightTransitionClass : ""}
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
}: {
  segments: TranscriptSegment[];
  highlightedSegmentId: number | null;
  highlightTransitionClass: string;
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

  // Reduced motion preference for highlight animation (FR-009)
  const prefersReducedMotion = usePrefersReducedMotion();

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
        />
      ) : (
        <StandardSegmentList
          segments={segments}
          highlightedSegmentId={highlightedSegmentId}
          highlightTransitionClass={highlightTransitionClass}
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
    </div>
  );
}
