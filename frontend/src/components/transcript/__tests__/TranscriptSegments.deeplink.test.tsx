/**
 * Tests for TranscriptSegments Component - Deep Link Navigation
 *
 * Tests coverage (T012):
 * - Scroll-to-segment on targetSegmentId match (FR-006, FR-007)
 * - Highlight behavior with visual indicator (FR-008, FR-009)
 * - Screen reader announcement for navigation (FR-015)
 * - Focus management for highlighted segment
 * - Highlight cleanup after 3 seconds
 * - onDeepLinkComplete callback invocation (FR-011)
 * - Guard rails: no scroll when targetSegmentId is undefined
 * - Guard rails: no re-trigger when segments change after initial navigation
 * - Reduced motion support (FR-009)
 *
 * This test file focuses exclusively on deep link behaviors.
 * General segment rendering, pagination, and virtualization are tested separately.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act } from "react";
import { TranscriptSegments } from "../TranscriptSegments";
import type { TranscriptSegment } from "../../../types/transcript";

// Mock dependencies
vi.mock("../../../hooks/useTranscriptSegments", () => ({
  useTranscriptSegments: vi.fn(),
}));

vi.mock("../../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn(() => false),
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
    measureElement: vi.fn(),
    scrollToIndex: vi.fn(),
  })),
}));

vi.mock("../../../utils/formatTimestamp", () => ({
  formatTimestamp: vi.fn((seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }),
}));

// Import after mocks to get mocked versions
import { useTranscriptSegments } from "../../../hooks/useTranscriptSegments";
import { usePrefersReducedMotion } from "../../../hooks/usePrefersReducedMotion";

/**
 * Test factory to generate TranscriptSegment test data.
 */
function createTestSegment(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    id: 1,
    text: "Test segment text",
    start_time: 0,
    end_time: 5,
    duration: 5,
    ...overrides,
  };
}

/**
 * Creates an array of test segments.
 */
function createTestSegments(count: number): TranscriptSegment[] {
  return Array.from({ length: count }, (_, index) =>
    createTestSegment({
      id: index + 1,
      text: `Segment ${index + 1} text`,
      start_time: index * 5,
      end_time: (index + 1) * 5,
      duration: 5,
    })
  );
}

/**
 * Default mock return value for useTranscriptSegments hook.
 */
function createDefaultHookReturn(segments: TranscriptSegment[] = []) {
  return {
    segments,
    totalCount: segments.length,
    isLoading: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    isError: false,
    error: null,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    cancelRequests: vi.fn(),
    seekToTimestamp: vi.fn().mockResolvedValue(true),
  };
}

