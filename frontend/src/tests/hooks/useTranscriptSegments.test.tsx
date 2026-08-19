/**
 * Unit tests for useTranscriptSegments hook.
 *
 * Tests TanStack Query infinite scroll integration for fetching transcript segments.
 * Implements FR-020a, FR-020b, NFR-P02, NFR-P04-P06.
 *
 * @module tests/hooks/useTranscriptSegments
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useTranscriptSegments } from "../../hooks/useTranscriptSegments";
import type { TranscriptSegment, SegmentListResponse } from "../../types/transcript";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("useTranscriptSegments", () => {
  let queryClient: QueryClient;

  const createMockSegments = (start: number, count: number): TranscriptSegment[] => {
    return Array.from({ length: count }, (_, i) => ({
      id: start + i,
      text: `Segment ${start + i} text content`,
      start_time: (start + i) * 5,
      end_time: (start + i) * 5 + 4.5,
      duration: 4.5,
      has_correction: false,
      corrected_at: null,
      correction_count: 0,
    }));
  };

  const createMockResponse = (
    offset: number,
    limit: number,
    total: number
  ): SegmentListResponse => {
    const segments = createMockSegments(offset + 1, Math.min(limit, total - offset));
    return {
      data: segments,
      pagination: {
        total,
        limit,
        offset,
        has_more: offset + limit < total,
      },
    };
  };

  // Counter to ensure unique video IDs across all tests
  let testCounter = 0;
  const getUniqueVideoId = () => `video-${Date.now()}-${++testCounter}`;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0, // Disable garbage collection caching
          staleTime: 0, // Always consider data stale
        },
      },
    });

    vi.clearAllMocks();
  });

  afterEach(async () => {
    // Clear all queries and ensure cleanup
    queryClient.clear();
    queryClient.removeQueries();
    await queryClient.cancelQueries();
    vi.resetAllMocks();
  });

  const createWrapper = () => {
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  describe("initial batch loading (FR-020a)", () => {
    it("loads initial batch of 50 segments", async () => {
      const mockResponse = createMockResponse(0, 50, 150);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useTranscriptSegments("dQw4w9WgXcQ", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      expect(result.current.totalCount).toBe(150);
      expect(result.current.hasNextPage).toBe(true);
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        "/videos/dQw4w9WgXcQ/transcript/segments?language=en&offset=0&limit=50",
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );
    });

    it("sets hasNextPage to false when all segments loaded initially", async () => {
      const mockResponse = createMockResponse(0, 50, 30);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useTranscriptSegments("test-1", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(30);
        },
        { timeout: 10000 }
      );

      expect(result.current.hasNextPage).toBe(false);
    });
  });

  describe("pagination with subsequent batches (FR-020b)", () => {
    it("loads subsequent batches of 25 segments", async () => {
      const mockResponse1 = createMockResponse(0, 50, 100);
      const mockResponse2 = createMockResponse(50, 25, 100);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      const { result } = renderHook(
        () => useTranscriptSegments("test-2", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      // Fetch next page
      await act(async () => {
        result.current.fetchNextPage();
      });

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(75);
        },
        { timeout: 10000 }
      );

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        "/videos/test-2/transcript/segments?language=en&offset=50&limit=25",
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );
    });

    it("loads multiple subsequent pages correctly", async () => {
      const mockResponse1 = createMockResponse(0, 50, 150);
      const mockResponse2 = createMockResponse(50, 25, 150);
      const mockResponse3 = createMockResponse(75, 25, 150);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2)
        .mockResolvedValueOnce(mockResponse3);

      const { result } = renderHook(
        () => useTranscriptSegments("test-3", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      await act(async () => {
        result.current.fetchNextPage();
      });

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(75);
        },
        { timeout: 10000 }
      );

      await act(async () => {
        result.current.fetchNextPage();
      });

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(100);
        },
        { timeout: 10000 }
      );

      expect(result.current.hasNextPage).toBe(true);
    });
  });

  describe("getNextPageParam logic", () => {
    it("returns undefined when has_more is false", async () => {
      const mockResponse = createMockResponse(0, 50, 50);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useTranscriptSegments("test-4", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.hasNextPage).toBe(false);
        },
        { timeout: 10000 }
      );
    });

    it("returns correct offset and limit for next page", { timeout: 15000 }, async () => {
      const mockResponse1 = createMockResponse(0, 50, 150);
      const mockResponse2 = createMockResponse(50, 25, 150);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      const { result } = renderHook(
        () => useTranscriptSegments("test-video-1", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.hasNextPage).toBe(true);
        },
        { timeout: 10000 }
      );

      await act(async () => {
        result.current.fetchNextPage();
      });

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(75);
        },
        { timeout: 10000 }
      );
    });
  });

  describe("loading states", () => {
    it("shows initial loading state", async () => {
      vi.mocked(apiConfig.apiFetch).mockImplementationOnce(
        () => new Promise(() => {}) // Never resolves
      );

      const { result } = renderHook(
        () => useTranscriptSegments("test-5", "en"),
        { wrapper: createWrapper() }
      );

      // Wait for the query to start processing (after debounce)
      await waitFor(
        () => {
          expect(result.current.isLoading).toBe(true);
        },
        { timeout: 10000 }
      );

      expect(result.current.isFetchingNextPage).toBe(false);
      expect(result.current.segments).toHaveLength(0);
    });

    it("shows fetchingNextPage state when loading more segments", { timeout: 15000 }, async () => {
      const mockResponse1 = createMockResponse(0, 50, 100);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockImplementationOnce(() => new Promise(() => {})); // Never resolves

      const { result } = renderHook(
        () => useTranscriptSegments("test-video-2", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      await act(async () => {
        result.current.fetchNextPage();
      });

      // Wait for fetchNextPage to start
      await waitFor(
        () => {
          expect(result.current.isFetchingNextPage).toBe(true);
        },
        { timeout: 10000 }
      );

      expect(result.current.isLoading).toBe(false);
    });
  });

  describe("error handling", () => {
    it("handles API errors", { timeout: 15000 }, async () => {
      const apiError = {
        type: "server" as const,
        message: "Failed to fetch segments",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(apiError);

      const { result } = renderHook(
        () => useTranscriptSegments("test-video-3", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 10000 }
      );

      expect(result.current.error).toEqual(apiError);
      expect(result.current.segments).toHaveLength(0);
    });

    it("provides retry function for error recovery", { timeout: 15000 }, async () => {
      const apiError = {
        type: "timeout" as const,
        message: "Request timeout",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch)
        .mockRejectedValueOnce(apiError)
        .mockResolvedValueOnce(createMockResponse(0, 50, 100));

      const { result } = renderHook(
        () => useTranscriptSegments("test-video-4", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 10000 }
      );

      // Retry after error
      await act(async () => {
        result.current.retry();
      });

      await waitFor(
        () => {
          expect(result.current.isError).toBe(false);
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );
    });
  });

  describe("query enabled/disabled", () => {
    it("does not fetch when enabled is false", () => {
      const { result } = renderHook(
        () => useTranscriptSegments("test-6", "en", false),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("does not fetch when videoId is empty", () => {
      const { result } = renderHook(
        () => useTranscriptSegments("", "en"),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("does not fetch when languageCode is empty", () => {
      const { result } = renderHook(
        () => useTranscriptSegments("test-7", ""),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });
  });

  describe("language switching and cancellation (NFR-P04-P06)", () => {
    it("cancels previous requests when language changes", { timeout: 15000 }, async () => {
      const mockResponse1 = createMockResponse(0, 50, 100);
      const mockResponse2 = createMockResponse(0, 50, 100);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      let language = "en";
      const { result, rerender } = renderHook(
        () => useTranscriptSegments("test-video-5", language),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      // Change language
      language = "es";
      rerender();

      await waitFor(
        () => {
          expect(apiConfig.apiFetch).toHaveBeenCalledWith(
            "/videos/test-video-5/transcript/segments?language=es&offset=0&limit=50",
            expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
          );
        },
        { timeout: 10000 }
      );
    });

    it("provides cancelRequests function", async () => {
      const mockResponse = createMockResponse(0, 50, 100);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useTranscriptSegments("test-8", "en"),
        { wrapper: createWrapper() }
      );

      expect(typeof result.current.cancelRequests).toBe("function");

      // Should not throw when called
      await act(async () => {
        result.current.cancelRequests();
      });
    });
  });

  describe("debounce for language switching (NFR-P05)", () => {
    it("applies 150ms debounce delay on initial load", async () => {
      const mockResponse = createMockResponse(0, 50, 100);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useTranscriptSegments("test-9", "en"),
        { wrapper: createWrapper() }
      );

      // Should not call API immediately (debounced)
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();

      // Wait for debounce delay and API call
      await waitFor(
        () => {
          expect(apiConfig.apiFetch).toHaveBeenCalled();
        },
        { timeout: 10000 }
      );
    });
  });

  describe("timeout handling (NFR-P02)", () => {
    it("applies 5 second timeout to segment batch loads", async () => {
      const mockResponse = createMockResponse(0, 50, 100);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useTranscriptSegments("test-10", "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(apiConfig.apiFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
          );
        },
        { timeout: 10000 }
      );
    });
  });

  describe("helper properties", () => {
    it("provides totalCount from pagination", { timeout: 15000 }, async () => {
      const videoId = getUniqueVideoId();
      const mockResponse = createMockResponse(0, 50, 150);
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
        },
        { timeout: 10000 }
      );

      expect(result.current.totalCount).toBe(150);
    });

    it("flattens all pages into single segments array", { timeout: 15000 }, async () => {
      const videoId = getUniqueVideoId();
      // Create responses where second batch has 25 segments (50+25=75 total)
      const mockResponse1 = createMockResponse(0, 50, 75);
      const mockResponse2 = createMockResponse(50, 25, 75);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );

      // Wait for initial load
      await waitFor(
        () => {
          expect(result.current.segments).toHaveLength(50);
          expect(result.current.hasNextPage).toBe(true);
        },
        { timeout: 10000 }
      );

      // Verify only 1 call so far
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);

      // Fetch next page
      await act(async () => {
        result.current.fetchNextPage();
      });

      // Wait for second page
      await waitFor(
        () => {
          expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2);
          expect(result.current.segments).toHaveLength(75);
        },
        { timeout: 10000 }
      );

      // Segments should be a flat array, not nested pages
      expect(Array.isArray(result.current.segments)).toBe(true);
      expect(result.current.segments[0]).toHaveProperty("text");
      expect(result.current.segments[50]).toHaveProperty("text");
      // No more pages after this
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  describe("deep-link seek: absolute-offset computation", () => {
    it("computes offset as full_total minus filtered_total and fetches a window centered on it", async () => {
      const videoId = getUniqueVideoId();

      // Initial (non-deep-link) load — unaffected by deep-link windowing.
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 300));

      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(
        () => expect(result.current.segments).toHaveLength(50),
        { timeout: 10000 }
      );

      // full_total = 300 (limit=1 probe, no start_time)
      const fullTotalResponse = createMockResponse(0, 1, 300);
      // filtered_total = 200 (limit=1 probe with start_time) — 200 segments
      // remain at/after the target, so absoluteOffset = 300 - 200 = 100.
      const filteredTotalResponse = createMockResponse(0, 1, 200);
      // Window: radius 75 -> offset = max(0, 100-75) = 25, limit = 150.
      const windowResponse = createMockResponse(25, 150, 300);

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(fullTotalResponse)
        .mockResolvedValueOnce(filteredTotalResponse)
        .mockResolvedValueOnce(windowResponse);

      let seekResult: boolean | undefined;
      await act(async () => {
        seekResult = await result.current.seekToTimestamp(500);
      });

      expect(seekResult).toBe(true);

      // Call #2: full_total probe (offset=0, limit=1, no start_time)
      expect(apiConfig.apiFetch).toHaveBeenNthCalledWith(
        2,
        `/videos/${videoId}/transcript/segments?language=en&offset=0&limit=1`,
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );
      // Call #3: filtered_total probe (start_time=target, offset=0, limit=1)
      expect(apiConfig.apiFetch).toHaveBeenNthCalledWith(
        3,
        `/videos/${videoId}/transcript/segments?language=en&start_time=500&offset=0&limit=1`,
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );
      // Call #4: the actual window fetch — pure offset paging, no start_time
      expect(apiConfig.apiFetch).toHaveBeenNthCalledWith(
        4,
        `/videos/${videoId}/transcript/segments?language=en&offset=25&limit=150`,
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(150);
      });
    });

    it("floors the window offset at 0 when the target is near the start of the transcript", async () => {
      const videoId = getUniqueVideoId();

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 300));
      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );
      await waitFor(() => expect(result.current.segments).toHaveLength(50));

      // absoluteOffset = 300 - 290 = 10, which is less than the radius (75),
      // so the window must floor at offset 0 rather than go negative.
      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(createMockResponse(0, 1, 300))
        .mockResolvedValueOnce(createMockResponse(0, 1, 290))
        .mockResolvedValueOnce(createMockResponse(0, 150, 300));

      await act(async () => {
        await result.current.seekToTimestamp(50);
      });

      expect(apiConfig.apiFetch).toHaveBeenNthCalledWith(
        4,
        `/videos/${videoId}/transcript/segments?language=en&offset=0&limit=150`,
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );
    });

    it("returns false without installing a window when the transcript has no segments", async () => {
      const videoId = getUniqueVideoId();

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 0));
      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(createMockResponse(0, 1, 0))
        .mockResolvedValueOnce(createMockResponse(0, 1, 0));

      let seekResult: boolean | undefined;
      await act(async () => {
        seekResult = await result.current.seekToTimestamp(50);
      });

      expect(seekResult).toBe(false);
    });
  });

  describe("deep-link seek: contiguity regression (timestamp discontinuity fix)", () => {
    it("resets the cache to a single contiguous window instead of appending after the offset-0 pages", async () => {
      const videoId = getUniqueVideoId();

      // Normal initial load already populated offset-0 pages (segments 1-50).
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 300));
      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );
      await waitFor(() => expect(result.current.segments).toHaveLength(50));

      // Deep-link seek to a target far away from the initially-loaded segments.
      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(createMockResponse(0, 1, 300)) // full_total
        .mockResolvedValueOnce(createMockResponse(0, 1, 200)) // filtered_total
        .mockResolvedValueOnce(createMockResponse(25, 150, 300)); // window (ids 26-175)

      await act(async () => {
        await result.current.seekToTimestamp(500);
      });

      await waitFor(() => expect(result.current.segments).toHaveLength(150));

      // REGRESSION: the array must be exactly the window (150), never
      // 50 (stale offset-0 page) + 150 (appended window) = 200. Appending
      // is precisely the bug — it leaves an un-fetched gap between the
      // offset-0 segments and the time-windowed page.
      expect(result.current.segments).toHaveLength(150);

      // Every segment must be contiguous by start_time — no gaps and no
      // out-of-order jump (this is the actual symptom: scrolling up used to
      // jump from ~5:45 to ~8:58, skipping segments in between).
      const startTimes = result.current.segments.map((s) => s.start_time);
      for (let i = 1; i < startTimes.length; i++) {
        expect(startTimes[i]! - startTimes[i - 1]!).toBe(5);
      }

      // First segment of the window is id 26 (offset 25 -> 0-indexed segment
      // 25 -> id 26 under this test's mock convention), not id 1 — proving
      // the stale offset-0 page was discarded, not retained.
      expect(result.current.segments[0]!.id).toBe(26);
    });
  });

  describe("bidirectional paging: fetchPreviousPage", () => {
    it("has no previous page from a normal offset-0 initial load", async () => {
      const videoId = getUniqueVideoId();
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 300));

      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.segments).toHaveLength(50));
      expect(result.current.hasPreviousPage).toBe(false);
    });

    it("prepends earlier segments contiguously after a deep-link window is installed", async () => {
      const videoId = getUniqueVideoId();

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 50, 300));
      const { result } = renderHook(
        () => useTranscriptSegments(videoId, "en"),
        { wrapper: createWrapper() }
      );
      await waitFor(() => expect(result.current.segments).toHaveLength(50));

      // Install a deep-link window at offset 25, limit 150 (ids 26-175).
      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce(createMockResponse(0, 1, 300))
        .mockResolvedValueOnce(createMockResponse(0, 1, 200))
        .mockResolvedValueOnce(createMockResponse(25, 150, 300));

      await act(async () => {
        await result.current.seekToTimestamp(500);
      });
      await waitFor(() => expect(result.current.segments).toHaveLength(150));

      expect(result.current.hasPreviousPage).toBe(true);

      // Previous page must be exactly contiguous: offset 25 - limit(25) = 0.
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(createMockResponse(0, 25, 300));

      await act(async () => {
        result.current.fetchPreviousPage();
      });

      await waitFor(() => expect(result.current.segments).toHaveLength(175));

      // Contiguous prepend: request was pure offset paging (no start_time).
      expect(apiConfig.apiFetch).toHaveBeenLastCalledWith(
        `/videos/${videoId}/transcript/segments?language=en&offset=0&limit=25`,
        expect.objectContaining({ externalSignal: expect.any(AbortSignal) })
      );

      // Prepended segments (ids 1-25) come first, followed by the original
      // window (ids 26-175) with no gap at the seam.
      expect(result.current.segments[0]!.id).toBe(1);
      expect(result.current.segments[24]!.id).toBe(25);
      expect(result.current.segments[25]!.id).toBe(26);

      const startTimes = result.current.segments.map((s) => s.start_time);
      for (let i = 1; i < startTimes.length; i++) {
        expect(startTimes[i]! - startTimes[i - 1]!).toBe(5);
      }

      // Reached offset 0 — no more previous pages.
      expect(result.current.hasPreviousPage).toBe(false);
    });
  });
});
