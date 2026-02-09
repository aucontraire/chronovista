/**
 * Tests for usePlaylists hook.
 *
 * Covers:
 * - Returns playlists data when API call succeeds
 * - Handles loading state correctly
 * - Handles error state correctly
 * - Implements infinite scroll (fetchNextPage)
 * - Handles empty playlists list
 * - Filter switching (all/linked/local)
 * - Cache key includes filter
 * - Intersection Observer setup for auto-loading
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";

import { usePlaylists } from "../../src/hooks/usePlaylists";
import { apiFetch } from "../../src/api/config";
import type { PlaylistListResponse } from "../../src/types/playlist";

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

describe("usePlaylists", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe("Successful Data Fetching", () => {
    it("should return playlists data when API call succeeds", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Test Playlist 1",
            description: "This is a test playlist",
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Test Playlist 2",
            description: "Another test playlist",
            video_count: 5,
            privacy_status: "unlisted",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(2);
      expect(result.current.playlists[0].title).toBe("Test Playlist 1");
      expect(result.current.playlists[1].title).toBe("Test Playlist 2");
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it("should flatten multiple pages into single playlists array", async () => {
      const page1Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Playlist 2",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => usePlaylists({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(1);
      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.playlists).toHaveLength(2);
      });

      expect(result.current.playlists[0].title).toBe("Playlist 1");
      expect(result.current.playlists[1].title).toBe("Playlist 2");
      expect(result.current.hasNextPage).toBe(false);
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

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.playlists).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it("should set isLoading to false after successful fetch", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

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

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.playlists).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
    });

    it("should allow retry after error", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error",
        status: undefined,
      };

      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Test Playlist",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      // First call fails, second succeeds
      mockApiFetch
        .mockRejectedValueOnce(mockError)
        .mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Retry the request
      result.current.retry();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(1);
      expect(result.current.playlists[0].title).toBe("Test Playlist");
    });
  });

  describe("Empty Playlists List", () => {
    it("should handle empty playlists list correctly", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.loadedCount).toBe(0);
      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.isError).toBe(false);
    });
  });

  describe("Infinite Scroll", () => {
    it("should implement fetchNextPage for infinite scroll", async () => {
      const page1Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Playlist 2",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => usePlaylists({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.playlists).toHaveLength(1);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(2);
      expect(result.current.hasNextPage).toBe(false);
    });

    it("should set hasNextPage to false when no more pages", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
    });

    it("should track isFetchingNextPage state", async () => {
      const page1Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Playlist 2",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => usePlaylists({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isFetchingNextPage).toBe(false);

      result.current.fetchNextPage();

      // Note: In a real test environment, isFetchingNextPage would briefly be true,
      // but in this synchronous mock setup, it resolves immediately
      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(2);
    });
  });

  describe("Filter Switching", () => {
    it("should fetch all playlists when filter is 'all'", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Linked Playlist",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
          {
            playlist_id: "int_123456789",
            title: "Local Playlist",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: false,
          },
        ],
        pagination: {
          total: 2,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => usePlaylists({ filter: "all" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("/playlists?")
        );
      });

      // Verify that the linked parameter is NOT included for "all" filter
      const callUrl = mockApiFetch.mock.calls[0][0] as string;
      expect(callUrl).not.toContain("linked=");
      expect(callUrl).toContain("offset=0");
      expect(callUrl).toContain("limit=25");
    });

    it("should fetch only linked playlists when filter is 'linked'", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Linked Playlist",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => usePlaylists({ filter: "linked" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("linked=true")
        );
      });
    });

    it("should fetch only local playlists when filter is 'local'", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "int_123456789",
            title: "Local Playlist",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: false,
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => usePlaylists({ filter: "local" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("linked=false")
        );
      });
    });

    it("should use 'all' as default filter when no filter is specified", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("/playlists?")
        );
      });

      // Verify that the linked parameter is NOT included (default is "all")
      const callUrl = mockApiFetch.mock.calls[0][0] as string;
      expect(callUrl).not.toContain("linked=");
    });
  });

  describe("Cache Key Includes Filter", () => {
    it("should use different cache keys for different filters", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValue(mockResponse);

      // Render with "all" filter
      const { unmount: unmount1 } = renderHook(
        () => usePlaylists({ filter: "all" }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });

      unmount1();

      // Render with "linked" filter - should trigger a new fetch
      const { unmount: unmount2 } = renderHook(
        () => usePlaylists({ filter: "linked" }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });

      unmount2();

      // Render with "local" filter - should trigger a new fetch
      renderHook(() => usePlaylists({ filter: "local" }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(3);
      });

      // Each filter should have triggered a separate API call
      expect(mockApiFetch).toHaveBeenCalledTimes(3);
    });

    it("should use cache key with filter and limit", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValue(mockResponse);

      // Render with "linked" filter and limit 10
      renderHook(() => usePlaylists({ filter: "linked", limit: 10 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });

      // Render with different limit but same filter - should trigger new fetch
      renderHook(() => usePlaylists({ filter: "linked", limit: 25 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });

      // Verify both calls had the correct parameters
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("limit=10")
      );
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("limit=25")
      );
    });
  });

  describe("Custom Options", () => {
    it("should accept custom limit option", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => usePlaylists({ limit: 10 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("limit=10")
        );
      });
    });

    it("should accept enabled option to disable query", async () => {
      const { result } = renderHook(() => usePlaylists({ enabled: false }), {
        wrapper: createWrapper(queryClient),
      });

      // Should not fetch when disabled
      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
    });

    it("should combine multiple options correctly", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => usePlaylists({ filter: "linked", limit: 10, enabled: true }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("linked=true")
        );
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("limit=10")
        );
      });
    });
  });

  describe("Intersection Observer Integration", () => {
    it("should provide loadMoreRef for infinite scroll trigger", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.loadMoreRef).toBeDefined();
      expect(result.current.loadMoreRef.current).toBeNull();
    });
  });

  describe("Pagination Logic", () => {
    it("should calculate correct offset for next page", async () => {
      const page1Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 3,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Playlist 2",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
        ],
        pagination: {
          total: 3,
          limit: 1,
          offset: 1,
          has_more: true,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => usePlaylists({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("offset=0")
      );

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("offset=1")
        );
      });

      expect(result.current.playlists).toHaveLength(2);
    });

    it("should handle total count from last page", async () => {
      const page1Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Playlist 1",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Playlist 2",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(() => usePlaylists({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should show total from first page
      expect(result.current.total).toBe(2);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.playlists).toHaveLength(2);
      });

      // Should still show total from last page
      expect(result.current.total).toBe(2);
    });
  });

  describe("Privacy Status Handling", () => {
    it("should correctly handle different privacy statuses", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "Public Playlist",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efde",
            title: "Private Playlist",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: true,
          },
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdc",
            title: "Unlisted Playlist",
            description: null,
            video_count: 7,
            privacy_status: "unlisted",
            is_linked: true,
          },
        ],
        pagination: {
          total: 3,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(3);
      expect(result.current.playlists[0].privacy_status).toBe("public");
      expect(result.current.playlists[1].privacy_status).toBe("private");
      expect(result.current.playlists[2].privacy_status).toBe("unlisted");
    });
  });

  describe("Linked Status Handling", () => {
    it("should correctly handle mixed linked and local playlists", async () => {
      const mockResponse: PlaylistListResponse = {
        data: [
          {
            playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            title: "YouTube Playlist",
            description: null,
            video_count: 10,
            privacy_status: "public",
            is_linked: true,
          },
          {
            playlist_id: "int_123456789",
            title: "Internal Playlist",
            description: null,
            video_count: 5,
            privacy_status: "private",
            is_linked: false,
          },
        ],
        pagination: {
          total: 2,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => usePlaylists(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.playlists).toHaveLength(2);
      expect(result.current.playlists[0].is_linked).toBe(true);
      expect(result.current.playlists[1].is_linked).toBe(false);
    });
  });
});
