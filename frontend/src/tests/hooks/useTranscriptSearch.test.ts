/**
 * Unit tests for useTranscriptSearch hook.
 *
 * Tests client-side transcript search with debouncing, navigation, and edge cases.
 * Implements FR-011, FR-013, FR-020 requirements.
 *
 * @module tests/hooks/useTranscriptSearch
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTranscriptSearch } from "../../hooks/useTranscriptSearch";
import type { TranscriptSegment } from "../../types/transcript";

/**
 * Creates a minimal TranscriptSegment for testing.
 */
function makeSegment(id: number, text: string): TranscriptSegment {
  return {
    id,
    text,
    start_time: id * 5,
    end_time: id * 5 + 4.5,
    duration: 4.5,
    has_correction: false,
    corrected_at: null,
    correction_count: 0,
  };
}

describe("useTranscriptSearch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const segments: TranscriptSegment[] = [
    makeSegment(0, "Hello world"),
    makeSegment(1, "Welcome to the world of testing"),
    makeSegment(2, "Testing is important"),
    makeSegment(3, "No match here at all"),
  ];

  describe("initial state", () => {
    it("returns empty matches with empty initial query", () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      expect(result.current.matches).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.currentIndex).toBe(0);
      expect(result.current.query).toBe("");
    });

    it("returns empty matches when query is only whitespace", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("   ");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.matches).toHaveLength(0);
      expect(result.current.total).toBe(0);
    });
  });

  describe("case-insensitive matching", () => {
    it("matches lowercase query against uppercase text", async () => {
      const mixedSegments = [makeSegment(0, "HELLO World")];
      const { result } = renderHook(() => useTranscriptSearch(mixedSegments));

      act(() => {
        result.current.setQuery("hello");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(1);
      expect(result.current.matches[0]).toMatchObject({
        segmentIndex: 0,
        startOffset: 0,
        length: 5,
      });
    });

    it("matches uppercase query against lowercase text", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("WORLD");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // "world" appears in segment 0 and segment 1
      expect(result.current.total).toBe(2);
    });

    it("matches mixed-case query", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("WoRlD");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(2);
    });
  });

  describe("match count accuracy", () => {
    it("counts a single match correctly", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("Hello");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(1);
      expect(result.current.matches[0]).toMatchObject({
        segmentIndex: 0,
        startOffset: 0,
        length: 5,
      });
    });

    it("counts multiple matches across different segments", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // "world" in segment 0 ("Hello world") and segment 1 ("...world of testing")
      expect(result.current.total).toBe(2);
    });

    it("counts multiple matches within a single segment", async () => {
      const repeatingSegments = [
        makeSegment(0, "test test test"),
      ];
      const { result } = renderHook(() => useTranscriptSearch(repeatingSegments));

      act(() => {
        result.current.setQuery("test");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(3);
    });

    it("counts correctly when query matches at end of segment", async () => {
      const edgeSegments = [makeSegment(0, "prefix suffix")];
      const { result } = renderHook(() => useTranscriptSearch(edgeSegments));

      act(() => {
        result.current.setQuery("suffix");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(1);
      expect(result.current.matches[0]).toMatchObject({
        segmentIndex: 0,
        startOffset: 7,
        length: 6,
      });
    });

    it("returns zero matches when query is not found", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("xyznotfound");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(0);
      expect(result.current.matches).toHaveLength(0);
    });
  });

  describe("next/prev navigation with wraparound", () => {
    it("navigates to next match", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Start at index 0
      expect(result.current.currentIndex).toBe(0);

      act(() => {
        result.current.next();
      });

      // Should advance to index 1
      expect(result.current.currentIndex).toBe(1);
    });

    it("wraps from last match to first on next()", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Move to last match (index 1 of 2 total)
      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(1);

      // Next from last should wrap to first
      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(0);
    });

    it("wraps from first match to last on prev()", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // At first match (index 0); prev should wrap to last (index 1)
      act(() => {
        result.current.prev();
      });

      expect(result.current.currentIndex).toBe(1);
    });

    it("navigates to previous match", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Move to second match first
      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(1);

      // Go back to first
      act(() => {
        result.current.prev();
      });

      expect(result.current.currentIndex).toBe(0);
    });

    it("does nothing on next() when there are no matches", () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      // No query set, no matches
      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(0);
    });

    it("does nothing on prev() when there are no matches", () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.prev();
      });

      expect(result.current.currentIndex).toBe(0);
    });

    it("resets to index 0 when query changes", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(1);

      // Change query
      act(() => {
        result.current.setQuery("testing");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.currentIndex).toBe(0);
    });
  });

  describe("debounce behavior (FR-020)", () => {
    it("does not update query immediately on setQuery", () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      // Query should not be applied yet (before debounce fires)
      expect(result.current.query).toBe("");
      expect(result.current.total).toBe(0);
    });

    it("applies query after 300ms debounce", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      expect(result.current.query).toBe("");

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.query).toBe("world");
      expect(result.current.total).toBe(2);
    });

    it("debounces rapid typing — only fires once after 300ms of silence", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      // Simulate rapid keystrokes
      act(() => {
        result.current.setQuery("w");
      });
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      act(() => {
        result.current.setQuery("wo");
      });
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      act(() => {
        result.current.setQuery("wor");
      });
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      act(() => {
        result.current.setQuery("world");
      });

      // Query still not committed (only 100ms each, total 400ms but last reset timer)
      expect(result.current.query).toBe("");

      // Advance the final 300ms
      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Should have committed "world" — not intermediate values
      expect(result.current.query).toBe("world");
      expect(result.current.total).toBe(2);
    });
  });

  describe("empty query returns no matches", () => {
    it("returns no matches for empty string", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(0);
      expect(result.current.matches).toHaveLength(0);
    });

    it("returns no matches when segments array is empty", async () => {
      const { result } = renderHook(() => useTranscriptSearch([]));

      act(() => {
        result.current.setQuery("hello");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(0);
    });
  });

  describe("reset functionality", () => {
    it("clears query and matches on reset()", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.total).toBe(2);

      act(() => {
        result.current.reset();
      });

      expect(result.current.query).toBe("");
      expect(result.current.total).toBe(0);
      expect(result.current.currentIndex).toBe(0);
    });

    it("cancels pending debounce on reset()", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      // Before debounce fires, reset
      act(() => {
        result.current.reset();
      });

      // Even after 300ms, query should remain empty
      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.query).toBe("");
      expect(result.current.total).toBe(0);
    });

    it("resets navigation index to 0", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      act(() => {
        result.current.next();
      });

      expect(result.current.currentIndex).toBe(1);

      act(() => {
        result.current.reset();
      });

      expect(result.current.currentIndex).toBe(0);
    });
  });

  describe("match position accuracy", () => {
    it("tracks correct segmentIndex for each match", async () => {
      const { result } = renderHook(() => useTranscriptSearch(segments));

      act(() => {
        result.current.setQuery("world");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // First match should be in segment 0 ("Hello world")
      expect(result.current.matches[0]).toMatchObject({ segmentIndex: 0 });
      // Second match should be in segment 1 ("Welcome to the world of testing")
      expect(result.current.matches[1]).toMatchObject({ segmentIndex: 1 });
    });

    it("tracks correct startOffset for match", async () => {
      const preciseSegments = [makeSegment(0, "abc def abc")];
      const { result } = renderHook(() => useTranscriptSearch(preciseSegments));

      act(() => {
        result.current.setQuery("abc");
      });

      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(result.current.matches).toHaveLength(2);
      expect(result.current.matches[0]).toMatchObject({ startOffset: 0, length: 3 });
      expect(result.current.matches[1]).toMatchObject({ startOffset: 8, length: 3 });
    });
  });
});
