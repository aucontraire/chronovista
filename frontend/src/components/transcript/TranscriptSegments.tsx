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

import { useCallback, useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import { useTranscriptSegments } from "../../hooks/useTranscriptSegments";
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
}

/**
 * SegmentItem component renders a single transcript segment.
 */
function SegmentItem({
  segment,
  isVirtualized,
}: {
  segment: TranscriptSegment;
  isVirtualized: boolean;
}) {
  return (
    <div
      className={`flex gap-4 py-2 ${isVirtualized ? "px-2" : ""}`}
      data-segment-id={segment.id}
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
}: {
  segments: TranscriptSegment[];
  containerRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
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
            <SegmentItem segment={segment} isVirtualized={true} />
          </div>
        );
      })}
    </div>
  );
}

/**
 * StandardSegmentList component for rendering segments without virtualization.
 */
function StandardSegmentList({ segments }: { segments: TranscriptSegment[] }) {
  return (
    <>
      {segments.map((segment) => (
        <SegmentItem key={segment.id} segment={segment} isVirtualized={false} />
      ))}
    </>
  );
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
}: TranscriptSegmentsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const previousLanguageRef = useRef<string>(languageCode);

  const {
    segments,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    isError,
    // error is available but not displayed; we use isError for conditional rendering
    fetchNextPage,
    retry,
  } = useTranscriptSegments(videoId, languageCode);

  // Determine if virtualization should be used (NFR-P12)
  const useVirtualization = segments.length > VIRTUALIZATION_CONFIG.threshold;

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
        />
      ) : (
        <StandardSegmentList segments={segments} />
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
    </div>
  );
}
