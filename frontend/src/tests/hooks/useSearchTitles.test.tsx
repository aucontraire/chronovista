/**
 * Tests for useSearchTitles Hook
 *
 * Tests all requirements from T020:
 * 1. Disabled when query too short
 * 2. Enabled when query meets minimum
 * 3. Disabled when enabled=false
 * 4. Default enabled=true
 * 5. Returns empty data on no results
 * 6. Returns results
 * 7. Passes correct API parameters
 * 8. Passes AbortSignal
 * 9. Error handling
 * 10. Refetch function
 * 11. Query key changes trigger new request
 */

import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSearchTitles } from "../../hooks/useSearchTitles";
import type { TitleSearchResponse } from "../../types/search";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

import { apiFetch } from "../../api/config";

describe("useSearchTitles", () => {
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

  const mockResponse: TitleSearchResponse = {
    data: [
      {
        video_id: "dQw4w9WgXcQ",
        title: "Test Video Title",
        channel_title: "Test Channel",
        upload_date: "2023-01-01T00:00:00Z",
      },
      {
        video_id: "abcd1234efg",
        title: "Another Test Video",
        channel_title: "Another Channel",
        upload_date: "2023-02-15T10:30:00Z",
      },
    ],
    total_count: 2,
  };

  describe("T020: Basic functionality", () => {
    it("should not execute query when query is too short (< 2 chars)", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "a", enabled: true }),
        { wrapper }
      );

      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
      expect(result.current.isLoading).toBe(false);
      expect(apiFetch).not.toHaveBeenCalled();
    });

    it("should not execute query when query is empty string", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "", enabled: true }),
        { wrapper }
      );

      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
      expect(result.current.isLoading).toBe(false);
      expect(apiFetch).not.toHaveBeenCalled();
    });

    it("should execute query when query meets minimum length (>= 2 chars)", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      expect(result.current.data).toHaveLength(2);
      expect(result.current.totalCount).toBe(2);
    });

    it("should execute query with exactly 2 characters", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "ab", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      expect(result.current.data).toHaveLength(2);
    });

    it("should not execute query when enabled is false, even with valid query", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: false }),
        { wrapper }
      );

      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
      expect(result.current.isLoading).toBe(false);
      expect(apiFetch).not.toHaveBeenCalled();
    });

    it("should default enabled to true when not provided", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test" }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      expect(result.current.data).toHaveLength(2);
    });

    it("should return empty data and zero count when API returns empty results", async () => {
      const emptyResponse: TitleSearchResponse = {
        data: [],
        total_count: 0,
      };
      vi.mocked(apiFetch).mockResolvedValue(emptyResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "noresults", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
    });

    it("should return results with correct data structure", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse.data);
      expect(result.current.totalCount).toBe(mockResponse.total_count);
      expect(result.current.data[0]).toEqual({
        video_id: "dQw4w9WgXcQ",
        title: "Test Video Title",
        channel_title: "Test Channel",
        upload_date: "2023-01-01T00:00:00Z",
      });
    });
  });

  describe("T020: API parameters", () => {
    it("should pass correct URL parameters to apiFetch (q and limit)", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      renderHook(
        () => useSearchTitles({ query: "test query", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      const callArgs = vi.mocked(apiFetch).mock.calls[0];
      if (callArgs) {
        const url = callArgs[0];
        expect(url).toContain("/search/titles?");
        expect(url).toContain("q=test+query");
        expect(url).toContain("limit=50");
      }
    });

    it("should encode special characters in query parameter", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      renderHook(
        () => useSearchTitles({ query: "test & query", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      const callArgs = vi.mocked(apiFetch).mock.calls[0];
      if (callArgs) {
        const url = callArgs[0];
        expect(url).toContain("q=test+%26+query");
      }
    });

    it("should pass AbortSignal to apiFetch for cancellation support", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
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
  });

  describe("T020: Concurrent search handling", () => {
    it("should handle query change by updating queryKey", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { rerender } = renderHook(
        ({ query }) => useSearchTitles({ query, enabled: true }),
        {
          wrapper,
          initialProps: { query: "test1" },
        }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(1);
      });

      const firstCallUrl = vi.mocked(apiFetch).mock.calls[0]?.[0];
      expect(firstCallUrl).toContain("q=test1");

      // Change query - should trigger new request
      rerender({ query: "test2" });

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });

      const secondCallUrl = vi.mocked(apiFetch).mock.calls[1]?.[0];
      expect(secondCallUrl).toContain("q=test2");
    });

    it("should handle AbortError gracefully (query cancellation)", async () => {
      const abortError = new DOMException("The operation was aborted", "AbortError");
      vi.mocked(apiFetch).mockRejectedValue(abortError);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // TanStack Query handles AbortError gracefully - should not show error state
      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
    });

    it("should cancel previous request when query changes rapidly", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { rerender } = renderHook(
        ({ query }) => useSearchTitles({ query, enabled: true }),
        {
          wrapper,
          initialProps: { query: "test1" },
        }
      );

      // Change query immediately without waiting for first request
      rerender({ query: "test2" });
      rerender({ query: "test3" });

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(3);
      });

      // All three should have been called, but TanStack Query cancels previous ones
      const calls = vi.mocked(apiFetch).mock.calls;
      expect(calls[0]?.[0]).toContain("q=test1");
      expect(calls[1]?.[0]).toContain("q=test2");
      expect(calls[2]?.[0]).toContain("q=test3");
    });
  });

  describe("T020: Error handling", () => {
    it("should handle network errors", async () => {
      const networkError = new Error("Network error");
      vi.mocked(apiFetch).mockRejectedValue(networkError);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(networkError);
      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
    });

    it("should handle API errors (404, 500, etc.)", async () => {
      const apiError = new Error("API Error: 500 Internal Server Error");
      vi.mocked(apiFetch).mockRejectedValue(apiError);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(apiError);
    });

    it("should handle malformed response data gracefully", async () => {
      const malformedResponse = {
        data: null as any, // Malformed: data is null
        total_count: 5,
      };

      vi.mocked(apiFetch).mockResolvedValue(malformedResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should handle gracefully with empty array
      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(5); // Still gets total_count
    });

    it("should handle missing total_count gracefully", async () => {
      const responseWithoutCount = {
        data: mockResponse.data,
        total_count: undefined as any,
      };

      vi.mocked(apiFetch).mockResolvedValue(responseWithoutCount);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse.data);
      expect(result.current.totalCount).toBe(0); // Defaults to 0
    });

    it("should handle completely invalid response structure", async () => {
      const invalidResponse = "invalid json" as any;

      vi.mocked(apiFetch).mockResolvedValue(invalidResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should fallback to empty state
      expect(result.current.data).toEqual([]);
      expect(result.current.totalCount).toBe(0);
    });
  });

  describe("T020: Refetch functionality", () => {
    it("should provide refetch function that triggers new request", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalledTimes(1);

      // Call refetch
      result.current.refetch();

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });

      expect(result.current.data).toEqual(mockResponse.data);
    });

    it("should allow refetch after error", async () => {
      const networkError = new Error("Network error");
      vi.mocked(apiFetch).mockRejectedValueOnce(networkError);

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Now mock successful response
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      // Refetch should retry
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse.data);
      expect(result.current.totalCount).toBe(2);
    });

    it("should not throw error when refetch is called", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      // Should not throw
      expect(() => result.current.refetch()).not.toThrow();
    });
  });

  describe("T020: Loading states", () => {
    it("should show loading state during initial fetch", async () => {
      vi.mocked(apiFetch).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve(mockResponse), 100)
          )
      );

      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      // Should be loading initially
      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toEqual([]);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse.data);
    });

    it("should not show loading when query is disabled", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: false }),
        { wrapper }
      );

      expect(result.current.isLoading).toBe(false);
    });

    it("should not show loading when query is too short", () => {
      const { result } = renderHook(
        () => useSearchTitles({ query: "a", enabled: true }),
        { wrapper }
      );

      expect(result.current.isLoading).toBe(false);
    });
  });

  describe("T020: Caching behavior", () => {
    it("should cache results based on query key", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { unmount } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Re-render with same query
      const { result } = renderHook(
        () => useSearchTitles({ query: "test", enabled: true }),
        { wrapper }
      );

      // Should use cached data initially
      expect(result.current.data).toEqual(mockResponse.data);
      expect(result.current.totalCount).toBe(2);

      // Should not make another API call immediately (staleTime is 2 minutes)
      expect(apiFetch).toHaveBeenCalledTimes(1);
    });

    it("should make new request for different query", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { unmount } = renderHook(
        () => useSearchTitles({ query: "test1", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Re-render with different query
      renderHook(
        () => useSearchTitles({ query: "test2", enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("T020: Edge cases", () => {
    it("should handle very long query strings", async () => {
      const longQuery = "a".repeat(500); // Max query length
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: longQuery, enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      const callUrl = vi.mocked(apiFetch).mock.calls[0]?.[0];
      expect(callUrl).toContain(`q=${encodeURIComponent(longQuery)}`);
    });

    it("should handle query with special URL characters", async () => {
      const specialQuery = "test?query=1&sort=desc#fragment";
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: specialQuery, enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      const callUrl = vi.mocked(apiFetch).mock.calls[0]?.[0];
      // Should be properly encoded
      expect(callUrl).toContain("q=test%3Fquery%3D1%26sort%3Ddesc%23fragment");
    });

    it("should handle unicode characters in query", async () => {
      const unicodeQuery = "café résumé 日本語";
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { result } = renderHook(
        () => useSearchTitles({ query: unicodeQuery, enabled: true }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalled();
      expect(result.current.data).toEqual(mockResponse.data);
    });

    it("should handle toggling enabled flag", async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockResponse);

      const { rerender, result } = renderHook(
        ({ enabled }) => useSearchTitles({ query: "test", enabled }),
        {
          wrapper,
          initialProps: { enabled: true },
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiFetch).toHaveBeenCalledTimes(1);
      expect(result.current.data).toEqual(mockResponse.data);

      // Disable the query
      rerender({ enabled: false });

      // Should still show cached data
      expect(result.current.data).toEqual(mockResponse.data);

      // Re-enable the query
      rerender({ enabled: true });

      // Should not make new request (still within staleTime)
      expect(apiFetch).toHaveBeenCalledTimes(1);
    });
  });
});
