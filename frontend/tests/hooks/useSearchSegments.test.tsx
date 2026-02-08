/**
 * Tests for useSearchSegments hook.
 *
 * Covers:
 * - Query is disabled when query length < 2
 * - Query is enabled when query length >= 2
 * - Pagination (getNextPageParam logic)
 * - Language filter is passed correctly
 * - Error handling
 * - Empty results handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";

import { useSearchSegments } from "../../src/hooks/useSearchSegments";
import { apiFetch } from "../../src/api/config";
import type { SearchResponse } from "../../src/types/search";

// Mock the API fetch function
vi.mock("../../src/api/config", () => ({
  apiFetch: vi.fn(),
}));

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
    logger: {
      log: () => {},
      warn: () => {},
      error: () => {},
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
      },
    ],
    pagination: {
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
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

  describe("Query Enabled State", () => {
    it("should NOT execute query when query length is less than 2", async () => {
      const { result } = renderHook(
        () => useSearchSegments({ query: "a" }),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not fetch when query is too short
      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
      expect(result.current.segments).toHaveLength(0);
    });

    it("should NOT execute query when query is empty", async () => {
      const { result } = renderHook(
        () => useSearchSegments({ query: "" }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
      expect(result.current.segments).toHaveLength(0);
    });

    it("should execute query when query length is exactly 2", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "ab" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(1);
      expect(result.current.segments).toHaveLength(1);
    });

    it("should execute query when query length is greater than 2", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

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
  });

  describe("Successful Data Fetching", () => {
    it("should return segments data when API call succeeds", async () => {
      const mockResponse = createMockSearchResponse({
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
          },
        ],
        pagination: {
          total: 2,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "matching" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.segments).toHaveLength(2);
      expect(result.current.segments[0].video_title).toBe("Video One");
      expect(result.current.segments[1].video_title).toBe("Video Two");
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it("should handle empty results correctly", async () => {
      const mockResponse = createMockSearchResponse({
        data: [],
        pagination: {
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(mockResponse);

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
    it("should pass language filter to API when provided", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test", language: "es" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("language=es"),
        expect.any(Object)
      );
    });

    it("should NOT include language parameter when language is null", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test", language: null }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.not.stringContaining("language="),
        expect.any(Object)
      );
    });

    it("should NOT include language parameter when language is undefined", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.not.stringContaining("language="),
        expect.any(Object)
      );
    });

    it("should include correct query key with language", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result: result1 } = renderHook(
        () => useSearchSegments({ query: "test", language: "en" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
      });

      // Different language should trigger a new query
      const mockResponse2 = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse2);

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

  describe("Pagination", () => {
    it("should correctly determine hasNextPage when more results available", async () => {
      const mockResponse = createMockSearchResponse({
        pagination: {
          total: 50,
          limit: 20,
          offset: 0,
          has_more: true,
        },
      });

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
    });

    it("should correctly determine hasNextPage as false when no more results", async () => {
      const mockResponse = createMockSearchResponse({
        pagination: {
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

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

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

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

      expect(result.current.segments[0].video_title).toBe("Video 1");
      expect(result.current.segments[1].video_title).toBe("Video 2");
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

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

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

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

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
    it("should handle loading state correctly", async () => {
      // Create a promise that never resolves to keep loading state
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.segments).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it("should set isLoading to false after successful fetch", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(false);
    });
  });

  describe("Error State", () => {
    it("should handle error state correctly", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error occurred",
        status: undefined,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

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

      const { result } = renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
    });
  });

  describe("Query Parameters", () => {
    it("should include query parameter in API call", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "hello world" }),
        { wrapper: createWrapper(queryClient) }
      );

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
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("limit=20"),
        expect.any(Object)
      );
    });

    it("should include offset parameter in API call", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("offset=0"),
        expect.any(Object)
      );
    });

    it("should pass signal for abort controller", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useSearchSegments({ query: "test" }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          signal: expect.any(AbortSignal),
        })
      );
    });
  });
});
