/**
 * Tests for TranscriptSegments - Search Navigation Scrolling
 *
 * Regression coverage for the bug where next/prev search navigation scrolled
 * to the wrong position for matches deep in a virtualized list. The old
 * effect computed `activeSegmentIndex * VIRTUALIZATION_CONFIG.estimatedHeight`
 * against the container's raw `scrollTop` — a fixed-row-height estimate that
 * accumulated positional error against the real (variable-height) rows the
 * further down the list it went, so the target segment was often scrolled
 * past the virtualizer's render window and never rendered at all.
 *
 * The fix moves the scroll into the list components that hold the measured
 * data:
 * - VirtualizedSegmentList calls `virtualizer.scrollToIndex(index, { align:
 *   "center" })`, which uses the virtualizer's own measured offsets and
 *   re-corrects once the target renders.
 * - StandardSegmentList (no virtualization) uses querySelector +
 *   scrollIntoView, since every row is already in the DOM.
 *
 * This file uses a purpose-built `useVirtualizer` mock (not the file-global
 * `getVirtualItems: () => []` mock used by sibling test files, which would
 * make this regression untestable — nothing ever renders under it). The mock
 * simulates react-virtual's real behavior: `scrollToIndex` shifts the
 * rendered window so a subsequent `getVirtualItems()` call includes the
 * target index.
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act } from "react";
import { TranscriptSegments } from "../TranscriptSegments";
import type { TranscriptSegment } from "../../../types/transcript";
import type { TranscriptSearchMatch } from "../../../hooks/useTranscriptSearch";

// Mock dependencies (same set as sibling TranscriptSegments test files)
vi.mock("../../../hooks/useTranscriptSegments", () => ({
  useTranscriptSegments: vi.fn(),
}));

vi.mock("../../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn(() => false),
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

/**
 * Purpose-built useVirtualizer mock that simulates real react-virtual
 * scrolling behavior: `scrollToIndex` shifts an internal windowStart (held
 * via a real React useState, so the call triggers a re-render like the
 * genuine virtualizer's DOM scroll -> internal state update does), and
 * `getVirtualItems` returns a window of items around that start, expanded to
 * always include index 0 (mirrors overscan always covering the top on
 * mount).
 */
const WINDOW_SIZE = 10;
const scrollToIndexMock = vi.fn();

vi.mock("@tanstack/react-virtual", async () => {
  const React = await import("react");

  return {
    useVirtualizer: (options: {
      count: number;
      getItemKey?: (index: number) => number | string;
    }) => {
      const [windowStart, setWindowStart] = React.useState(0);
      const { count, getItemKey } = options;

      const scrollToIndex = (
        index: number,
        opts?: { align?: string }
      ) => {
        scrollToIndexMock(index, opts);
        const half = Math.floor(WINDOW_SIZE / 2);
        setWindowStart(Math.max(0, Math.min(index - half, Math.max(0, count - WINDOW_SIZE))));
      };

      const start = Math.max(0, Math.min(windowStart, Math.max(0, count - WINDOW_SIZE)));
      const end = Math.min(count, start + WINDOW_SIZE);

      const virtualItems: { index: number; key: number | string; start: number; size: number }[] =
        [];
      for (let i = start; i < end; i++) {
        virtualItems.push({
          index: i,
          key: getItemKey ? getItemKey(i) : i,
          start: i * 48,
          size: 48,
        });
      }

      return {
        getVirtualItems: () => virtualItems,
        getTotalSize: () => count * 48,
        measureElement: vi.fn(),
        scrollToIndex,
      };
    },
  };
});

// Import after mocks to get mocked versions
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
 * Builds a searchProps object with a single match at the given segment
 * index, marked as the active match.
 */
function createSearchProps(
  activeSegmentIndex: number,
  overrides: Partial<{
    matches: TranscriptSearchMatch[];
    activeMatchIndex: number;
  }> = {}
) {
  const matches: TranscriptSearchMatch[] = overrides.matches ?? [
    { segmentIndex: activeSegmentIndex, startOffset: 0, length: 6 },
  ];

  return {
    matches,
    activeMatchIndex: overrides.activeMatchIndex ?? 0,
    onSegmentsChange: vi.fn(),
    activeMatchContainerRef: { current: null },
    searchQuery: "target",
    activeSegmentIndex,
  };
}

