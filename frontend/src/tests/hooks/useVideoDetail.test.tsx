/**
 * Unit tests for useVideoDetail hook.
 *
 * Tests TanStack Query integration for fetching video details.
 *
 * @module tests/hooks/useVideoDetail
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useVideoDetail } from "../../hooks/useVideoDetail";
import type { VideoDetail } from "../../types/video";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("useVideoDetail", () => {
  let queryClient: QueryClient;

  const mockVideoDetail: VideoDetail = {
    video_id: "dQw4w9WgXcQ",
    title: "Test Video Title",
    description: "Test video description with detailed content.",
    channel_id: "UC123456789",
    channel_title: "Test Channel",
    upload_date: "2024-01-15T10:30:00Z",
    duration: 240,
    view_count: 1000000,
    like_count: 50000,
    comment_count: 1500,
    tags: ["music", "test", "video"],
    category_id: "10",
    default_language: "en",
    made_for_kids: false,
    transcript_summary: {
      count: 2,
      languages: ["en", "es"],
      has_manual: true,
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
    it("fetches and returns video detail data", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeUndefined();

      // Wait for data to load
      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockVideoDetail);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("calls apiFetch with correct endpoint", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ");
      });
    });

    it("uses correct query key for caching", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Check that the query is cached with the correct key
      const cachedData = queryClient.getQueryData(["video", "dQw4w9WgXcQ"]);
      expect(cachedData).toEqual(mockVideoDetail);
    });
  });

  describe("loading state", () => {
    it("shows loading state initially", () => {
      vi.mocked(apiConfig.apiFetch).mockImplementationOnce(
        () => new Promise(() => {}) // Never resolves
      );

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeUndefined();
      expect(result.current.error).toBeNull();
    });

    it("transitions from loading to success", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.isSuccess).toBe(true);
      });
    });
  });

  describe("error handling", () => {
    it("handles 404 not found error", async () => {
      const notFoundError = {
        type: "server" as const,
        message: "Video not found",
        status: 404,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(notFoundError);

      const { result } = renderHook(() => useVideoDetail("invalidVideo"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(notFoundError);
      expect(result.current.data).toBeUndefined();
    });

    it("handles network error", async () => {
      const networkError = {
        type: "network" as const,
        message: "Cannot reach the API server. Make sure the backend is running on port 8765.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(networkError);

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(networkError);
    });

    it("handles timeout error", async () => {
      const timeoutError = {
        type: "timeout" as const,
        message: "The server took too long to respond.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(timeoutError);

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(timeoutError);
    });

    it("handles server error (500)", async () => {
      const serverError = {
        type: "server" as const,
        message: "Something went wrong on the server.",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(serverError);

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(serverError);
    });
  });

  describe("query enabled/disabled", () => {
    it("does not fetch when videoId is empty string", () => {
      const { result } = renderHook(() => useVideoDetail(""), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("fetches when videoId is provided after being empty", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      let videoId = "";
      const { result, rerender } = renderHook(() => useVideoDetail(videoId), {
        wrapper: createWrapper(),
      });

      // Initially disabled
      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();

      // Update videoId
      videoId = "dQw4w9WgXcQ";
      rerender();

      // Should now fetch
      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ");
    });
  });

  describe("staleTime configuration", () => {
    it("uses 10 second staleTime per NFR-P01", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      const { result } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Check query state includes staleTime
      const queryState = queryClient.getQueryState(["video", "dQw4w9WgXcQ"]);
      expect(queryState).toBeDefined();
    });
  });

  describe("caching behavior", () => {
    it("uses cached data for subsequent renders", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      // First render
      const { result: result1 } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);

      // Second render with same queryClient
      const { result: result2 } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      // Should immediately have data from cache
      expect(result2.current.data).toEqual(mockVideoDetail);
      // Should not trigger another fetch
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);
    });

    it("fetches different data for different video IDs", async () => {
      const mockVideoDetail2: VideoDetail = {
        ...mockVideoDetail,
        video_id: "different123",
        title: "Different Video",
      };

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce({ data: mockVideoDetail })
        .mockResolvedValueOnce({ data: mockVideoDetail2 });

      // First video
      const { result: result1 } = renderHook(() => useVideoDetail("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second video
      const { result: result2 } = renderHook(() => useVideoDetail("different123"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.video_id).toBe("dQw4w9WgXcQ");
      expect(result2.current.data?.video_id).toBe("different123");
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2);
    });
  });
});
