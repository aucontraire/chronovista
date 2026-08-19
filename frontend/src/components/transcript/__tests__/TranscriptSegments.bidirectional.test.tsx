/**
 * Tests for TranscriptSegments - Bidirectional Infinite Scroll
 *
 * Covers the wiring introduced to fix the deep-link timestamp-discontinuity
 * bug: scrolling UP from a deep-link window must load earlier segments
 * (fetchPreviousPage) and the viewport must not visibly jump while that
 * prepend happens.
 *
 * This file focuses exclusively on the bidirectional-paging wiring:
 * - The manual-scroll fallback triggers fetchPreviousPage near the top
 *   (mirrors the existing bottom fetchNextPage fallback).
 * - The "loading earlier segments" skeleton is gated on isFetchingPreviousPage.
 * - Scroll position is preserved (anchored) when a prepend grows the
 *   container's scrollHeight.
 *
 * The data-contiguity behavior of fetchPreviousPage itself (prepended
 * segments are contiguous with the existing window) is covered at the hook
 * level in src/tests/hooks/useTranscriptSegments.test.tsx, since this file
 * mocks useTranscriptSegments entirely.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
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

vi.mock("../../../hooks/useCorrectSegment", () => ({
  useCorrectSegment: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

vi.mock("../../../hooks/useRevertSegment", () => ({
  useRevertSegment: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

vi.mock("../../../hooks/useSegmentCorrectionHistory", () => ({
  useSegmentCorrectionHistory: vi.fn().mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
}));

import { useTranscriptSegments } from "../../../hooks/useTranscriptSegments";

function createTestSegment(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    id: 1,
    text: "Test segment text",
    start_time: 0,
    end_time: 5,
    duration: 5,
    has_correction: false,
    corrected_at: null,
    correction_count: 0,
    ...overrides,
  };
}

function createTestSegments(count: number, startId = 1): TranscriptSegment[] {
  return Array.from({ length: count }, (_, index) =>
    createTestSegment({
      id: startId + index,
      text: `Segment ${startId + index} text`,
      start_time: (startId + index) * 5,
      end_time: (startId + index) * 5 + 5,
      duration: 5,
    })
  );
}

function createDefaultHookReturn(segments: TranscriptSegment[] = []) {
  return {
    segments,
    totalCount: segments.length,
    isLoading: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    isFetchingPreviousPage: false,
    hasPreviousPage: false,
    isError: false,
    error: null,
    fetchNextPage: vi.fn(),
    fetchPreviousPage: vi.fn(),
    retry: vi.fn(),
    cancelRequests: vi.fn(),
    seekToTimestamp: vi.fn().mockResolvedValue(true),
  };
}

/**
 * Defines scrollTop/scrollHeight as a controllable get/set pair on a single
 * DOM node so tests can simulate scroll position and content growth without
 * a real layout engine (happy-dom does not compute layout).
 */
function makeScrollable(
  element: HTMLElement,
  initial: { scrollTop: number; scrollHeight: number }
) {
  let scrollTopValue = initial.scrollTop;
  let scrollHeightValue = initial.scrollHeight;

  Object.defineProperty(element, "scrollTop", {
    configurable: true,
    get: () => scrollTopValue,
    set: (v: number) => {
      scrollTopValue = v;
    },
  });
  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    get: () => scrollHeightValue,
  });
  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    get: () => 400,
  });

  return {
    setScrollHeight: (v: number) => {
      scrollHeightValue = v;
    },
    getScrollTop: () => scrollTopValue,
  };
}

