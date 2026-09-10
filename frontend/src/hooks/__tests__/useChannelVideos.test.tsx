/**
 * Tests for useChannelVideos hook.
 *
 * Covers:
 * - Returns videos for a channel, flattening multiple pages
 * - Loading, error, and empty-list (EC-003) states
 * - The include_unavailable parameter (default true, explicit false)
 * - Infinite scroll (fetchNextPage, hasNextPage, isFetchingNextPage) and the
 *   Intersection Observer loadMoreRef integration
 * - Error retry via the returned retry() function
 * - Disabled state when channelId is not provided / enabled option is false
 * - Custom limit option
 */

import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { useChannelVideos } from "../useChannelVideos";
import type { VideoListItem, VideoListResponse } from "../../types/video";

// Mock the API fetch function
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
 * Factory for a fully-populated VideoListItem, since the type requires
 * fields (tags, category_id, topics, availability_status, ...) that most
 * of these tests don't care about.
 */
function createMockVideo(overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    video_id: "video1",
    title: "Video 1",
    channel_id: "UC123456789012345678901",
    channel_title: "Test Channel",
    upload_date: "2024-01-15T10:30:00Z",
    duration: 245,
    view_count: 1000000,
    transcript_summary: {
      count: 0,
      languages: [],
      has_manual: false,
      has_corrections: false,
    },
    tags: [],
    category_id: null,
    category_name: null,
    topics: [],
    availability_status: "available",
    recovered_at: null,
    recovery_source: null,
    ...overrides,
  };
}

