/**
 * Unit tests for VideoDetailPage component.
 *
 * Tests browser tab title, absolute date display, and video metadata rendering.
 *
 * @module tests/pages/VideoDetailPage
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { VideoDetailPage } from "../../pages/VideoDetailPage";
import * as apiConfig from "../../api/config";
import type { VideoDetail } from "../../types/video";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("VideoDetailPage", () => {
  let queryClient: QueryClient;
  const originalTitle = document.title;

  const mockVideoDetail: VideoDetail = {
    video_id: "test123",
    title: "Amazing Test Video About Coding",
    description: "This is a comprehensive test video.",
    channel_id: "channel456",
    channel_title: "TestChannel",
    upload_date: "2024-01-15T10:30:00Z",
    duration: 3600,
    view_count: 1500000,
    like_count: 75000,
    comment_count: 2500,
    tags: ["coding", "tutorial"],
    category_id: "28",
    category_name: "Science & Technology",
    topics: [],
    default_language: "en",
    made_for_kids: false,
    transcript_summary: {
      count: 1,
      languages: ["en"],
      has_manual: true,
    },
    availability_status: "available",
    alternative_url: null,
    recovered_at: null,
    recovery_source: null,
  };

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
          staleTime: 0,
        },
      },
    });
    vi.clearAllMocks();
    document.title = "Chronovista";
  });

  afterEach(() => {
    document.title = originalTitle;
    queryClient.clear();
  });

  const renderWithProviders = (videoId: string) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/videos/${videoId}`]}>
          <Routes>
            <Route path="/videos/:videoId" element={<VideoDetailPage />} />
            <Route path="/videos" element={<div>Videos List</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("browser tab title", () => {
    it("sets document.title to 'Channel - Video Title' when video loads", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(document.title).toBe("TestChannel - Amazing Test Video About Coding");
      });
    });

    it("uses 'Unknown Channel' when channel_title is null", async () => {
      const videoWithNoChannel: VideoDetail = {
        ...mockVideoDetail,
        channel_title: null,
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: videoWithNoChannel,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(document.title).toBe("Unknown Channel - Amazing Test Video About Coding");
      });
    });

    it("resets document.title to default on unmount", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      const { unmount } = renderWithProviders("test123");

      await waitFor(() => {
        expect(document.title).toBe("TestChannel - Amazing Test Video About Coding");
      });

      unmount();

      expect(document.title).toBe("Chronovista");
    });
  });

  describe("absolute date display", () => {
    it("displays upload date in absolute format (e.g., 'Jan 15, 2024')", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("Amazing Test Video About Coding")).toBeInTheDocument();
      });

      // Should show "Jan 15, 2024" instead of relative time like "2 weeks ago"
      expect(screen.getByText("Jan 15, 2024")).toBeInTheDocument();
    });

    it("does not show relative time like 'ago'", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("Amazing Test Video About Coding")).toBeInTheDocument();
      });

      // Should NOT contain relative time indicators
      expect(screen.queryByText(/ago/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/yesterday/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/just now/i)).not.toBeInTheDocument();
    });

    it("formats different dates correctly", async () => {
      const videoFromDec: VideoDetail = {
        ...mockVideoDetail,
        upload_date: "2023-12-25T08:00:00Z",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: videoFromDec,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("Dec 25, 2023")).toBeInTheDocument();
      });
    });
  });

  describe("video metadata display", () => {
    it("displays channel name", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("TestChannel")).toBeInTheDocument();
      });
    });

    it("displays video title", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
          "Amazing Test Video About Coding"
        );
      });
    });

    it("displays formatted view count", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("1.5M views")).toBeInTheDocument();
      });
    });

    it("displays formatted like count", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("75.0K likes")).toBeInTheDocument();
      });
    });

    it("displays formatted duration", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockVideoDetail,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        // 3600 seconds = 1:00:00
        expect(screen.getByText("1:00:00")).toBeInTheDocument();
      });
    });
  });

  describe("loading state", () => {
    it("shows loading state initially", () => {
      vi.mocked(apiConfig.apiFetch).mockImplementationOnce(
        () => new Promise(() => {}) // Never resolves
      );

      renderWithProviders("test123");

      // LoadingState component should be rendered
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });
  });

  describe("error state", () => {
    it("shows error message when API fails", async () => {
      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce({
        type: "server",
        message: "Server error",
        status: 500,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByText("Could not load video.")).toBeInTheDocument();
      });
    });

    it("shows retry button in error state", async () => {
      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce({
        type: "server",
        message: "Server error",
        status: 500,
      });

      renderWithProviders("test123");

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
      });
    });
  });
});