describe("TranscriptSegments - Search Navigation Scrolling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useTranscriptSegments).mockReturnValue(createDefaultHookReturn());
  });

  describe("Virtualized list — far match (regression)", () => {
    it("scrolls to and renders a match far beyond the initial virtual window", () => {
      // 300 segments comfortably clears the virtualization threshold (50).
      const segments = createTestSegments(300);
      const farIndex = 200;
      segments[farIndex] = createTestSegment({
        id: farIndex + 1,
        text: "target word here",
        start_time: farIndex * 5,
        end_time: farIndex * 5 + 5,
        duration: 5,
      });

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          searchProps={createSearchProps(farIndex)}
        />
      );

      // The old scrollTop = index * 48 math never called any virtualizer
      // method and never rendered the far row — this assertion is what
      // would fail against that implementation.
      expect(scrollToIndexMock).toHaveBeenCalledWith(farIndex, {
        align: "center",
      });

      // The far segment's row must actually be in the DOM (the virtual
      // window shifted to include it) ...
      const farRow = container.querySelector(
        `[data-segment-id="${farIndex + 1}"]`
      );
      expect(farRow).not.toBeNull();

      // ... and its active match must be highlighted via TextHighlighter's
      // <mark aria-current="true"> — proof the row rendered with the right
      // search state, not just that some row exists at that DOM position.
      const activeMark = farRow?.querySelector('mark[aria-current="true"]');
      expect(activeMark).not.toBeNull();
      expect(activeMark?.textContent).toBe("target");
    });

    it("does not call scrollToIndex again when the active index is unchanged", () => {
      const segments = createTestSegments(300);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      // Index 5 is inside the initial render window (0-9), i.e. an
      // already-visible/nearby match.
      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          searchProps={createSearchProps(5)}
        />
      );

      expect(scrollToIndexMock).toHaveBeenCalledTimes(1);
      expect(scrollToIndexMock).toHaveBeenCalledWith(5, { align: "center" });

      // Simulate a new page loading (matches array identity changes) while
      // the user's active match index stays the same — must NOT re-scroll.
      act(() => {
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            searchProps={createSearchProps(5, {
              matches: [
                { segmentIndex: 5, startOffset: 0, length: 6 },
                { segmentIndex: 42, startOffset: 0, length: 6 },
              ],
            })}
          />
        );
      });

      expect(scrollToIndexMock).toHaveBeenCalledTimes(1);
    });

    it("scrolls again when the active index changes to a different nearby match", () => {
      const segments = createTestSegments(300);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          searchProps={createSearchProps(5)}
        />
      );

      expect(scrollToIndexMock).toHaveBeenCalledTimes(1);

      act(() => {
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            searchProps={createSearchProps(6)}
          />
        );
      });

      expect(scrollToIndexMock).toHaveBeenCalledTimes(2);
      expect(scrollToIndexMock).toHaveBeenLastCalledWith(6, {
        align: "center",
      });
    });
  });

  describe("Standard (non-virtualized) list", () => {
    it("scrolls to and highlights the active match via scrollIntoView", () => {
      // Fewer than 50 segments stays under the virtualization threshold.
      const segments = createTestSegments(30);
      const targetIndex = 25;
      segments[targetIndex] = createTestSegment({
        id: targetIndex + 1,
        text: "target word here",
        start_time: targetIndex * 5,
        end_time: targetIndex * 5 + 5,
        duration: 5,
      });

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const scrollIntoViewMock = vi.fn();
      Element.prototype.scrollIntoView =
        scrollIntoViewMock as unknown as typeof Element.prototype.scrollIntoView;

      const { container } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          searchProps={createSearchProps(targetIndex)}
        />
      );

      expect(scrollIntoViewMock).toHaveBeenCalledWith(
        expect.objectContaining({ block: "center" })
      );

      const targetRow = container.querySelector(
        `[data-segment-id="${targetIndex + 1}"]`
      );
      const activeMark = targetRow?.querySelector('mark[aria-current="true"]');
      expect(activeMark).not.toBeNull();

      // scrollToIndex (the virtualized path) must NOT be used here.
      expect(scrollToIndexMock).not.toHaveBeenCalled();
    });

    it("does not call scrollIntoView again when the active index is unchanged", () => {
      const segments = createTestSegments(30);

      vi.mocked(useTranscriptSegments).mockReturnValue(
        createDefaultHookReturn(segments)
      );

      const scrollIntoViewMock = vi.fn();
      Element.prototype.scrollIntoView =
        scrollIntoViewMock as unknown as typeof Element.prototype.scrollIntoView;

      const { rerender } = render(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
          searchProps={createSearchProps(3)}
        />
      );

      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);

      act(() => {
        rerender(
          <TranscriptSegments
            videoId="test-video"
            languageCode="en"
            searchProps={createSearchProps(3, {
              matches: [
                { segmentIndex: 3, startOffset: 0, length: 6 },
                { segmentIndex: 10, startOffset: 0, length: 6 },
              ],
            })}
          />
        );
      });

      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
    });
  });
});
