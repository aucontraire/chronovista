/**
 * Tests for VideoDetailPage — Feature 048 (User Story 3) layout and interaction tests.
 *
 * Covers:
 * - Two-column layout with VideoEmbed + TranscriptPanel when transcript exists (FR-011)
 * - Single-column thumbnail layout when no transcript exists (FR-008)
 * - VideoEmbed rendered only when hasTranscript is true
 * - Download button rendered (regression) when no transcript exists
 * - aria-live polite region present in the error state DOM
 * - TranscriptPanel receives correct props (videoId, deep-link params, player state)
 * - VideoEmbed receives containerRef and playerError from useYouTubePlayer (Feature 048)
 * - Loading and error guard clauses
 * - Navigation links present in loaded state
 *
 * Strategy:
 * - Mock all hooks at module level (useVideoDetail, useDeepLinkParams,
 *   useOnboardingStatus, useVideoPlaylists, useEntityMentions, useTranscriptDownload,
 *   useYouTubePlayer)
 * - Mock heavy child components (TranscriptPanel, VideoEmbed, ClassificationSection,
 *   EntityMentionsPanel, UnavailabilityBanner, LoadingState) with lightweight stubs
 *   that capture props for assertion
 * - Use MemoryRouter + QueryClientProvider for render context
 *
 * Note on useYouTubePlayer:
 * The hook is now called in VideoDetailPage (lifted from VideoEmbed) so that
 * seekTo/activeSegmentId/followPlayback/toggleFollowPlayback can be shared with
 * TranscriptPanel. The hook is mocked here so no real YouTube API is loaded.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { VideoDetailPage } from "../../pages/VideoDetailPage";
import type { VideoDetail } from "../../types/video";

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

// Mock API config so no real network calls are made
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
  RECOVERY_TIMEOUT: 120000,
}));

// Mock useVideoDetail — controls video data returned to the page
vi.mock("../../hooks/useVideoDetail", () => ({
  useVideoDetail: vi.fn(),
}));

// Mock useDeepLinkParams — provides deep-link query parameters
vi.mock("../../hooks/useDeepLinkParams", () => ({
  useDeepLinkParams: vi.fn(),
}));

// Mock useOnboardingStatus — provides auth state
vi.mock("../../hooks/useOnboarding", () => ({
  useOnboardingStatus: vi.fn(),
}));

// Mock useVideoPlaylists — not relevant to these layout tests
vi.mock("../../hooks/useVideoPlaylists", () => ({
  useVideoPlaylists: vi.fn(),
}));

// Mock useEntityMentions — not relevant to these layout tests
vi.mock("../../hooks/useEntityMentions", () => ({
  useVideoEntities: vi.fn(),
  useEntityVideos: vi.fn(),
}));

// Mock useTranscriptDownload — prevents mutation side-effects
vi.mock("../../hooks/useTranscriptDownload", () => ({
  useTranscriptDownload: vi.fn(),
}));

// Mock useYouTubePlayer — the hook is now lifted to VideoDetailPage so its
// return values (containerRef, error, seekTo, activeSegmentId, followPlayback,
// toggleFollowPlayback) are passed to VideoEmbed and TranscriptPanel.
vi.mock("../../hooks/useYouTubePlayer", () => ({
  useYouTubePlayer: vi.fn(),
}));

// Mock recoveryStore — prevents Zustand state leaking between tests
vi.mock("../../stores/recoveryStore", () => ({
  useRecoveryStore: vi.fn(),
}));

// Lightweight stub for VideoEmbed — records props; no real YouTube API loaded
vi.mock("../../components/video/VideoEmbed", () => ({
  VideoEmbed: vi.fn((props: Record<string, unknown>) => (
    <div
      data-testid="video-embed"
      data-video-id={String(props["videoId"] ?? "")}
      data-availability={String(props["availabilityStatus"] ?? "")}
    />
  )),
}));

// Lightweight stub for TranscriptPanel — records props passed by the page
vi.mock("../../components/transcript", () => ({
  TranscriptPanel: vi.fn((props: Record<string, unknown>) => (
    <div
      data-testid="transcript-panel"
      data-video-id={String(props["videoId"] ?? "")}
    />
  )),
}));

// Stubs for other heavy components
vi.mock("../../components/ClassificationSection", () => ({
  ClassificationSection: () => <div data-testid="classification-section" />,
}));

vi.mock("../../components/EntityMentionsPanel", () => ({
  EntityMentionsPanel: () => <div data-testid="entity-mentions-panel" />,
}));

vi.mock("../../components/UnavailabilityBanner", () => ({
  UnavailabilityBanner: () => <div data-testid="unavailability-banner" />,
}));

vi.mock("../../components/LoadingState", () => ({
  LoadingState: () => <div data-testid="loading-state">Loading...</div>,
}));

// ---------------------------------------------------------------------------
// Import mocked modules for vi.mocked() access
// ---------------------------------------------------------------------------

import { useVideoDetail } from "../../hooks/useVideoDetail";
import { useDeepLinkParams } from "../../hooks/useDeepLinkParams";
import { useOnboardingStatus } from "../../hooks/useOnboarding";
import { useVideoPlaylists } from "../../hooks/useVideoPlaylists";
import { useVideoEntities } from "../../hooks/useEntityMentions";
import { useTranscriptDownload } from "../../hooks/useTranscriptDownload";
import { useRecoveryStore } from "../../stores/recoveryStore";
import { useYouTubePlayer } from "../../hooks/useYouTubePlayer";
import { VideoEmbed } from "../../components/video/VideoEmbed";
import { TranscriptPanel } from "../../components/transcript";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

/**
 * Video that has transcripts — triggers the two-column layout with VideoEmbed.
 */