describe("TranscriptSegments - Bidirectional Infinite Scroll", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useTranscriptSegments).mockReturnValue(createDefaultHookReturn());
  });

  describe("scroll-up triggers fetchPreviousPage (manual-scroll fallback)", () => {
    it("calls fetchPreviousPage when scrolled near the top and hasPreviousPage is true", () => {
      const segments = createTestSegments(150, 26); // simulates an installed deep-link window
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: true,
        fetchPreviousPage,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      const region = screen.getByRole("region", { name: "Transcript segments" });
      makeScrollable(region, { scrollTop: 0, scrollHeight: 2000 });

      fireEvent.scroll(region);

      expect(fetchPreviousPage).toHaveBeenCalledTimes(1);
    });

    it("does NOT call fetchPreviousPage when hasPreviousPage is false", () => {
      const segments = createTestSegments(50);
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: false,
        fetchPreviousPage,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      const region = screen.getByRole("region", { name: "Transcript segments" });
      makeScrollable(region, { scrollTop: 0, scrollHeight: 2000 });

      fireEvent.scroll(region);

      expect(fetchPreviousPage).not.toHaveBeenCalled();
    });

    it("does NOT call fetchPreviousPage when isFetchingPreviousPage is true (already in flight)", () => {
      const segments = createTestSegments(150, 26);
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: true,
        isFetchingPreviousPage: true,
        fetchPreviousPage,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      const region = screen.getByRole("region", { name: "Transcript segments" });
      makeScrollable(region, { scrollTop: 0, scrollHeight: 2000 });

      fireEvent.scroll(region);

      expect(fetchPreviousPage).not.toHaveBeenCalled();
    });

    it("does NOT call fetchPreviousPage when scrolled away from the top", () => {
      const segments = createTestSegments(150, 26);
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: true,
        fetchPreviousPage,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      const region = screen.getByRole("region", { name: "Transcript segments" });
      // Scrolled well past the 200px trigger distance from the top.
      makeScrollable(region, { scrollTop: 800, scrollHeight: 2000 });

      fireEvent.scroll(region);

      expect(fetchPreviousPage).not.toHaveBeenCalled();
    });

    it("still triggers fetchNextPage independently when scrolled to the bottom", () => {
      const segments = createTestSegments(150, 26);
      const fetchNextPage = vi.fn();
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasNextPage: true,
        hasPreviousPage: true,
        fetchNextPage,
        fetchPreviousPage,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      const region = screen.getByRole("region", { name: "Transcript segments" });
      // Near the bottom (distanceFromBottom = 2000 - 1650 - 400 = -50 < 200),
      // far from the top (scrollTop = 1650 > 200).
      makeScrollable(region, { scrollTop: 1650, scrollHeight: 2000 });

      fireEvent.scroll(region);

      expect(fetchNextPage).toHaveBeenCalledTimes(1);
      expect(fetchPreviousPage).not.toHaveBeenCalled();
    });
  });

  describe("loading indicator for earlier segments", () => {
    it("shows the 'Loading earlier segments' skeleton when isFetchingPreviousPage is true", () => {
      const segments = createTestSegments(150, 26);

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: true,
        isFetchingPreviousPage: true,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      expect(screen.getByLabelText(/loading earlier segments/i)).toBeInTheDocument();
    });

    it("does NOT show the 'Loading earlier segments' skeleton when isFetchingPreviousPage is false", () => {
      const segments = createTestSegments(150, 26);

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(segments),
        hasPreviousPage: true,
        isFetchingPreviousPage: false,
      });

      render(<TranscriptSegments videoId="test-video" languageCode="en" />);

      expect(screen.queryByLabelText(/loading earlier segments/i)).not.toBeInTheDocument();
    });
  });

  describe("scroll-anchor preservation on prepend", () => {
    it("keeps the previously-visible content in place when earlier segments are prepended", () => {
      const initialSegments = createTestSegments(150, 26); // ids 26-175
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(initialSegments),
        hasPreviousPage: true,
        fetchPreviousPage,
      });

      const { rerender } = render(
        <TranscriptSegments videoId="test-video" languageCode="en" />
      );

      const region = screen.getByRole("region", { name: "Transcript segments" });
      const scrollable = makeScrollable(region, { scrollTop: 50, scrollHeight: 1000 });

      // Trigger the prepend via the scroll fallback (captures the anchor).
      act(() => {
        fireEvent.scroll(region);
      });
      expect(fetchPreviousPage).toHaveBeenCalledTimes(1);

      // Simulate the prepend completing: 25 earlier segments (ids 1-25) land,
      // growing scrollHeight by 400px worth of new rows.
      const expandedSegments = [...createTestSegments(25, 1), ...initialSegments];
      scrollable.setScrollHeight(1400);
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(expandedSegments),
        hasPreviousPage: false,
        fetchPreviousPage,
      });

      act(() => {
        rerender(<TranscriptSegments videoId="test-video" languageCode="en" />);
      });

      // scrollTop must be pushed down by exactly the added height (400px)
      // so the segment that was on screen before the prepend stays on
      // screen after it — no visible jump.
      expect(scrollable.getScrollTop()).toBe(450);
    });

    it("does NOT adjust scroll position for an unrelated segments change (no prepend anchor set)", () => {
      const segments = createTestSegments(50);

      vi.mocked(useTranscriptSegments).mockReturnValue(createDefaultHookReturn(segments));

      const { rerender } = render(
        <TranscriptSegments videoId="test-video" languageCode="en" />
      );

      const region = screen.getByRole("region", { name: "Transcript segments" });
      const scrollable = makeScrollable(region, { scrollTop: 300, scrollHeight: 1000 });

      // Segments grow (e.g. a normal fetchNextPage append) with no prior
      // fetchPreviousPage call, so no anchor was captured.
      scrollable.setScrollHeight(1600);
      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(createTestSegments(100))
      );

      act(() => {
        rerender(<TranscriptSegments videoId="test-video" languageCode="en" />);
      });

      // scrollTop is untouched — only a captured prepend anchor should ever
      // trigger the adjustment.
      expect(scrollable.getScrollTop()).toBe(300);
    });

    it("does not re-apply the anchor on a second, unrelated segments change", () => {
      const initialSegments = createTestSegments(150, 26);
      const fetchPreviousPage = vi.fn();

      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(initialSegments),
        hasPreviousPage: true,
        fetchPreviousPage,
      });

      const { rerender } = render(
        <TranscriptSegments videoId="test-video" languageCode="en" />
      );

      const region = screen.getByRole("region", { name: "Transcript segments" });
      const scrollable = makeScrollable(region, { scrollTop: 50, scrollHeight: 1000 });

      act(() => {
        fireEvent.scroll(region);
      });

      const expandedSegments = [...createTestSegments(25, 1), ...initialSegments];
      scrollable.setScrollHeight(1400);
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn(expandedSegments),
        hasPreviousPage: false,
        fetchPreviousPage,
      });

      act(() => {
        rerender(<TranscriptSegments videoId="test-video" languageCode="en" />);
      });

      expect(scrollable.getScrollTop()).toBe(450);

      // A second, unrelated segments change (e.g. a bottom fetchNextPage
      // append) must NOT reuse the already-consumed anchor.
      scrollable.setScrollHeight(2000);
      vi.mocked(useTranscriptSegments).mockReturnValue({
        ...createDefaultHookReturn([...expandedSegments, ...createTestSegments(25, 176)]),
        hasPreviousPage: false,
        fetchPreviousPage,
      });

      act(() => {
        rerender(<TranscriptSegments videoId="test-video" languageCode="en" />);
      });

      expect(scrollable.getScrollTop()).toBe(450);
    });
  });
});
