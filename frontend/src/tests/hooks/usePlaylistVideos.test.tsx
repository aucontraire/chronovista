/**
 * Unit tests for usePlaylistVideos hook.
 *
 * Tests TanStack Query integration for fetching playlist videos with infinite scroll.
 * Includes tests for the include_unavailable parameter.
 *
 * @module tests/hooks/usePlaylistVideos
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { usePlaylistVideos } from "../../hooks/usePlaylistVideos";
import type { PlaylistVideoListResponse } from "../../types/playlist";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("usePlaylistVideos", () => {
  let queryClient: QueryClient;

  const mockPlaylistId = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf";

  const mockPlaylistVideoResponse: PlaylistVideoListResponse = {
    data: [
      {
        video_id: "dQw4w9WgXcQ",
        title: "Test Video 1",
        channel_id: "UC1234567890123456789012",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        duration: 240,
        view_count: 1000,
        transcript_summary: {
          count: 1,
          languages: ["en"],
          has_manual: false,
        },
        position: 0,
        availability_status: "available",
      },
      {
        video_id: "unavail123",
        title: "Recovered Video Title",
        channel_id: "UC1234567890123456789012",
        channel_title: "Recovered Channel Name",
        upload_date: "2024-01-10T10:30:00Z",
        duration: 180,
        view_count: null,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
        },
        position: 1,
        availability_status: "deleted",
      },
      {
        video_id: "private456",
        title: "Private Video Title",
        channel_id: null,
        channel_title: null,
        upload_date: "2024-01-05T10:30:00Z",
        duration: 300,
        view_count: null,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
        },
        position: 2,
        availability_status: "private",
      },
    ],
    pagination: {
      total: 3,
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
    it("fetches and returns playlist videos", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.videos).toEqual([]);

      // Wait for data to load
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(3);
      expect(result.current.videos[0]?.video_id).toBe("dQw4w9WgXcQ");
      expect(result.current.videos[1]?.video_id).toBe("unavail123");
      expect(result.current.videos[2]?.video_id).toBe("private456");
      expect(result.current.total).toBe(3);
      expect(result.current.isError).toBe(false);
    });

    it("includes unavailable videos by default", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=true
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/playlists/${mockPlaylistId}/videos?offset=0&limit=25&include_unavailable=true`
      );

      // Verify all videos (including unavailable) are included
      expect(result.current.videos).toHaveLength(3);

      const deletedVideo = result.current.videos.find(
        (v) => v.availability_status === "deleted"
      );
      expect(deletedVideo).toBeDefined();
      expect(deletedVideo?.video_id).toBe("unavail123");
      expect(deletedVideo?.title).toBe("Recovered Video Title");
      expect(deletedVideo?.channel_title).toBe("Recovered Channel Name");

      const privateVideo = result.current.videos.find(
        (v) => v.availability_status === "private"
      );
      expect(privateVideo).toBeDefined();
      expect(privateVideo?.video_id).toBe("private456");
      expect(privateVideo?.title).toBe("Private Video Title");
    });

    it("excludes unavailable videos when includeUnavailable is false", async () => {
      const availableOnlyResponse: PlaylistVideoListResponse = {
        data: [mockPlaylistVideoResponse.data[0]!],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(availableOnlyResponse);

      const { result } = renderHook(
        () => usePlaylistVideos(mockPlaylistId, { includeUnavailable: false }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with include_unavailable=false
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/playlists/${mockPlaylistId}/videos?offset=0&limit=25&include_unavailable=false`
      );

      // Verify only available videos are included
      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0]?.availability_status).toBe("available");
    });

    it("respects custom limit parameter", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(
        () => usePlaylistVideos(mockPlaylistId, { limit: 50 }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify API was called with custom limit
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/playlists/${mockPlaylistId}/videos?offset=0&limit=50&include_unavailable=true`
      );
    });

    it("preserves video position order", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Verify videos are in position order
      expect(result.current.videos[0]?.position).toBe(0);
      expect(result.current.videos[1]?.position).toBe(1);
      expect(result.current.videos[2]?.position).toBe(2);
    });
  });

  describe("error handling", () => {
    it("handles API errors correctly", async () => {
      const mockError = {
        type: "server",
        message: "Failed to fetch playlist videos",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.videos).toEqual([]);
    });

    it("handles 404 playlist not found", async () => {
      const mockError = {
        type: "server",
        message: "Playlist not found",
        status: 404,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => usePlaylistVideos("invalid-id"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
    });
  });

  describe("pagination", () => {
    it("indicates when more pages are available", async () => {
      const responseWithMore: PlaylistVideoListResponse = {
        ...mockPlaylistVideoResponse,
        pagination: {
          total: 100,
          limit: 25,
          offset: 0,
          has_more: true,
        },
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(responseWithMore);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.total).toBe(100);
    });

    it("indicates when all pages are loaded", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.total).toBe(3);
      expect(result.current.loadedCount).toBe(3);
    });
  });

  describe("enabled option", () => {
    it("does not fetch when enabled is false", async () => {
      const { result } = renderHook(
        () => usePlaylistVideos(mockPlaylistId, { enabled: false }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });
  });

  describe("unavailable video metadata", () => {
    it("returns recovered metadata for deleted videos", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const deletedVideo = result.current.videos.find(
        (v) => v.availability_status === "deleted"
      );

      // Verify recovered metadata is present
      expect(deletedVideo?.title).toBe("Recovered Video Title");
      expect(deletedVideo?.channel_title).toBe("Recovered Channel Name");
      expect(deletedVideo?.channel_id).toBe("UC1234567890123456789012");
    });

    it("handles null channel metadata for private videos", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockPlaylistVideoResponse);

      const { result } = renderHook(() => usePlaylistVideos(mockPlaylistId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const privateVideo = result.current.videos.find(
        (v) => v.availability_status === "private"
      );

      // Verify null channel fields are preserved
      expect(privateVideo?.channel_id).toBeNull();
      expect(privateVideo?.channel_title).toBeNull();
      expect(privateVideo?.title).toBe("Private Video Title");
    });
  });
});
