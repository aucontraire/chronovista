/**
 * Tests for useSearchSegments hook.
 *
 * Covers:
 * - Query enabled/disabled state based on minimum query length (boundary cases)
 * - Successful data fetching and empty results handling
 * - Language filter behavior and query key changes
 * - Pagination (page flattening, hasNextPage, offset calculation, isFetchingNextPage)
 * - T057: Concurrent search handling (FR-023, EC-019) - AbortSignal passthrough,
 *   query-change cancellation, AbortError handling
 * - T059: Malformed backend response handling (EC-017)
 * - Loading and error states (network errors and typed API errors)
 * - Query parameters passed to apiFetch (q, limit, offset)
 */

import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { useSearchSegments } from "../useSearchSegments";
import type { SearchResponse } from "../../types/search";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

import { apiFetch } from "../../api/config";

const mockApiFetch = vi.mocked(apiFetch);

/**
 * Create a fresh QueryClient for each test to avoid cross-test pollution.
 */
function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  });
}

/**
 * Wrapper component that provides QueryClient context.
 */
function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

/**
 * Factory for creating mock search responses.
 */
function createMockSearchResponse(
  overrides: Partial<SearchResponse> = {}
): SearchResponse {
  return {
    data: [
      {
        segment_id: 1,
        video_id: "abc123def45",
        video_title: "Test Video",
        channel_title: "Test Channel",
        language_code: "en",
        text: "This is a test segment with search terms",
        start_time: 10.5,
        end_time: 15.0,
        context_before: "Previous segment text",
        context_after: "Next segment text",
        match_count: 2,
        video_upload_date: "2024-01-15T12:00:00Z",
        availability_status: "available",
      },
    ],
    pagination: {
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
    available_languages: ["en"],
    ...overrides,
  };
}

describe("useSearchSegments", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  const wrapper = ({ children }: { children: ReactNode }) => (
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
        availability_status: "available",
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

  describe("Query Enabled State", () => {
    it("should NOT execute query when query length is less than 2", () => {
      const { result } = renderHook(
        () => useSearchSegments({ query: "a", language: null }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
      expect(result.current.segments).toHaveLength(0);
    });

    it("should NOT execute query when query is empty", () => {
      const { result } = renderHook(() => useSearchSegments({ query: "" }), {
        wrapper: createWrapper(queryClient),
      });

      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
      expect(result.current.segments).toHaveLength(0);
    });

    it("should execute query when query length is exactly 2", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      const { result } = renderHook(() => useSearchSegments({ query: "ab" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(1);
      expect(result.current.segments).toHaveLength(1);
    });

    it("should execute query when query length is greater than 2", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      const { result } = renderHook(
        () => useSearchSegments({ query: "test query" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(1);
      expect(result.current.segments).toHaveLength(1);
    });

    it("should execute query when query meets minimum length and expose total", async () => {
      mockApiFetch.mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalled();
      expect(result.current.segments).toHaveLength(1);
      expect(result.current.total).toBe(1);
    });
  });

  describe("Successful Data Fetching", () => {
    it("should return segments data when API call succeeds", async () => {
      const successResponse = createMockSearchResponse({
        data: [
          {
            segment_id: 1,
            video_id: "abc123def45",
            video_title: "Video One",
            channel_title: "Channel One",
            language_code: "en",
            text: "First matching segment",
            start_time: 10.0,
            end_time: 15.0,
            context_before: null,
            context_after: "Next text",
            match_count: 1,
            video_upload_date: "2024-01-15T12:00:00Z",
            availability_status: "available",
          },
          {
            segment_id: 2,
            video_id: "xyz789abc12",
            video_title: "Video Two",
            channel_title: "Channel Two",
            language_code: "en",
            text: "Second matching segment",
            start_time: 20.0,
            end_time: 25.0,
            context_before: "Before text",
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-02-20T14:00:00Z",
            availability_status: "available",
          },
        ],
        pagination: {
          total: 2,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(successResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "matching" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.segments).toHaveLength(2);
      expect(result.current.segments[0]?.video_title).toBe("Video One");
      expect(result.current.segments[1]?.video_title).toBe("Video Two");
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it("should handle empty results correctly", async () => {
      const emptyResponse = createMockSearchResponse({
        data: [],
        pagination: {
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(emptyResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "nonexistent" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.segments).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.loadedCount).toBe(0);
      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.isError).toBe(false);
    });
  });

  describe("Language Filter", () => {
    it("should include language parameter when provided", async () => {
      mockApiFetch.mockResolvedValue(mockResponse);

      renderHook(() => useSearchSegments({ query: "test", language: "en" }), {
        wrapper,
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      const callArgs = mockApiFetch.mock.calls[0];
      if (callArgs) {
        expect(callArgs[0]).toContain("language=en");
      }
    });

    it("should pass language filter to API when provided", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "test", language: "es" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("language=es"),
        expect.any(Object)
      );
    });

    it("should NOT include language parameter when language is null", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "test", language: null }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.not.stringContaining("language="),
        expect.any(Object)
      );
    });

    it("should NOT include language parameter when language is undefined", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.not.stringContaining("language="),
        expect.any(Object)
      );
    });

    it("should include correct query key with language (new request per language)", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      const { result: result1 } = renderHook(
        () => useSearchSegments({ query: "test", language: "en" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
      });

      // Different language should trigger a new query
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      const { result: result2 } = renderHook(
        () => useSearchSegments({ query: "test", language: "es" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result2.current.isLoading).toBe(false);
      });

      // Should have been called twice for different languages
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe("T057: Concurrent search handling (FR-023, EC-019)", () => {
    it("should pass AbortSignal to apiFetch for cancellation support", async () => {
      mockApiFetch.mockResolvedValue(mockResponse);

      renderHook(() => useSearchSegments({ query: "test", language: null }), {
        wrapper,
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          externalSignal: expect.any(AbortSignal),
        })
      );

      const callArgs = mockApiFetch.mock.calls[0];
      if (callArgs) {
        const options = callArgs[1];
        expect(options).toHaveProperty("externalSignal");
        expect(options?.externalSignal).toBeInstanceOf(AbortSignal);
      }
    });

    it("should handle query change by updating queryKey", async () => {
      mockApiFetch.mockResolvedValue(mockResponse);

      const { rerender } = renderHook(
        ({ query }) => useSearchSegments({ query, language: null }),
        {
          wrapper,
          initialProps: { query: "test1" },
        }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });

      // Change query - should trigger new request
      rerender({ query: "test2" });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });
    });

    it("should handle AbortError gracefully (query cancellation)", async () => {
      const abortError = new DOMException(
        "The operation was aborted",
        "AbortError"
      );
      mockApiFetch.mockRejectedValue(abortError);

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
        pagination: null as unknown as SearchResponse["pagination"],
      };

      mockApiFetch.mockResolvedValue(malformedResponse);

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
        data: null as unknown as SearchResponse["data"],
        pagination: mockResponse.pagination,
      };

      mockApiFetch.mockResolvedValue(malformedResponse);

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
          total: "invalid" as unknown as number,
          limit: null as unknown as number,
          offset: "0" as unknown as number,
          has_more: "true" as unknown as boolean,
        },
      };

      mockApiFetch.mockResolvedValue(malformedResponse);

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
      const malformedResponse = "invalid json" as unknown as SearchResponse;

      mockApiFetch.mockResolvedValue(malformedResponse);

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
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(1);
      });

      // Second request (pagination) returns malformed data
      const malformedResponse = {
        invalid: "data",
      } as unknown as SearchResponse;
      mockApiFetch.mockResolvedValueOnce(malformedResponse);

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
        } as unknown as SearchResponse["pagination"],
      };

      mockApiFetch.mockResolvedValue(responseWithoutHasMore);

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

      mockApiFetch
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
            availability_status: "available",
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

      mockApiFetch.mockResolvedValueOnce(page1Response);

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

    it("should correctly determine hasNextPage when more results available", async () => {
      const paginatedResponse = createMockSearchResponse({
        pagination: {
          total: 50,
          limit: 20,
          offset: 0,
          has_more: true,
        },
      });

      mockApiFetch.mockResolvedValueOnce(paginatedResponse);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
    });

    it("should correctly determine hasNextPage as false when no more results", async () => {
      const paginatedResponse = createMockSearchResponse({
        pagination: {
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(paginatedResponse);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
    });

    it("should flatten multiple pages into single segments array", async () => {
      const page1Response = createMockSearchResponse({
        data: [
          {
            segment_id: 1,
            video_id: "abc123def45",
            video_title: "Video 1",
            channel_title: "Channel 1",
            language_code: "en",
            text: "First segment",
            start_time: 10.0,
            end_time: 15.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-01-15T12:00:00Z",
            availability_status: "available",
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      });

      const page2Response = createMockSearchResponse({
        data: [
          {
            segment_id: 2,
            video_id: "xyz789abc12",
            video_title: "Video 2",
            channel_title: "Channel 2",
            language_code: "en",
            text: "Second segment",
            start_time: 20.0,
            end_time: 25.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-02-20T14:00:00Z",
            availability_status: "available",
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      });

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.segments).toHaveLength(1);
      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.segments).toHaveLength(2);
      });

      expect(result.current.segments[0]?.video_title).toBe("Video 1");
      expect(result.current.segments[1]?.video_title).toBe("Video 2");
      expect(result.current.hasNextPage).toBe(false);
    });

    it("should correctly calculate next page offset", async () => {
      const page1Response = createMockSearchResponse({
        pagination: {
          total: 60,
          limit: 20,
          offset: 0,
          has_more: true,
        },
      });

      const page2Response = createMockSearchResponse({
        pagination: {
          total: 60,
          limit: 20,
          offset: 20,
          has_more: true,
        },
      });

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });

      // Second call should have offset=20
      expect(mockApiFetch).toHaveBeenNthCalledWith(
        2,
        expect.stringContaining("offset=20"),
        expect.any(Object)
      );
    });

    it("should track isFetchingNextPage state", async () => {
      const page1Response = createMockSearchResponse({
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      });

      const page2Response = createMockSearchResponse({
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      });

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isFetchingNextPage).toBe(false);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.segments).toHaveLength(2);
    });
  });

  describe("Loading State", () => {
    it("should handle loading state correctly", () => {
      // Create a promise that never resolves to keep loading state
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.segments).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it("should set isLoading to false after successful fetch", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(false);
    });
  });

  describe("Error handling", () => {
    it("should handle network errors", async () => {
      const networkError = new Error("Network error");
      mockApiFetch.mockRejectedValue(networkError);

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

    it("should handle error state correctly", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error occurred",
        status: undefined,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.segments).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
    });

    it("should handle server error correctly", async () => {
      const mockError = {
        type: "server" as const,
        message: "Internal server error",
        status: 500,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
    });
  });

  describe("Query Parameters", () => {
    it("should include query parameter in API call", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "hello world" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // URL encoding will convert space to +
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("q=hello"),
        expect.any(Object)
      );
    });

    it("should include limit parameter in API call", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("limit=20"),
        expect.any(Object)
      );
    });

    it("should include offset parameter in API call", async () => {
      mockApiFetch.mockResolvedValueOnce(createMockSearchResponse());

      renderHook(() => useSearchSegments({ query: "test" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("offset=0"),
        expect.any(Object)
      );
    });
  });
});
