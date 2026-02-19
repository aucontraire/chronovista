/**
 * Unit tests for useChannelVideos hook.
 *
 * Tests TanStack Query integration for fetching channel videos with infinite scroll.
 * Includes tests for the include_unavailable parameter.
 *
 * @module tests/hooks/useChannelVideos
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useChannelVideos } from "../../hooks/useChannelVideos";
import type { VideoListResponse } from "../../types/video";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("useChannelVideos", () => {
  let queryClient: QueryClient;

  const mockChannelId = "UC1234567890123456789012";

  const mockVideoListResponse: VideoListResponse = {
    data: [
      {
        video_id: "dQw4w9WgXcQ",
        title: "Test Video 1",
        channel_id: mockChannelId,
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        duration: 240,
        view_count: 1000,
        transcript_summary: {
          count: 1,
          languages: ["en"],
          has_manual: false,
        },
        tags: [],
        category_id: "10",
        category_name: "Music",
        topics: [],
        availability_status: "available",
        recovered_at: null,
        recovery_source: null,
      },
      {
        video_id: "unavail123",
        title: "Unavailable Video",
        channel_id: mockChannelId,
        channel_title: "Test Channel",
        upload_date: "2024-01-10T10:30:00Z",
        duration: 180,
        view_count: null,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
        },
        tags: [],
        category_id: null,
        category_name: null,
        topics: [],
        availability_status: "deleted",
        recovered_at: null,
        recovery_source: null,
      },
    ],
    pagination: {
      total: 2,
      limit: 25,
      offset: 0,
      has_more: false,
    },
  };

  beforeEach(() => {
    // Create a fresh QueryClient for each test
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false, // Disable retries for testing
        },
      },
    });

    // Clear all mocks
    vi.clearAllMocks();
  });

  const createWrapper = () => {
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  describe("successful data fetching", () => {
    it("fetches and returns channel videos", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(),
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

    it("includes unavailable videos by default", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=true
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=25&include_unavailable=true`
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
      const availableOnlyResponse: VideoListResponse = {
        data: [mockVideoListResponse.data[0]!],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(availableOnlyResponse);

      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { includeUnavailable: false }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=false
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=25&include_unavailable=false`
      );

      // Verify only available videos are included
      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0]?.availability_status).toBe("available");
    });

    it("respects custom limit parameter", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { limit: 50 }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with custom limit
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/channels/${mockChannelId}/videos?offset=0&limit=50&include_unavailable=true`
      );
    });
  });

  describe("error handling", () => {
    it("handles API errors correctly", async () => {
      const mockError = {
        type: "server",
        message: "Failed to fetch videos",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.videos).toEqual([]);
    });

    it("handles undefined channelId", async () => {
      const { result } = renderHook(() => useChannelVideos(undefined), {
        wrapper: createWrapper(),
      });

      // Should not make API call
      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
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

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(responseWithMore);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.total).toBe(100);
    });

    it("indicates when all pages are loaded", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(() => useChannelVideos(mockChannelId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
    });
  });

  describe("enabled option", () => {
    it("does not fetch when enabled is false", async () => {
      const { result } = renderHook(
        () => useChannelVideos(mockChannelId, { enabled: false }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });
  });
});