const mockVideoWithTranscript: VideoDetail = {
  video_id: "abc123",
  title: "Test Video With Transcript",
  description: "A test description",
  channel_id: "chan-1",
  channel_title: "Test Channel",
  upload_date: "2024-03-01T00:00:00Z",
  duration: 600,
  view_count: 50000,
  like_count: 1200,
  comment_count: 300,
  tags: ["tag1"],
  category_id: "22",
  category_name: "People & Blogs",
  topics: [],
  default_language: "en",
  made_for_kids: false,
  transcript_summary: {
    count: 3,
    languages: ["en", "es"],
    has_manual: true,
    has_corrections: false,
  },
  availability_status: "available",
  alternative_url: null,
  recovered_at: null,
  recovery_source: null,
};

/**
 * Video that has no transcripts — triggers the single-column thumbnail layout
 * and renders the download button.
 */
const mockVideoWithoutTranscript: VideoDetail = {
  ...mockVideoWithTranscript,
  video_id: "def456",
  title: "Test Video Without Transcript",
  transcript_summary: {
    count: 0,
    languages: [],
    has_manual: false,
    has_corrections: false,
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Builds a TanStack Query result object for useVideoDetail with sensible defaults.
 *
 * @param video - The video data to return (undefined simulates 404 or error)
 * @param overrides - Additional properties to set on the result object
 */
function makeVideoDetailResult(
  video: VideoDetail | undefined,
  overrides: {
    isLoading?: boolean;
    isError?: boolean;
    error?: unknown;
  } = {}
): ReturnType<typeof useVideoDetail> {
  const { isLoading = false, isError = false, error = null } = overrides;
  return {
    data: video,
    isLoading,
    isError,
    error,
    refetch: vi.fn(),
    isSuccess: !isLoading && !isError && video !== undefined,
    status: isLoading ? "pending" : isError ? "error" : "success",
    isFetching: isLoading,
    isPending: isLoading,
    isRefetching: false,
    isLoadingError: false,
    isRefetchError: false,
    isPaused: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: Date.now(),
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    fetchStatus: isLoading ? ("fetching" as const) : ("idle" as const),
    isFetched: !isLoading,
    isFetchedAfterMount: !isLoading,
    isInitialLoading: isLoading,
    isEnabled: true,
    promise: Promise.resolve(video),
  } as ReturnType<typeof useVideoDetail>;
}

/**
 * Sets up all hook mocks with sensible defaults. Individual tests override the
 * values they care about after calling this function.
 */
function setupDefaultMocks() {
  vi.mocked(useDeepLinkParams).mockReturnValue({
    lang: null,
    segmentId: null,
    timestamp: null,
    clearDeepLinkParams: vi.fn(),
  });

  vi.mocked(useOnboardingStatus).mockReturnValue({
    data: { is_authenticated: true } as ReturnType<
      typeof useOnboardingStatus
    >["data"],
    isLoading: false,
    isError: false,
    error: null,
  } as ReturnType<typeof useOnboardingStatus>);

  vi.mocked(useVideoPlaylists).mockReturnValue({
    playlists: [],
  } as unknown as ReturnType<typeof useVideoPlaylists>);

  vi.mocked(useVideoEntities).mockReturnValue({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useVideoEntities>);

  vi.mocked(useTranscriptDownload).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useTranscriptDownload>);

  // useYouTubePlayer: lifted to VideoDetailPage (Feature 048 wiring fix).
  // Provide a stable mock so VideoEmbed receives containerRef and playerError.
  vi.mocked(useYouTubePlayer).mockReturnValue({
    containerRef: { current: null },
    isReady: false,
    isPlaying: false,
    currentTime: 0,
    activeSegmentId: null,
    error: null,
    followPlayback: true,
    seekTo: vi.fn(),
    togglePlayback: vi.fn(),
    toggleFollowPlayback: vi.fn(),
  } as unknown as ReturnType<typeof useYouTubePlayer>);

  // Recovery store: provide all selectors and actions the page uses
  vi.mocked(useRecoveryStore).mockImplementation(
    (selector?: unknown) => {
      const state = {
        startRecovery: vi.fn(() => "session-1"),
        updatePhase: vi.fn(),
        setResult: vi.fn(),
        setError: vi.fn(),
        setAbortController: vi.fn(),
        getActiveSession: vi.fn(() => null),
      };
      if (typeof selector === "function") {
        return (selector as (s: typeof state) => unknown)(state);
      }
      return state;
    }
  );
}

/**
 * Renders VideoDetailPage inside MemoryRouter + QueryClientProvider.
 *
 * @param videoId - Route parameter (defaults to "abc123")
 */
function renderPage(videoId = "abc123") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

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
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("VideoDetailPage — Feature 048 layout and interactions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // -------------------------------------------------------------------------
  // TC-1: Two-column layout with VideoEmbed when transcript exists
  // -------------------------------------------------------------------------
  describe("TC-1: Two-column layout when transcript exists (FR-011)", () => {
    it("renders VideoEmbed when the video has transcripts", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
    });

    it("renders TranscriptPanel when the video has transcripts", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("renders VideoEmbed and TranscriptPanel simultaneously", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("renders the two-column grid container when transcript count is > 0", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      const { container } = renderPage("abc123");

      // The grid element uses the grid CSS class from the component template
      const gridEl = container.querySelector(".grid");
      expect(gridEl).toBeInTheDocument();
    });

    it("passes the correct videoId to VideoEmbed", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const mockVideoEmbed = VideoEmbed as ReturnType<typeof vi.fn>;
      expect(mockVideoEmbed).toHaveBeenCalledWith(
        expect.objectContaining({ videoId: "abc123" }),
        undefined
      );
    });

    it("passes availabilityStatus='available' to VideoEmbed", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const mockVideoEmbed = VideoEmbed as ReturnType<typeof vi.fn>;
      expect(mockVideoEmbed).toHaveBeenCalledWith(
        expect.objectContaining({ availabilityStatus: "available" }),
        undefined
      );
    });

    it("passes containerRef and playerError from useYouTubePlayer to VideoEmbed (Feature 048)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const mockVideoEmbed = VideoEmbed as ReturnType<typeof vi.fn>;
      // containerRef and playerError come from the lifted useYouTubePlayer hook
      expect(mockVideoEmbed).toHaveBeenCalledWith(
        expect.objectContaining({
          containerRef: expect.objectContaining({ current: null }),
          playerError: null,
        }),
        undefined
      );
    });

    it("passes player controls from useYouTubePlayer to TranscriptPanel (Feature 048)", () => {
      const mockSeekTo = vi.fn();
      const mockToggleFollowPlayback = vi.fn();
      vi.mocked(useYouTubePlayer).mockReturnValue({
        containerRef: { current: null },
        isReady: true,
        isPlaying: true,
        currentTime: 15,
        activeSegmentId: 3,
        error: null,
        followPlayback: false,
        seekTo: mockSeekTo,
        togglePlayback: vi.fn(),
        toggleFollowPlayback: mockToggleFollowPlayback,
      } as unknown as ReturnType<typeof useYouTubePlayer>);

      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          seekTo: mockSeekTo,
          activeSegmentId: 3,
          followPlayback: false,
          toggleFollowPlayback: mockToggleFollowPlayback,
        }),
        undefined
      );
    });

    it("passes the correct videoId to TranscriptPanel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({ videoId: "abc123" }),
        undefined
      );
    });

    it("passes deep-link params from useDeepLinkParams to TranscriptPanel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en-US",
        segmentId: 7,
        timestamp: 42,
        clearDeepLinkParams: vi.fn(),
      });

      renderPage("abc123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          initialLanguage: "en-US",
          targetSegmentId: 7,
          targetTimestamp: 42,
        }),
        undefined
      );
    });
  });

  // -------------------------------------------------------------------------
  // TC-2: Single-column layout when no transcript exists (FR-008)
  // -------------------------------------------------------------------------
  describe("TC-2: Single-column layout when no transcript (FR-008)", () => {
    it("does NOT render VideoEmbed when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderPage("def456");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });

    it("does NOT render TranscriptPanel when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderPage("def456");

      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("renders a thumbnail image in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      const { container } = renderPage("def456");

      // The single-column branch renders an <img> with the video title as alt text
      const img = container.querySelector("img");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("alt", "Test Video Without Transcript");
    });

    it("renders the article wrapper in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      const { container } = renderPage("def456");

      expect(container.querySelector("article")).toBeInTheDocument();
    });

    it("renders the video title in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderPage("def456");

      expect(
        screen.getByRole("heading", { name: "Test Video Without Transcript", level: 1 })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // TC-3: Download button regression — present when no transcript (FR-002)
  // -------------------------------------------------------------------------
  describe("TC-3: Download button when no transcript (FR-002 regression)", () => {
    it("renders the Download Transcript button when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderPage("def456");

      // aria-label in idle state: "Download transcript for this video"
      expect(
        screen.getByRole("button", { name: /download transcript for this video/i })
      ).toBeInTheDocument();
    });

    it("does NOT render the Download Transcript button when transcript count is > 0", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(
        screen.queryByRole("button", { name: /download transcript/i })
      ).not.toBeInTheDocument();
    });

    it("download button is disabled when user is not authenticated (FR-003)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );
      vi.mocked(useOnboardingStatus).mockReturnValue({
        data: { is_authenticated: false } as ReturnType<
          typeof useOnboardingStatus
        >["data"],
        isLoading: false,
        isError: false,
        error: null,
      } as ReturnType<typeof useOnboardingStatus>);

      renderPage("def456");

      const btn = screen.getByRole("button", {
        name: /download transcript for this video/i,
      });
      expect(btn).toBeDisabled();
    });

    it("download button is enabled when user is authenticated", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderPage("def456");

      const btn = screen.getByRole("button", {
        name: /download transcript for this video/i,
      });
      expect(btn).toBeEnabled();
    });

    it("calls the download mutate function when the button is clicked", async () => {
      const user = userEvent.setup();
      const mockMutate = vi.fn();

      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );
      vi.mocked(useTranscriptDownload).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as unknown as ReturnType<typeof useTranscriptDownload>);

      renderPage("def456");

      await user.click(
        screen.getByRole("button", { name: /download transcript for this video/i })
      );

      expect(mockMutate).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // TC-4: aria-live polite region present (a11y requirement)
  // -------------------------------------------------------------------------
  describe("TC-4: aria-live polite region accessibility", () => {
    it("has an aria-live=polite region in the error state", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Server error", status: 500 },
        })
      );

      const { container } = renderPage("abc123");

      // The error state renders: role="alert" aria-live="polite"
      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });

    it("error alert has role=alert with aria-live=polite", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Server error" },
        })
      );

      const { container } = renderPage("abc123");

      const alertEl = container.querySelector('[role="alert"][aria-live="polite"]');
      expect(alertEl).toBeInTheDocument();
    });

    it("download error message has aria-live=polite when download fails (FR-006)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );
      // Simulate a failed download mutation
      vi.mocked(useTranscriptDownload).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
        isError: true,
        error: { status: 503, message: "Rate limited" },
        reset: vi.fn(),
      } as unknown as ReturnType<typeof useTranscriptDownload>);

      const { container } = renderPage("def456");

      // The TranscriptDownloadButton renders a <p aria-live="polite"> for the error msg
      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // TC-5: Loading and error guard clauses
  // -------------------------------------------------------------------------
  describe("TC-5: Loading and error guard clauses", () => {
    it("renders LoadingState component when video is loading", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, { isLoading: true })
      );

      renderPage("abc123");

      expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    });

    it("does not render VideoEmbed or TranscriptPanel when loading", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, { isLoading: true })
      );

      renderPage("abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("renders the unified error message when video fetch fails (FR-027)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Server error", status: 500 },
        })
      );

      renderPage("abc123");

      expect(screen.getByText("Could not load video.")).toBeInTheDocument();
    });

    it("renders a Retry button in the error state", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Network error" },
        })
      );

      renderPage("abc123");

      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    it("does not render VideoEmbed or TranscriptPanel in the error state (FR-026)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Network error" },
        })
      );

      renderPage("abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("renders Video Not Found heading when video data is undefined after success", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined)
      );

      renderPage("abc123");

      expect(screen.getByText("Video Not Found")).toBeInTheDocument();
    });

    it("does not render VideoEmbed when video data is undefined (404 state)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined)
      );

      renderPage("abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // TC-6: Navigation and metadata in loaded state
  // -------------------------------------------------------------------------
  describe("TC-6: Navigation links and video metadata", () => {
    it("renders at least one Back to Videos link in the header", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const backLinks = screen.getAllByRole("link", { name: /back to videos/i });
      expect(backLinks.length).toBeGreaterThanOrEqual(1);
    });

    it("renders Watch on YouTube link pointing to the correct URL", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const ytLink = screen.getByRole("link", { name: /watch on youtube/i });
      expect(ytLink).toBeInTheDocument();
      expect(ytLink).toHaveAttribute(
        "href",
        "https://www.youtube.com/watch?v=abc123"
      );
    });

    it("Watch on YouTube link opens in a new tab", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const ytLink = screen.getByRole("link", { name: /watch on youtube/i });
      expect(ytLink).toHaveAttribute("target", "_blank");
      expect(ytLink).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("renders the video title as an h1 heading in two-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(
        screen.getByRole("heading", {
          name: "Test Video With Transcript",
          level: 1,
        })
      ).toBeInTheDocument();
    });

    it("renders the channel name in two-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByText("Test Channel")).toBeInTheDocument();
    });

    it("renders the channel name as a link to the channel page", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      const channelLink = screen.getByRole("link", { name: "Test Channel" });
      expect(channelLink).toHaveAttribute("href", "/channels/chan-1");
    });
  });

  // -------------------------------------------------------------------------
  // TC-7: Unavailability banner and auxiliary panels
  // -------------------------------------------------------------------------
  describe("TC-7: Auxiliary panels always rendered when video data is present", () => {
    it("renders the UnavailabilityBanner for available videos", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("unavailability-banner")).toBeInTheDocument();
    });

    it("renders the ClassificationSection panel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("classification-section")).toBeInTheDocument();
    });

    it("renders the EntityMentionsPanel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderPage("abc123");

      expect(screen.getByTestId("entity-mentions-panel")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // TC-8: Boundary — transcript_summary.count boundary values
  // -------------------------------------------------------------------------
  describe("TC-8: transcript_summary.count boundary values", () => {
    it("treats count=1 as having a transcript (two-column layout)", () => {
      const videoCount1: VideoDetail = {
        ...mockVideoWithTranscript,
        transcript_summary: { count: 1, languages: ["en"], has_manual: false, has_corrections: false },
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoCount1)
      );

      renderPage("abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("treats count=0 as no transcript (single-column layout)", () => {
      const videoCount0: VideoDetail = {
        ...mockVideoWithTranscript,
        transcript_summary: { count: 0, languages: [], has_manual: false, has_corrections: false },
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoCount0)
      );

      renderPage("abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("treats null transcript_summary as no transcript (count defaults to 0)", () => {
      const videoNoSummary: VideoDetail = {
        ...mockVideoWithTranscript,
        // Cast: in practice the API may return null for videos never fetched
        transcript_summary: null as unknown as VideoDetail["transcript_summary"],
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoNoSummary)
      );

      renderPage("abc123");

      // hasTranscript = (null?.count ?? 0) > 0 = false → single-column
      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });
  });
});
