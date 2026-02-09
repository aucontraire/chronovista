/**
 * Tests for useSearchSegments Hook
 *
 * Tests edge case handling:
 * - T057: Concurrent search handling (FR-023, EC-019)
 * - T059: Malformed backend response handling (EC-017)
 */

import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSearchSegments } from "../../hooks/useSearchSegments";
import type { SearchResponse } from "../../types/search";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

import { apiFetch } from "../../api/config";

describe("useSearchSegments", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  const mockResponse: SearchResponse = {
    data: [
      {
        segment_id: 1,
        video_id: "dQw4w9WgXcQ",
        video_title: "Test Video",
        channel_title: "Test Channel",
        language_code: "en",
        text: "This is a test transcript segment",
        start_time: 10.5,
        end_time: 15.2,
        context_before: "Previous context",
        context_after: "Next context",
        match_count: 2,
        video_upload_date: "2023-01-01T00:00:00Z",
      },
    ],
    pagination: {
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
    available_languages: ["en"],
  };

  describe("Basic functionality", () => {
    it("should not execute query when query is too short", () => {
      const { result } = renderHook(
        () => useSearchSegments({ query: "a", language: null }),
        { wrapper }
      );

      expect(result.current.segments).toEqual([]);
      expect(result.current.isLoading).toBe(false);
      expect(apiFetch).not.toHaveBeenCalled();
    });

    it("should execute query when query meets minimum length", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      expect(result.current.segments).toHaveLength(1);
      expect(result.current.total).toBe(1);
    });

    it("should include language parameter when provided", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test", language: "en" }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      const callArgs = vi.mocked(apiFetch).mock.calls[0];
      if (callArgs) {
        expect(callArgs[0]).toContain("language=en");
      }
    });
  });

  describe("T057: Concurrent search handling (FR-023, EC-019)", () => {
    it("should pass AbortSignal to apiFetch for cancellation support", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      const callArgs = vi.mocked(apiFetch).mock.calls[0];
      if (callArgs) {
        const options = callArgs[1];
        expect(options).toHaveProperty("signal");
        expect(options?.signal).toBeInstanceOf(AbortSignal);
      }
    });

    it("should handle query change by updating queryKey", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { rerender } = renderHook(
        ({ query }) => useSearchSegments({ query, language: null }),
        {
          wrapper,
          initialProps: { query: "test1" },
        }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(1);
      });

      // Change query - should trigger new request
      rerender({ query: "test2" });

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });
    });

    it("should handle AbortError gracefully (query cancellation)", async () => {
      const abortError = new DOMException("The operation was aborted", "AbortError");
      vi.mocked(apiFetch).mockRejectedValue(abortError);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // TanStack Query handles AbortError gracefully - should not show error state
      expect(result.current.segments).toEqual([]);
    });
  });

  describe("T059: Malformed backend response handling (EC-017)", () => {
    it("should handle missing pagination data gracefully", async () => {
      const malformedResponse = {
        data: mockResponse.data,
        pagination: null as any, // Malformed: pagination is null
      };

      vi.mocked(apiFetch).mockResolvedValue(malformedResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should still return data even if pagination is missing (graceful degradation)
      expect(result.current.segments).toEqual(mockResponse.data);
      expect(result.current.total).toBe(null);
      expect(result.current.hasNextPage).toBe(false);
    });

    it("should handle missing data array gracefully", async () => {
      const malformedResponse = {
        data: null as any, // Malformed: data is null
        pagination: mockResponse.pagination,
      };

      vi.mocked(apiFetch).mockResolvedValue(malformedResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should handle gracefully with empty array
      expect(result.current.segments).toEqual([]);
    });

    it("should handle malformed pagination metadata in getNextPageParam", async () => {
      const malformedResponse = {
        data: mockResponse.data,
        pagination: {
          total: "invalid" as any, // Malformed: should be number
          limit: null as any, // Malformed: should be number
          offset: "0" as any, // Malformed: should be number
          has_more: "true" as any, // Malformed: should be boolean
        },
      };

      vi.mocked(apiFetch).mockResolvedValue(malformedResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should not crash and should not have next page
      expect(result.current.hasNextPage).toBe(false);
    });

    it("should handle completely invalid response structure", async () => {
      const malformedResponse = "invalid json" as any;

      vi.mocked(apiFetch).mockResolvedValue(malformedResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should fallback to empty state
      expect(result.current.segments).toEqual([]);
      expect(result.current.total).toBe(null);
    });

    it("should preserve existing results when pagination fails", async () => {
      // First request succeeds
      vi.mocked(apiFetch).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(1);
      });

      // Second request (pagination) returns malformed data
      const malformedResponse = { invalid: "data" } as any;
      vi.mocked(apiFetch).mockResolvedValueOnce(malformedResponse);

      // Try to fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      // Should preserve the first page results even if second page fails
      expect(result.current.segments).toHaveLength(1);
    });

    it("should handle missing has_more field in pagination", async () => {
      const responseWithoutHasMore = {
        data: mockResponse.data,
        pagination: {
          total: 1,
          limit: 20,
          offset: 0,
          // has_more is missing
        } as any,
      };

      vi.mocked(apiFetch).mockResolvedValue(responseWithoutHasMore);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should default to no more pages
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  describe("Pagination", () => {
    it("should handle pagination correctly", async () => {
      const firstSegment = mockResponse.data[0];
      if (!firstSegment) {
        throw new Error("Mock data missing first segment");
      }

      const page1Response: SearchResponse = {
        data: [firstSegment],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
        available_languages: ["en"],
      };

      const page2Response: SearchResponse = {
        data: [{ ...firstSegment, segment_id: 2, text: "Second segment" }],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
        available_languages: ["en"],
      };

      vi.mocked(apiFetch)
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(1);
      });

      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(2);
      });

      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.total).toBe(2);
    });

    it("should return available languages from API (not from loaded pages)", async () => {
      // This tests the bug fix: availableLanguages should come from API's full result set,
      // not from currently loaded segments
      const page1Response: SearchResponse = {
        data: [
          {
            segment_id: 1,
            video_id: "dQw4w9WgXcQ",
            video_title: "English Video",
            channel_title: "Test Channel",
            language_code: "en",
            text: "English segment",
            start_time: 0,
            end_time: 5,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2023-01-01T00:00:00Z",
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
        // Even though only English is in this page, API reports all languages in full result set
        available_languages: ["en", "es"],
      };

      vi.mocked(apiFetch).mockResolvedValueOnce(page1Response);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(1);
      });

      // Should show ALL languages from full result set, not just from loaded segments
      expect(result.current.availableLanguages).toEqual(["en", "es"]);
      // Loaded segments only have English
      const firstSegment = result.current.segments[0];
      if (firstSegment) {
        expect(firstSegment.language_code).toBe("en");
      }
    });
  });

  describe("Error handling", () => {
    it("should handle network errors", async () => {
      const networkError = new Error("Network error");
      vi.mocked(apiFetch).mockRejectedValue(networkError);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(networkError);
      expect(result.current.segments).toEqual([]);
    });
  });
});