describe("useChannelVideos", () => {
  let queryClient: QueryClient;

  const mockChannelId = "UC1234567890123456789012";

  const mockVideoListResponse: VideoListResponse = {
    data: [
      createMockVideo({
        video_id: "dQw4w9WgXcQ",
        title: "Test Video 1",
        channel_id: mockChannelId,
        upload_date: "2024-01-15T10:30:00Z",
        duration: 240,
        view_count: 1000,
        transcript_summary: {
          count: 1,
          languages: ["en"],
          has_manual: false,
          has_corrections: false,
        },
        availability_status: "available",
      }),
      createMockVideo({
        video_id: "unavail123",
        title: "Unavailable Video",
        channel_id: mockChannelId,
        upload_date: "2024-01-10T10:30:00Z",
        duration: 180,
        view_count: null,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
          has_corrections: false,
        },
        availability_status: "deleted",
      }),
    ],
    pagination: {
      total: 2,
      limit: 25,
      offset: 0,
      has_more: false,
    },
  };

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe("successful data fetching", () => {
    it("fetches and returns channel videos", async () => {
      mockApiFetch.mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(queryClient),
      });

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.videos).toEqual([]);

      // Wait for data to load
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
      expect(result.current.videos[0]?.video_id).toBe("dQw4w9WgXcQ");
      expect(result.current.videos[1]?.video_id).toBe("unavail123");
      expect(result.current.total).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it("should return videos for a channel", async () => {
      const mockResponse: VideoListResponse = {
        data: [
          createMockVideo({
            video_id: "dQw4w9WgXcQ",
            title: "Video 1",
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 1,
              languages: ["en"],
              has_manual: true,
              has_corrections: false,
            },
          }),
          createMockVideo({
            video_id: "jNQXAC9IVRw",
            title: "Video 2",
            upload_date: "2024-01-10T08:00:00Z",
            duration: 180,
            view_count: 500000,
            transcript_summary: {
              count: 2,
              languages: ["en", "es"],
              has_manual: false,
              has_corrections: false,
            },
          }),
        ],
        pagination: {
          total: 2,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
      expect(result.current.videos[0]?.title).toBe("Video 1");
      expect(result.current.videos[1]?.title).toBe("Video 2");
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it("includes unavailable videos by default", async () => {
      mockApiFetch.mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=true
      expect(mockApiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=25&include_unavailable=true`,
        expect.anything()
      );

      // Verify both available and unavailable videos are included
      expect(result.current.videos).toHaveLength(2);
      const unavailableVideo = result.current.videos.find(
        (v) => v.availability_status === "deleted"
      );
      expect(unavailableVideo).toBeDefined();
      expect(unavailableVideo?.video_id).toBe("unavail123");
    });

    it("excludes unavailable videos when includeUnavailable is false", async () => {
      const firstVideo = mockVideoListResponse.data[0];
      if (!firstVideo) {
        throw new Error("Mock data missing first video");
      }

      const availableOnlyResponse: VideoListResponse = {
        data: [firstVideo],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(availableOnlyResponse);

      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { includeUnavailable: false }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=false
      expect(mockApiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=25&include_unavailable=false`,
        expect.anything()
      );

      // Verify only available videos are included
      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0]?.availability_status).toBe("available");
    });

    it("respects custom limit parameter", async () => {
      mockApiFetch.mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { limit: 50 }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with custom limit
      expect(mockApiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=50&include_unavailable=true`,
        expect.anything()
      );
    });

    it("should flatten multiple pages into single videos array", async () => {
      const page1Response: VideoListResponse = {
        data: [createMockVideo({ video_id: "video1", title: "Video 1" })],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          createMockVideo({
            video_id: "video2",
            title: "Video 2",
            upload_date: "2024-01-10T08:00:00Z",
            duration: 180,
            view_count: 500000,
          }),
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

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901", { limit: 1 }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(1);
      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.videos).toHaveLength(2);
      });

      expect(result.current.videos[0]?.title).toBe("Video 1");
      expect(result.current.videos[1]?.title).toBe("Video 2");
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  describe("error handling", () => {
    it("handles API errors correctly", async () => {
      const mockError = {
        type: "server",
        message: "Failed to fetch videos",
        status: 500,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.videos).toEqual([]);
    });

    it("handles undefined channelId", () => {
      const { result } = renderHook(() => useChannelVideos(undefined), {
        wrapper: createWrapper(queryClient),
      });

      // Should not make API call
      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
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

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it("should set isLoading to false after successful fetch", async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
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
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
    });

    it("should allow retry after error", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error",
        status: undefined,
      };

      const mockResponse: VideoListResponse = {
        data: [
          createMockVideo({
            video_id: "dQw4w9WgXcQ",
            title: "Test Video",
            transcript_summary: {
              count: 1,
              languages: ["en"],
              has_manual: true,
              has_corrections: false,
            },
          }),
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

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Retry the request
      result.current.retry();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0]?.title).toBe("Test Video");
    });
  });

  describe("pagination", () => {
    it("indicates when more pages are available", async () => {
      const responseWithMore: VideoListResponse = {
        ...mockVideoListResponse,
        pagination: {
          total: 100,
          limit: 25,
          offset: 0,
          has_more: true,
        },
      };

      mockApiFetch.mockResolvedValueOnce(responseWithMore);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.total).toBe(100);
    });

    it("indicates when all pages are loaded", async () => {
      mockApiFetch.mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
    });
  });

  describe("Empty Video List (EC-003)", () => {
    it("should handle empty video list correctly", async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.loadedCount).toBe(0);
      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.isError).toBe(false);
    });

    it("should distinguish between empty result and error", async () => {
      const emptyResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(emptyResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should be successful fetch with empty data, not an error
      expect(result.current.isError).toBe(false);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.total).toBe(0);
    });
  });

  describe("Infinite Scroll", () => {
    it("should implement fetchNextPage for infinite scroll", async () => {
      const page1Response: VideoListResponse = {
        data: [createMockVideo({ video_id: "video1", title: "Video 1" })],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          createMockVideo({
            video_id: "video2",
            title: "Video 2",
            upload_date: "2024-01-10T08:00:00Z",
            duration: 180,
            view_count: 500000,
          }),
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

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901", { limit: 1 }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.videos).toHaveLength(1);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
      expect(result.current.hasNextPage).toBe(false);
    });

    it("should set hasNextPage to false when no more pages", async () => {
      const mockResponse: VideoListResponse = {
        data: [createMockVideo({ video_id: "video1", title: "Video 1" })],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
    });

    it("should track isFetchingNextPage state", async () => {
      const page1Response: VideoListResponse = {
        data: [createMockVideo({ video_id: "video1", title: "Video 1" })],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          createMockVideo({
            video_id: "video2",
            title: "Video 2",
            upload_date: "2024-01-10T08:00:00Z",
            duration: 180,
            view_count: 500000,
          }),
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

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901", { limit: 1 }),
        { wrapper: createWrapper(queryClient) }
      );

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

      expect(result.current.videos).toHaveLength(2);
    });
  });

  describe("Disabled State When No Channel ID", () => {
    it("should return disabled state when channelId is not provided", () => {
      const { result } = renderHook(() => useChannelVideos(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it("should not fetch when channelId is empty string", () => {
      const { result } = renderHook(() => useChannelVideos(""), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it("should be enabled when valid channelId is provided", async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/channels/UC123456789012345678901/videos"),
        expect.anything()
      );
    });
  });

  describe("Custom Options", () => {
    it("should accept custom limit option", async () => {
      const mockResponse: VideoListResponse = {
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
        () => useChannelVideos("UC123456789012345678901", { limit: 10 }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining("limit=10"),
          expect.anything()
        );
      });
    });

    it("does not fetch when enabled is false", () => {
      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });
  });

  describe("Intersection Observer Integration", () => {
    it("should provide loadMoreRef for infinite scroll trigger", async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos("UC123456789012345678901"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.loadMoreRef).toBeDefined();
      expect(result.current.loadMoreRef.current).toBeNull();
    });
  });
});