describe("TranscriptSegments - Deep Link Navigation", () => {
  let scrollIntoViewMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // Reset all mocks before each test
    vi.clearAllMocks();
    // Use fake timers with auto-advance to prevent waitFor deadlock
    vi.useFakeTimers({ shouldAdvanceTime: true });

    // Mock scrollIntoView (happy-dom doesn't implement this)
    scrollIntoViewMock = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoViewMock as unknown as typeof Element.prototype.scrollIntoView;

    // Default mock implementations
    vi.mocked(useTranscriptSegments).mockReturnValue(createDefaultHookReturn());
    vi.mocked(usePrefersReducedMotion).mockReturnValue(false);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  describe("Scroll-to-segment behavior (FR-006, FR-007)", () => {
    it("should scroll to the target segment when targetSegmentId is provided and segment exists", () => {
      const segments = createTestSegments(10);
      const targetSegment = segments[4]!; // id: 5

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      // Advance timers to trigger the scroll delay (50ms for standard list)
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Verify scrollIntoView was called
      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "smooth",
        block: "center",
      });
    });

    it("should use smooth scroll behavior by default", () => {
      const segments = createTestSegments(5);
      const targetSegment = segments[2]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(scrollIntoViewMock).toHaveBeenCalledWith(
        expect.objectContaining({ behavior: "smooth" })
      );
    });

    it("should scroll to center of viewport", () => {
      const segments = createTestSegments(5);
      const targetSegment = segments[1]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(scrollIntoViewMock).toHaveBeenCalledWith(
        expect.objectContaining({ block: "center" })
      );
    });

    it("should NOT scroll when targetSegmentId is undefined", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          // No targetSegmentId provided
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    it("should NOT scroll when targetSegmentId does not exist in segments", () => {
      const segments = createTestSegments(5); // ids 1-5

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // ID that doesn't exist
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    it("should NOT re-trigger scroll when segments change after initial navigation", () => {
      const initialSegments = createTestSegments(5);
      const targetSegment = initialSegments[2]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(initialSegments)
      );

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // ScrollIntoView should be called once
      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);

      // Add more segments
      const moreSegments = createTestSegments(10);
      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(moreSegments)
      );

      act(() => {
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            targetSegmentId={targetSegment.id}
          />
        );
      });

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should still be called only once (not re-triggered)
      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
    });

    it("should NOT scroll when isLoading is true", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        isLoading: true, // Still loading
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });
  });

  describe("Highlight behavior (FR-008, FR-009)", () => {
    it("should apply highlight classes to the target segment", () => {
      const segments = createTestSegments(5);
      const targetSegment = segments[1]!; // id: 2

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Find the highlighted segment
      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      expect(highlightedElement).toHaveClass("bg-yellow-100");
      expect(highlightedElement).toHaveClass("border-l-4");
      expect(highlightedElement).toHaveClass("border-yellow-400");
    });

    it("should apply transition class for fade-out animation when motion is not reduced", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[0]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );
      vi.mocked(usePrefersReducedMotion).mockReturnValue(false); // Animations enabled

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      expect(highlightedElement).toHaveClass("transition-all");
      expect(highlightedElement).toHaveClass("duration-1000");
      expect(highlightedElement).toHaveClass("ease-out");
    });

    it("should NOT apply transition class when user prefers reduced motion", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[0]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );
      vi.mocked(usePrefersReducedMotion).mockReturnValue(true); // Reduced motion

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      // Should still have highlight colors
      expect(highlightedElement).toHaveClass("bg-yellow-100");
      // But NOT transition classes
      expect(highlightedElement).not.toHaveClass("transition-all");
    });

    it("should clear highlight after 3 seconds", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[1]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const segmentElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      // Initially highlighted
      expect(segmentElement).toHaveClass("bg-yellow-100");

      // Advance timers by 3 seconds
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      // Highlight should be cleared
      expect(segmentElement).not.toHaveClass("bg-yellow-100");
      expect(segmentElement).toHaveClass("border-transparent");
    });

    it("should only highlight the target segment, not others", () => {
      const segments = createTestSegments(5);
      const targetSegment = segments[2]!; // id: 3

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Check that only the target is highlighted
      const allSegments = container.querySelectorAll("[data-segment-id]");

      allSegments.forEach((element) => {
        const segmentId = parseInt(element.getAttribute("data-segment-id") || "0", 10);
        if (segmentId === targetSegment.id) {
          expect(element).toHaveClass("bg-yellow-100");
        } else {
          expect(element).not.toHaveClass("bg-yellow-100");
          expect(element).toHaveClass("border-transparent");
        }
      });
    });
  });

  describe("Screen reader announcement (FR-015)", () => {
    it("should announce navigation to the target segment", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[1]!; // start_time: 5

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Find the aria-live region
      const announcement = screen.getByText(
        /Navigated to matched transcript segment at/i
      );

      expect(announcement).toBeInTheDocument();
      expect(announcement).toHaveAttribute("role", "status");
      expect(announcement).toHaveAttribute("aria-live", "polite");
      expect(announcement).toHaveAttribute("aria-atomic", "true");
    });

    it("should include formatted timestamp in announcement", () => {
      const segments = createTestSegments(3);
      const targetSegment = createTestSegment({
        id: 10,
        start_time: 125.5, // Should format as "2:05"
        end_time: 130,
        duration: 4.5,
      });
      segments.push(targetSegment);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const announcement = screen.getByText(
        /Navigated to matched transcript segment at 2:05/i
      );

      expect(announcement).toBeInTheDocument();
    });

    it("should clear announcement after 3 seconds", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[0]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Announcement should exist initially
      let announcement = container.querySelector('[aria-live="polite"][aria-atomic="true"]');
      expect(announcement?.textContent).toContain("Navigated to");

      // Advance by 3 seconds
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      // Announcement should be cleared (element removed since deepLinkAnnouncement is empty)
      announcement = container.querySelector('[aria-live="polite"][aria-atomic="true"]');
      expect(announcement).toBeNull();
    });

    it("should have sr-only class for visual hiding", () => {
      const segments = createTestSegments(2);
      const targetSegment = segments[0]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const announcement = container.querySelector('[aria-live="polite"][aria-atomic="true"]');

      expect(announcement).toHaveClass("sr-only");
    });
  });

  describe("Focus management", () => {
    it("should apply tabIndex=-1 to highlighted segment", () => {
      const segments = createTestSegments(4);
      const targetSegment = segments[2]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      expect(highlightedElement).toHaveAttribute("tabindex", "-1");
    });

    it("should programmatically focus the highlighted segment after scroll", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[1]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      // Mock focus on the element
      const focusMock = vi.fn();
      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      ) as HTMLElement | null;

      if (highlightedElement) {
        highlightedElement.focus = focusMock;
      }

      act(() => {
        vi.advanceTimersByTime(50); // Scroll delay
      });

      act(() => {
        vi.advanceTimersByTime(200); // Focus delay
      });

      expect(focusMock).toHaveBeenCalled();
    });

    it("should NOT apply tabIndex to non-highlighted segments", () => {
      const segments = createTestSegments(5);
      const targetSegment = segments[2]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const allSegments = container.querySelectorAll("[data-segment-id]");

      allSegments.forEach((element) => {
        const segmentId = parseInt(element.getAttribute("data-segment-id") || "0", 10);
        if (segmentId === targetSegment.id) {
          expect(element).toHaveAttribute("tabindex", "-1");
        } else {
          expect(element).not.toHaveAttribute("tabindex");
        }
      });
    });
  });

  describe("onDeepLinkComplete callback (FR-011)", () => {
    it("should call onDeepLinkComplete after cleanup (3 seconds)", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[1]!;
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // Callback should not be called yet
      expect(onDeepLinkComplete).not.toHaveBeenCalled();

      // Advance timers through scroll delay + focus delay
      act(() => {
        vi.advanceTimersByTime(250);
      });

      // Still not called
      expect(onDeepLinkComplete).not.toHaveBeenCalled();

      // Advance to cleanup time (3 seconds total)
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      // Should be called after cleanup
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should call onDeepLinkComplete immediately when no valid target", () => {
      const segments = createTestSegments(3);
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Non-existent ID
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should be called immediately since target doesn't exist
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should NOT call onDeepLinkComplete when callback is not provided", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[0]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      // No error should be thrown when callback is undefined
      expect(() => {
        render(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            targetSegmentId={targetSegment.id}
            // No onDeepLinkComplete provided
          />
        );
      }).not.toThrow();

      act(() => {
        vi.advanceTimersByTime(3050);
      });

      // No assertion needed - just verify no error was thrown
    });
  });

  describe("Guard rails and edge cases", () => {
    it("should handle segments array being empty", () => {
      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn([]) // Empty segments
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={1}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    it("should handle component unmounting before cleanup completes", () => {
      const segments = createTestSegments(3);
      const targetSegment = segments[0]!;
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { unmount } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      // Unmount before cleanup
      unmount();

      // Advance timers after unmount
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      // Callback might or might not be called depending on cleanup
      // Main point is no error should be thrown
      expect(() => vi.runOnlyPendingTimers()).not.toThrow();
    });

    it("should handle targetSegmentId being 1 (smallest valid ID)", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={1} // Smallest valid ID (hook validates seg > 0)
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(scrollIntoViewMock).toHaveBeenCalled();
    });

    it("should NOT scroll when hasNextPage is true but segment not found", () => {
      const segments = createTestSegments(5); // ids 1-5

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: true, // More pages available
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10} // Not in current segments
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should not scroll (T013 will handle fetching until found)
      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    it("should call onDeepLinkComplete when segment not found and no more pages", () => {
      const segments = createTestSegments(5);
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: false, // No more pages
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Not found
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });
  });

  describe("Integration with standard segment list", () => {
    it("should work correctly with standard (non-virtualized) list", () => {
      // Use fewer than 100 segments to avoid virtualization
      const segments = createTestSegments(50);
      const targetSegment = segments[25]!;

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={targetSegment.id}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const highlightedElement = container.querySelector(
        `[data-segment-id="${targetSegment.id}"]`
      );

      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });

    it("should render all segments with data-segment-id attribute", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const segmentElements = container.querySelectorAll("[data-segment-id]");
      expect(segmentElements).toHaveLength(5);

      segmentElements.forEach((element, index) => {
        expect(element).toHaveAttribute("data-segment-id", `${index + 1}`);
      });
    });
  });

  describe("Fetch-until-found (FR-006)", () => {
    it("should call fetchNextPage when target segment is not in loaded segments and hasNextPage is true", () => {
      const segments = createTestSegments(5); // ids 1-5
      const mockFetchNextPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: true,
        fetchNextPage: mockFetchNextPage,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10} // Not in segments 1-5
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // fetchNextPage should be called since segment not found and more pages available
      expect(mockFetchNextPage).toHaveBeenCalled();
    });

    it("should scroll to segment after it appears in subsequently fetched data", () => {
      const initialSegments = createTestSegments(5); // ids 1-5
      const mockFetchNextPage = vi.fn();
      const onDeepLinkComplete = vi.fn();

      // Step 1: Initial render - target not found
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(initialSegments),
        hasNextPage: true,
        fetchNextPage: mockFetchNextPage,
      });

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // fetchNextPage should be called
      expect(mockFetchNextPage).toHaveBeenCalled();
      expect(scrollIntoViewMock).not.toHaveBeenCalled();

      // Step 2: Simulate page loaded - target now available
      const expandedSegments = createTestSegments(10); // ids 1-10
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(expandedSegments),
        hasNextPage: false,
        fetchNextPage: mockFetchNextPage,
      });

      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to the found segment
      expect(scrollIntoViewMock).toHaveBeenCalled();
    });

    it("should cap sequential fetches at 3 pages then attempt targeted seek", async () => {
      const mockFetchNextPage = vi.fn();
      const mockSeekToTimestamp = vi.fn().mockResolvedValue(true);

      // Start with 5 segments (5s each => 25s total), target at 999 (never found)
      let currentCount = 5;
      const updateMock = () => {
        vi.mocked(useTranscriptSegments).mockReturnValue({
          ...createDefaultHookReturn(createTestSegments(currentCount)),
          hasNextPage: true,
          fetchNextPage: mockFetchNextPage,
          seekToTimestamp: mockSeekToTimestamp,
        });
      };

      updateMock();

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
          targetTimestamp={500} // Deep timestamp triggers seek after 3 pages
        />
      );

      // Simulate 3 sequential fetch iterations (the new cap)
      for (let i = 0; i < 3; i++) {
        act(() => {
          vi.advanceTimersByTime(50);
        });
        expect(mockFetchNextPage).toHaveBeenCalledTimes(i + 1);

        currentCount += 25;
        updateMock();
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            targetSegmentId={999}
            targetTimestamp={500}
          />
        );
      }

      // On 4th effect run, should attempt seekToTimestamp instead of fetchNextPage
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // fetchNextPage should have been called exactly 3 times (cap enforced)
      expect(mockFetchNextPage).toHaveBeenCalledTimes(3);
      // seekToTimestamp should have been called once (targeted jump)
      expect(mockSeekToTimestamp).toHaveBeenCalledTimes(1);
    });

    it("should stop fetching when hasNextPage becomes false before cap", () => {
      const onDeepLinkComplete = vi.fn();
      const mockFetchNextPage = vi.fn();

      // Step 1: Initial render with hasNextPage=true
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(createTestSegments(5)),
        hasNextPage: true,
        fetchNextPage: mockFetchNextPage,
      });

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Not in segments
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // fetchNextPage should be called once
      expect(mockFetchNextPage).toHaveBeenCalledTimes(1);

      // Step 2: Update mock with hasNextPage=false (no more data)
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(createTestSegments(10)),
        hasNextPage: false, // No more pages
        fetchNextPage: mockFetchNextPage,
      });

      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // fetchNextPage should NOT be called again (hasNextPage=false)
      expect(mockFetchNextPage).toHaveBeenCalledTimes(1);
      // onDeepLinkComplete should be called (fallback triggered)
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should NOT call fetchNextPage when isFetchingNextPage is true", () => {
      const segments = createTestSegments(5);
      const mockFetchNextPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: true,
        isFetchingNextPage: true, // Currently fetching
        fetchNextPage: mockFetchNextPage,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // fetchNextPage should NOT be called (effect returns early when isFetchingNextPage=true)
      expect(mockFetchNextPage).not.toHaveBeenCalled();
    });

    it("should NOT call fetchNextPage after segment is found", () => {
      const segments = createTestSegments(10); // ids 1-10
      const mockFetchNextPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: true, // More pages available, but not needed
        fetchNextPage: mockFetchNextPage,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={5} // Already in loaded segments
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment immediately
      expect(scrollIntoViewMock).toHaveBeenCalled();
      // fetchNextPage should NOT be called (segment already found)
      expect(mockFetchNextPage).not.toHaveBeenCalled();
    });

    it("should increment fetch iteration counter on each sequential fetch attempt up to 3", () => {
      const mockFetchNextPage = vi.fn();
      let currentCount = 5;

      const updateMock = (hasNext: boolean = true) => {
        vi.mocked(useTranscriptSegments).mockReturnValue({
          ...createDefaultHookReturn(createTestSegments(currentCount)),
          hasNextPage: hasNext,
          fetchNextPage: mockFetchNextPage,
        });
      };

      updateMock();

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
        />
      );

      // Perform 3 sequential iterations (the cap)
      for (let i = 0; i < 3; i++) {
        act(() => {
          vi.advanceTimersByTime(50);
        });

        expect(mockFetchNextPage).toHaveBeenCalledTimes(i + 1);

        currentCount += 10;
        updateMock();
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            targetSegmentId={999}
          />
        );
      }

      // On the 4th effect run, fetchNextPage should NOT be called again
      // (cap of 3 sequential pages reached — seek or fallback happens instead)
      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(mockFetchNextPage).toHaveBeenCalledTimes(3);
    });

    it("should find segment on 2nd sequential fetch (before 3-page cap)", () => {
      const mockFetchNextPage = vi.fn();
      const onDeepLinkComplete = vi.fn();
      let currentCount = 5;

      const updateMock = (includeTarget: boolean = false) => {
        const segments = includeTarget
          ? [...createTestSegments(currentCount), createTestSegment({ id: 999, text: "Target segment" })]
          : createTestSegments(currentCount);

        vi.mocked(useTranscriptSegments).mockReturnValue({
          ...createDefaultHookReturn(segments),
          hasNextPage: !includeTarget,
          fetchNextPage: mockFetchNextPage,
        });
      };

      updateMock();

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // 1st sequential fetch — segment not found
      act(() => {
        vi.advanceTimersByTime(50);
      });
      expect(mockFetchNextPage).toHaveBeenCalledTimes(1);

      currentCount += 25;
      updateMock(false);
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // 2nd sequential fetch — segment appears
      act(() => {
        vi.advanceTimersByTime(50);
      });
      expect(mockFetchNextPage).toHaveBeenCalledTimes(2);

      currentCount += 25;
      updateMock(true); // Include target segment
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to found segment
      expect(scrollIntoViewMock).toHaveBeenCalled();
      // fetchNextPage should NOT be called again (segment found)
      expect(mockFetchNextPage).toHaveBeenCalledTimes(2);
      // onDeepLinkComplete should NOT be called yet (scroll is happening)
      expect(onDeepLinkComplete).not.toHaveBeenCalled();
    });

    it("should not fetch when segments array is empty", () => {
      const mockFetchNextPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn([]), // Empty segments
        hasNextPage: true,
        fetchNextPage: mockFetchNextPage,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should not fetch when segments array is empty (effect returns early)
      expect(mockFetchNextPage).not.toHaveBeenCalled();
    });

    it("should not fetch when isLoading is true", () => {
      const segments = createTestSegments(5);
      const mockFetchNextPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        isLoading: true, // Still loading initial data
        hasNextPage: true,
        fetchNextPage: mockFetchNextPage,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={10}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should not fetch when isLoading is true (effect returns early)
      expect(mockFetchNextPage).not.toHaveBeenCalled();
    });
  });

  describe("Timestamp fallback (FR-007)", () => {
    it("should scroll to nearest segment by timestamp when segment not found and no more pages", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 0, end_time: 10, duration: 10, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 10, end_time: 20, duration: 10, text: "Segment 2" }),
        createTestSegment({ id: 3, start_time: 20, end_time: 30, duration: 10, text: "Segment 3" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: false,
      });

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Not found
          targetTimestamp={12} // Falls back to timestamp
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment id=2 (start_time=10, closest to 12)
      expect(scrollIntoViewMock).toHaveBeenCalled();
      const highlightedElement = container.querySelector('[data-segment-id="2"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });

    it("should scroll to nearest segment by timestamp when only targetTimestamp is provided (no seg)", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 0, end_time: 30, duration: 30, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 30, end_time: 60, duration: 30, text: "Segment 2" }),
        createTestSegment({ id: 3, start_time: 60, end_time: 90, duration: 30, text: "Segment 3" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetTimestamp={25} // No targetSegmentId
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment id=2 (start_time=30, diff=5 — closest to 25)
      expect(scrollIntoViewMock).toHaveBeenCalled();
      const highlightedElement = container.querySelector('[data-segment-id="2"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });

    it("should highlight the nearest segment by timestamp with yellow classes", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 0, end_time: 30, duration: 30, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 30, end_time: 60, duration: 30, text: "Segment 2" }),
        createTestSegment({ id: 3, start_time: 60, end_time: 90, duration: 30, text: "Segment 3" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetTimestamp={25}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const highlightedElement = container.querySelector('[data-segment-id="2"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
      expect(highlightedElement).toHaveClass("border-l-4");
      expect(highlightedElement).toHaveClass("border-yellow-400");
    });

    it("should call onDeepLinkComplete after 3s when using timestamp fallback", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 0, end_time: 10, duration: 10, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 10, end_time: 20, duration: 10, text: "Segment 2" }),
        createTestSegment({ id: 3, start_time: 20, end_time: 30, duration: 10, text: "Segment 3" }),
      ];
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: false,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Not found
          targetTimestamp={12}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should not be called yet
      expect(onDeepLinkComplete).not.toHaveBeenCalled();

      // Advance to cleanup time (3 seconds)
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      // Should be called after cleanup
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should fall through to timestamp when segment ID search exhausts and hasNextPage becomes false", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 0, end_time: 5, duration: 5, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 5, end_time: 10, duration: 5, text: "Segment 2" }),
        createTestSegment({ id: 3, start_time: 10, end_time: 15, duration: 5, text: "Segment 3" }),
        createTestSegment({ id: 4, start_time: 15, end_time: 20, duration: 5, text: "Segment 4" }),
        createTestSegment({ id: 5, start_time: 20, end_time: 25, duration: 5, text: "Segment 5" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: false, // No more pages
      });

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={999} // Not found
          targetTimestamp={12} // Falls back to timestamp
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment id=3 (start_time=10, diff=2 — closest to 12)
      expect(scrollIntoViewMock).toHaveBeenCalled();
      const highlightedElement = container.querySelector('[data-segment-id="3"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });

    it("should handle targetTimestamp=0 (beginning of transcript)", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 5, end_time: 10, duration: 5, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 10, end_time: 15, duration: 5, text: "Segment 2" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetTimestamp={0} // Beginning of transcript
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment id=1 (start_time=5, closest to 0)
      expect(scrollIntoViewMock).toHaveBeenCalled();
      const highlightedElement = container.querySelector('[data-segment-id="1"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });

    it("should NOT call onDeepLinkComplete when no segments loaded and only timestamp provided", () => {
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn([]), // Empty segments
        isLoading: false,
      });

      render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetTimestamp={50}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should NOT be called (segments.length === 0 guard returns early)
      expect(onDeepLinkComplete).not.toHaveBeenCalled();
      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    it("should handle timestamp exactly matching a segment start_time", () => {
      const segments = [
        createTestSegment({ id: 1, start_time: 10, end_time: 20, duration: 10, text: "Segment 1" }),
        createTestSegment({ id: 2, start_time: 20, end_time: 30, duration: 10, text: "Segment 2" }),
      ];

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetTimestamp={10} // Exact match with segment 1
        />
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should scroll to segment id=1 (exact match, diff=0)
      expect(scrollIntoViewMock).toHaveBeenCalled();
      const highlightedElement = container.querySelector('[data-segment-id="1"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");
    });
  });

  describe("Panel collapse abort (T017)", () => {
    it("should abort highlight when panel collapses during deep link navigation", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container, rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={true}
        />
      );

      // Trigger deep link
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Verify highlight is visible
      let highlightedElement = container.querySelector('[data-segment-id="3"]');
      expect(highlightedElement).toHaveClass("bg-yellow-100");

      // Collapse panel
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={false}
        />
      );

      // Verify highlight cleared
      highlightedElement = container.querySelector('[data-segment-id="3"]');
      expect(highlightedElement).not.toHaveClass("bg-yellow-100");
      expect(highlightedElement).toHaveClass("border-transparent");
    });

    it("should call onDeepLinkComplete immediately on panel collapse", () => {
      const segments = createTestSegments(5);
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={true}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // Trigger deep link
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should not be called yet
      expect(onDeepLinkComplete).not.toHaveBeenCalled();

      // Collapse panel
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={false}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // Should be called immediately
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should NOT re-trigger deep link on re-expansion", () => {
      const segments = createTestSegments(5);
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={true}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // Trigger deep link
      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);

      // Collapse panel (abort)
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={false}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);

      // Re-expand panel
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={true}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      // Should NOT trigger another scroll (still 1 from earlier)
      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
      // onDeepLinkComplete should NOT be called again (still 1 from collapse)
      expect(onDeepLinkComplete).toHaveBeenCalledTimes(1);
    });

    it("should NOT abort when panel collapses with no active deep link", () => {
      const segments = createTestSegments(5);
      const onDeepLinkComplete = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          // No targetSegmentId
          isExpanded={true}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // Collapse panel
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          isExpanded={false}
          onDeepLinkComplete={onDeepLinkComplete}
        />
      );

      // onDeepLinkComplete should NOT be called (no active deep link)
      expect(onDeepLinkComplete).not.toHaveBeenCalled();
    });

    it("should clear screen reader announcement on panel collapse", () => {
      const segments = createTestSegments(5);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container, rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={true}
        />
      );

      // Trigger deep link
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Verify announcement exists
      let announcement = container.querySelector('[aria-live="polite"][aria-atomic="true"]');
      expect(announcement?.textContent).toContain("Navigated to");

      // Collapse panel
      rerender(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          targetSegmentId={3}
          isExpanded={false}
        />
      );

      // Announcement should be cleared (removed)
      announcement = container.querySelector('[aria-live="polite"][aria-atomic="true"]');
      expect(announcement).toBeNull();
    });
  });
});
