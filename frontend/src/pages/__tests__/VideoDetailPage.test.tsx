/**
 * Tests for VideoDetailPage component.
 *
 * Covers:
 * - Deep link params (lang, seg, t) correctly passed to TranscriptPanel, with
 *   null values converted to undefined via the ?? operator, and
 *   clearDeepLinkParams passed through as onDeepLinkComplete (T057-era tests)
 * - Loading, error (network + 404), and success guard clauses
 * - Feature 048 (User Story 3) two-column layout: VideoEmbed + TranscriptPanel
 *   when a transcript exists, single-column thumbnail layout otherwise, the
 *   Download Transcript button regression, aria-live error regions,
 *   useYouTubePlayer `enabled` wiring, and transcript_summary.count boundaries
 * - Formatted video metadata (view/like counts, duration, description)
 * - 404 state content (heading, description, Back to Videos link)
 * - Retry button interaction (calls refetch)
 * - Channel link navigation, hover styling, "Unknown Channel" fallback, and
 *   keyboard accessibility (US3)
 *
 * Note: Scan for Entity Mentions button tests have been moved to
 * src/components/__tests__/EntityMentionsPanel.test.tsx (the button now lives
 * inside EntityMentionsPanel). Tag-badge rendering ("should render tags as
 * badges" / "should show 'None' for tags") is covered by
 * ClassificationSection's own test suite — ClassificationSection is stubbed
 * here, consistent with the EntityMentionsPanel precedent above.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { VideoDetailPage } from "../VideoDetailPage";
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

// Mock the deep link params hook
const mockClearDeepLinkParams = vi.fn();
vi.mock("../../hooks/useDeepLinkParams", () => ({
  useDeepLinkParams: vi.fn(),
}));

// Mock useVideoDetail to return test video data
vi.mock("../../hooks/useVideoDetail", () => ({
  useVideoDetail: vi.fn(),
}));

// Mock useVideoPlaylists
vi.mock("../../hooks/useVideoPlaylists", () => ({
  useVideoPlaylists: vi.fn(() => ({ playlists: [] })),
}));

// Mock useOnboardingStatus — provides auth state for the download button gate
vi.mock("../../hooks/useOnboarding", () => ({
  useOnboardingStatus: vi.fn(),
}));

// Mock useTranscriptDownload — prevents mutation side-effects
vi.mock("../../hooks/useTranscriptDownload", () => ({
  useTranscriptDownload: vi.fn(),
}));

// Mock useYouTubePlayer — lifted to VideoDetailPage (Feature 048) so its
// return values are passed to VideoEmbed and TranscriptPanel.
vi.mock("../../hooks/useYouTubePlayer", () => ({
  useYouTubePlayer: vi.fn(),
}));

// Mock recoveryStore — prevents Zustand state leaking between tests
vi.mock("../../stores/recoveryStore", () => ({
  useRecoveryStore: vi.fn(),
}));

// Mock TranscriptPanel to capture props
vi.mock("../../components/transcript", () => ({
  TranscriptPanel: vi.fn((props: Record<string, unknown>) => (
    <div data-testid="transcript-panel" data-props={JSON.stringify(props)} />
  )),
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

// Mock ClassificationSection
vi.mock("../../components/ClassificationSection", () => ({
  ClassificationSection: () => <div data-testid="classification-section" />,
}));

// Mock LoadingState
vi.mock("../../components/LoadingState", () => ({
  LoadingState: () => <div data-testid="loading-state" />,
}));

// Mock EntityMentionsPanel to prevent real API calls from useEntityMentions
vi.mock("../../components/EntityMentionsPanel", () => ({
  EntityMentionsPanel: () => <div data-testid="entity-mentions-panel" />,
}));

// Mock UnavailabilityBanner
vi.mock("../../components/UnavailabilityBanner", () => ({
  UnavailabilityBanner: () => <div data-testid="unavailability-banner" />,
}));

// Mock useEntityMentions to prevent unintended network requests
vi.mock("../../hooks/useEntityMentions", () => ({
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
  useEntityVideos: vi.fn(() => ({
    videos: [],
    total: null,
    pagination: null,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
  })),
  useScanEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useScanVideoEntities: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
}));

// Import mocked functions after mock declarations
import { useDeepLinkParams } from "../../hooks/useDeepLinkParams";
import { useVideoDetail } from "../../hooks/useVideoDetail";
import { useOnboardingStatus } from "../../hooks/useOnboarding";
import { useTranscriptDownload } from "../../hooks/useTranscriptDownload";
import { useYouTubePlayer } from "../../hooks/useYouTubePlayer";
import { useRecoveryStore } from "../../stores/recoveryStore";
import { TranscriptPanel } from "../../components/transcript";
import { VideoEmbed } from "../../components/video/VideoEmbed";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/**
 * Mock video data matching VideoDetail interface.
 */
const mockVideo: VideoDetail = {
  video_id: "test-video-123",
  title: "Test Video Title",
  description: "Test video description",
  channel_id: "channel-1",
  channel_title: "Test Channel",
  upload_date: "2024-01-15T00:00:00Z",
  duration: 300,
  view_count: 1000,
  like_count: 50,
  comment_count: 25,
  tags: ["test", "video"],
  category_id: "22",
  category_name: "People & Blogs",
  topics: [],
  default_language: "en",
  made_for_kids: false,
  transcript_summary: {
    count: 2,
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
 * Builds a TanStack Query result object for useVideoDetail with sensible
 * defaults. Individual tests only need to specify what they care about.
 *
 * @param video - The video data to return (undefined/null simulates 404 or error)
 * @param overrides - Additional properties to set on the result object
 */
function makeVideoDetailResult(
  video: VideoDetail | undefined | null,
  overrides: {
    isLoading?: boolean;
    isError?: boolean;
    error?: unknown;
    refetch?: () => void;
  } = {}
): ReturnType<typeof useVideoDetail> {
  const { isLoading = false, isError = false, error = null, refetch = vi.fn() } =
    overrides;
  return {
    data: video,
    isLoading,
    isError,
    error,
    refetch,
    isSuccess: !isLoading && !isError && video != null,
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
    promise: Promise.resolve(video ?? undefined),
  } as unknown as ReturnType<typeof useVideoDetail>;
}

/**
 * Renders VideoDetailPage with MemoryRouter and QueryClientProvider.
 *
 * @param url - Initial URL for MemoryRouter (default: '/videos/test-video-123')
 * @returns Render result from @testing-library/react
 */
function renderVideoDetailPage(url = "/videos/test-video-123") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/videos/:videoId" element={<VideoDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VideoDetailPage", () => {
  beforeEach(() => {
    // Reset all mocks before each test
    vi.clearAllMocks();

    // Default mock implementation for useVideoDetail (successful load)
    vi.mocked(useVideoDetail).mockReturnValue(makeVideoDetailResult(mockVideo));

    // Default: no deep-link query params present
    vi.mocked(useDeepLinkParams).mockReturnValue({
      lang: null,
      segmentId: null,
      timestamp: null,
      clearDeepLinkParams: mockClearDeepLinkParams,
    });

    // Defaults for the hooks VideoDetailPage calls unconditionally (Feature 048).
    // Individual tests below override what they need.
    vi.mocked(useOnboardingStatus).mockReturnValue({
      data: { is_authenticated: true } as ReturnType<
        typeof useOnboardingStatus
      >["data"],
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useOnboardingStatus>);

    vi.mocked(useTranscriptDownload).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useTranscriptDownload>);

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

    vi.mocked(useRecoveryStore).mockImplementation((selector?: unknown) => {
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
    });
  });

  describe("Deep Link Parameter Passing", () => {
    it("passes all deep link params to TranscriptPanel when URL has ?lang=en-US&seg=42&t=125", () => {
      // Mock hook to return all params
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en-US",
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en-US&seg=42&t=125");

      // Verify TranscriptPanel was rendered
      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();

      // Verify all props were passed correctly
      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: "en-US",
          targetSegmentId: 42,
          targetTimestamp: 125,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined // React internal ref
      );
    });

    it("passes onDeepLinkComplete callback from clearDeepLinkParams", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "es",
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=es");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it("passes only lang param when URL has ?lang=en-US without seg/t", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en-US",
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en-US");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: "en-US",
          targetSegmentId: undefined, // null converted to undefined
          targetTimestamp: undefined, // null converted to undefined
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it("passes only seg and t params when URL has ?seg=10&t=50 without lang", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 10,
        timestamp: 50,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?seg=10&t=50");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: undefined, // null converted to undefined
          targetSegmentId: 10,
          targetTimestamp: 50,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });
  });

  describe("Without Deep Link Parameters", () => {
    it("passes undefined for all optional params when URL has no query params", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: undefined,
          targetSegmentId: undefined,
          targetTimestamp: undefined,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it("still passes clearDeepLinkParams even when no params are present", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs).toBeDefined();
      expect(callArgs?.onDeepLinkComplete).toBe(mockClearDeepLinkParams);
    });
  });

  describe("Invalid Parameter Handling", () => {
    it("passes undefined for segmentId when hook returns null (invalid seg param)", () => {
      // Hook returns null when seg param is invalid (e.g., seg=abc)
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: null, // Invalid seg=abc becomes null from hook
        timestamp: 100,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en&seg=abc&t=100");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: "en",
          targetSegmentId: undefined, // null converted to undefined
          targetTimestamp: 100,
        }),
        undefined
      );
    });

    it("passes undefined for timestamp when hook returns null (invalid t param)", () => {
      // Hook returns null when t param is invalid (e.g., t=xyz)
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "fr",
        segmentId: 5,
        timestamp: null, // Invalid t=xyz becomes null from hook
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=fr&seg=5&t=xyz");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: "fr",
          targetSegmentId: 5,
          targetTimestamp: undefined, // null converted to undefined
        }),
        undefined
      );
    });

    it("passes undefined for all params when all are invalid", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null, // Empty/whitespace lang becomes null
        segmentId: null, // Invalid seg becomes null
        timestamp: null, // Invalid t becomes null
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=&seg=0&t=-1");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
          initialLanguage: undefined,
          targetSegmentId: undefined,
          targetTimestamp: undefined,
        }),
        undefined
      );
    });
  });

  describe("Null to Undefined Conversion", () => {
    it("converts null lang to undefined via ?? operator", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.initialLanguage).toBeUndefined();
      expect(callArgs?.initialLanguage).not.toBeNull();
    });

    it("converts null segmentId to undefined via ?? operator", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: null,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.targetSegmentId).toBeUndefined();
      expect(callArgs?.targetSegmentId).not.toBeNull();
    });

    it("converts null timestamp to undefined via ?? operator", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: 42,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.targetTimestamp).toBeUndefined();
      expect(callArgs?.targetTimestamp).not.toBeNull();
    });
  });

  describe("Edge Cases", () => {
    it("passes timestamp=0 when hook returns 0 (valid zero value)", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: 1,
        timestamp: 0, // Zero is valid for timestamp
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en&seg=1&t=0");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetTimestamp: 0,
        }),
        undefined
      );
    });

    it("passes BCP-47 language codes with variants correctly", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "zh-Hans-CN",
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=zh-Hans-CN");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          initialLanguage: "zh-Hans-CN",
        }),
        undefined
      );
    });

    it("passes large segment IDs correctly", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 999999,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?seg=999999");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetSegmentId: 999999,
        }),
        undefined
      );
    });

    it("passes large timestamps correctly", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: 9999999,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?t=9999999");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetTimestamp: 9999999,
        }),
        undefined
      );
    });
  });

  describe("Guard Clauses - TranscriptPanel Not Rendered", () => {
    it("does not render TranscriptPanel when video is loading", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, { isLoading: true })
      );

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en&seg=42&t=125");

      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
      expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    });

    it("does not render TranscriptPanel when video fetch errors", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Failed to fetch", status: 500 },
        })
      );

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en&seg=42&t=125");

      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Could not load video.")).toBeInTheDocument();
    });

    it("does not render TranscriptPanel when video is not found", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined) // No data
      );

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: "en",
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123?lang=en&seg=42&t=125");

      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
      expect(screen.getByText("Video Not Found")).toBeInTheDocument();
    });
  });

  describe("TranscriptPanel Always Receives videoId", () => {
    it("passes videoId from route params to TranscriptPanel", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage("/videos/test-video-123");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "test-video-123",
        }),
        undefined
      );
    });

    it("passes different videoId for different routes", () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      // Update mock video to match the new ID
      const newMockVideo = { ...mockVideo, video_id: "another-video-456" };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(newMockVideo)
      );

      renderVideoDetailPage("/videos/another-video-456");

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: "another-video-456",
        }),
        undefined
      );
    });
  });

  // ---------------------------------------------------------------------------
  // Scan for Entity Mentions button tests have been moved to
  // src/components/__tests__/EntityMentionsPanel.test.tsx
  // ---------------------------------------------------------------------------

  describe("EntityMentionsPanel receives hasTranscript prop", () => {
    beforeEach(() => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });
    });

    it("renders entity-mentions-panel for a video with transcripts", () => {
      renderVideoDetailPage("/videos/test-video-123");
      // The EntityMentionsPanel mock renders a div with data-testid="entity-mentions-panel".
      // The real scan button behaviour is tested in EntityMentionsPanel.test.tsx.
      expect(screen.getByTestId("entity-mentions-panel")).toBeInTheDocument();
    });

    it("renders entity-mentions-panel even when video has no transcripts", () => {
      const videoNoTranscript: VideoDetail = {
        ...mockVideo,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
          has_corrections: false,
        },
      };

      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoNoTranscript)
      );

      renderVideoDetailPage("/videos/test-video-123");

      expect(screen.getByTestId("entity-mentions-panel")).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Feature 048 (User Story 3): two-column layout, download button, aria-live
  // regions, useYouTubePlayer wiring, and transcript-count boundaries.
  // ---------------------------------------------------------------------------

  describe("TC-1: Two-column layout when transcript exists (FR-011)", () => {
    it("renders VideoEmbed when the video has transcripts", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
    });

    it("renders TranscriptPanel when the video has transcripts", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("renders VideoEmbed and TranscriptPanel simultaneously", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("renders the two-column grid container when transcript count is > 0", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      const { container } = renderVideoDetailPage("/videos/abc123");

      // The grid element uses the grid CSS class from the component template
      const gridEl = container.querySelector(".grid");
      expect(gridEl).toBeInTheDocument();
    });

    it("passes the correct videoId to VideoEmbed", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

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

  describe("TC-2: Single-column layout when no transcript (FR-008)", () => {
    it("does NOT render VideoEmbed when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });

    it("does NOT render TranscriptPanel when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("renders a thumbnail image in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      const { container } = renderVideoDetailPage("/videos/def456");

      // The single-column branch renders an <img> with the video title as alt text
      const img = container.querySelector("img");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("alt", "Test Video Without Transcript");
    });

    it("renders the article wrapper in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      const { container } = renderVideoDetailPage("/videos/def456");

      expect(container.querySelector("article")).toBeInTheDocument();
    });

    it("renders the video title in single-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

      expect(
        screen.getByRole("heading", {
          name: "Test Video Without Transcript",
          level: 1,
        })
      ).toBeInTheDocument();
    });
  });

  describe("TC-3: Download button when no transcript (FR-002 regression)", () => {
    it("renders the Download Transcript button when transcript count is zero", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

      // aria-label in idle state: "Download transcript for this video"
      expect(
        screen.getByRole("button", {
          name: /download transcript for this video/i,
        })
      ).toBeInTheDocument();
    });

    it("does NOT render the Download Transcript button when transcript count is > 0", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/def456");

      const btn = screen.getByRole("button", {
        name: /download transcript for this video/i,
      });
      expect(btn).toBeDisabled();
    });

    it("download button is enabled when user is authenticated", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

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

      renderVideoDetailPage("/videos/def456");

      await user.click(
        screen.getByRole("button", {
          name: /download transcript for this video/i,
        })
      );

      expect(mockMutate).toHaveBeenCalledTimes(1);
    });
  });

  describe("TC-4: aria-live polite region accessibility", () => {
    it("has an aria-live=polite region in the error state", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Server error", status: 500 },
        })
      );

      const { container } = renderVideoDetailPage("/videos/abc123");

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

      const { container } = renderVideoDetailPage("/videos/abc123");

      const alertEl = container.querySelector(
        '[role="alert"][aria-live="polite"]'
      );
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

      const { container } = renderVideoDetailPage("/videos/def456");

      // The TranscriptDownloadButton renders a <p aria-live="polite"> for the error msg
      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });
  });

  describe("TC-5: Loading and error guard clauses (Feature 048)", () => {
    it("renders LoadingState component when video is loading", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, { isLoading: true })
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    });

    it("does not render VideoEmbed or TranscriptPanel when loading", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, { isLoading: true })
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("does not render VideoEmbed or TranscriptPanel in the error state (FR-026)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Network error" },
        })
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("renders a Retry button in the error state", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { message: "Network error" },
        })
      );

      renderVideoDetailPage("/videos/abc123");

      expect(
        screen.getByRole("button", { name: /retry/i })
      ).toBeInTheDocument();
    });

    it("does not render VideoEmbed when video data is undefined (404 state)", () => {
      vi.mocked(useVideoDetail).mockReturnValue(makeVideoDetailResult(undefined));

      renderVideoDetailPage("/videos/abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });
  });

  describe("TC-6: Navigation links and video metadata", () => {
    it("renders at least one Back to Videos link in the header", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      const backLinks = screen.getAllByRole("link", {
        name: /back to videos/i,
      });
      expect(backLinks.length).toBeGreaterThanOrEqual(1);
    });

    it("renders Watch on YouTube link pointing to the correct URL", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

      const ytLink = screen.getByRole("link", { name: /watch on youtube/i });
      expect(ytLink).toHaveAttribute("target", "_blank");
      expect(ytLink).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("renders the video title as an h1 heading in two-column layout", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

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

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByText("Test Channel")).toBeInTheDocument();
    });

    it("renders the channel name as a link to the channel page", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      const channelLink = screen.getByRole("link", { name: "Test Channel" });
      expect(channelLink).toHaveAttribute("href", "/channels/chan-1");
    });
  });

  describe("TC-7: Auxiliary panels always rendered when video data is present", () => {
    it("renders the UnavailabilityBanner for available videos", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("unavailability-banner")).toBeInTheDocument();
    });

    it("renders the ClassificationSection panel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("classification-section")).toBeInTheDocument();
    });

    it("renders the EntityMentionsPanel", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("entity-mentions-panel")).toBeInTheDocument();
    });
  });

  // VideoDetailPage computes:
  //   playerEnabled = (video?.transcript_summary?.count ?? 0) > 0
  //                   && video?.availability_status === "available"
  // and passes it as `enabled` to useYouTubePlayer. These tests verify the
  // three logical cases by inspecting the mock's call arguments.
  describe("TC-8: useYouTubePlayer enabled prop wiring", () => {
    it("calls useYouTubePlayer with enabled=false when the video has no transcript", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithoutTranscript)
      );

      renderVideoDetailPage("/videos/def456");

      const mockHook = vi.mocked(useYouTubePlayer);
      // The hook is called unconditionally — check the most recent call.
      const lastCall = mockHook.mock.calls[mockHook.mock.calls.length - 1];
      expect(lastCall?.[0]).toMatchObject({ enabled: false });
    });

    it("calls useYouTubePlayer with enabled=true when transcript exists and video is available", () => {
      // mockVideoWithTranscript has count=3 and availability_status="available"
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      const mockHook = vi.mocked(useYouTubePlayer);
      const lastCall = mockHook.mock.calls[mockHook.mock.calls.length - 1];
      expect(lastCall?.[0]).toMatchObject({ enabled: true });
    });

    it("calls useYouTubePlayer with enabled=false when video is unavailable even with a transcript", () => {
      const deletedVideoWithTranscript: VideoDetail = {
        ...mockVideoWithTranscript,
        availability_status: "deleted",
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(deletedVideoWithTranscript)
      );

      renderVideoDetailPage("/videos/abc123");

      const mockHook = vi.mocked(useYouTubePlayer);
      const lastCall = mockHook.mock.calls[mockHook.mock.calls.length - 1];
      expect(lastCall?.[0]).toMatchObject({ enabled: false });
    });
  });

  describe("TC-9: transcript_summary.count boundary values", () => {
    it("reads count=1 as having a transcript (two-column layout)", () => {
      const videoCount1: VideoDetail = {
        ...mockVideoWithTranscript,
        transcript_summary: {
          count: 1,
          languages: ["en"],
          has_manual: false,
          has_corrections: false,
        },
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoCount1)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.getByTestId("video-embed")).toBeInTheDocument();
      expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
    });

    it("reads count=0 as no transcript (single-column layout)", () => {
      const videoCount0: VideoDetail = {
        ...mockVideoWithTranscript,
        transcript_summary: {
          count: 0,
          languages: [],
          has_manual: false,
          has_corrections: false,
        },
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoCount0)
      );

      renderVideoDetailPage("/videos/abc123");

      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("transcript-panel")).not.toBeInTheDocument();
    });

    it("reads null transcript_summary as no transcript (count defaults to 0)", () => {
      const videoNoSummary: VideoDetail = {
        ...mockVideoWithTranscript,
        // Cast: in practice the API may return null for videos never fetched
        transcript_summary: null as unknown as VideoDetail["transcript_summary"],
      };
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(videoNoSummary)
      );

      renderVideoDetailPage("/videos/abc123");

      // hasTranscript = (null?.count ?? 0) > 0 = false → single-column
      expect(screen.queryByTestId("video-embed")).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Formatted video metadata (view/like counts, duration, description).
  // Tag-badge rendering itself is covered by ClassificationSection's own
  // suite; ClassificationSection is stubbed in this file.
  // ---------------------------------------------------------------------------

  describe("Video Data Display (formatted metadata)", () => {
    const mockVideoData: VideoDetail = {
      video_id: "dQw4w9WgXcQ",
      title: "Test Video Title",
      description: "This is a test video description.",
      channel_id: "UC123456",
      channel_title: "Test Channel",
      upload_date: "2024-01-15T10:30:00Z",
      duration: 245, // 4:05
      view_count: 1234567,
      like_count: 98765,
      comment_count: 4321,
      tags: ["test", "video", "example"],
      category_id: "22",
      category_name: null,
      topics: [],
      default_language: "en",
      made_for_kids: false,
      availability_status: "available",
      alternative_url: null,
      recovered_at: null,
      recovery_source: null,
      transcript_summary: {
        count: 2,
        languages: ["en", "es"],
        has_manual: true,
        has_corrections: false,
      },
    };

    beforeEach(() => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoData)
      );
    });

    it("should render formatted view count", () => {
      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      expect(screen.getByText("1.2M views")).toBeInTheDocument();
    });

    it("should render formatted like count", () => {
      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      expect(screen.getByText("98.8K likes")).toBeInTheDocument();
    });

    it("should render formatted duration", () => {
      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      expect(screen.getByText("4:05")).toBeInTheDocument();
    });

    it("should render description", () => {
      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      expect(
        screen.getByText("This is a test video description.")
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // 404 state content — heading is already covered under "Guard Clauses"
  // above; these add the descriptive text and the 404-specific Back link.
  // ---------------------------------------------------------------------------

  describe("404 Error Display", () => {
    it("should render 404 state when video is null", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(null) as ReturnType<typeof useVideoDetail>
      );

      renderVideoDetailPage("/videos/invalid-id");

      expect(
        screen.getByRole("heading", { name: "Video Not Found" })
      ).toBeInTheDocument();
      expect(
        screen.getByText(/doesn't exist or has been removed/i)
      ).toBeInTheDocument();
    });

    it("should render Back to Videos link in 404 state", () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(null) as ReturnType<typeof useVideoDetail>
      );

      renderVideoDetailPage("/videos/invalid-id");

      const backLink = screen.getAllByRole("link", {
        name: /back to videos/i,
      })[0];
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute("href", "/videos");
    });
  });

  describe("Error State Interactions", () => {
    it("should call refetch when Retry button is clicked", async () => {
      const user = userEvent.setup();
      const mockRefetch = vi.fn();

      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(undefined, {
          isError: true,
          error: { type: "network", message: "Network error" },
          refetch: mockRefetch,
        })
      );

      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      const retryButton = screen.getByRole("button", { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe("Channel Link Navigation (US3)", () => {
    const mockVideoData: VideoDetail = {
      video_id: "dQw4w9WgXcQ",
      title: "Test Video Title",
      description: "This is a test video description.",
      channel_id: "UC123456",
      channel_title: "Test Channel",
      upload_date: "2024-01-15T10:30:00Z",
      duration: 245,
      view_count: 1234567,
      like_count: 98765,
      comment_count: 4321,
      tags: ["test", "video", "example"],
      category_id: "22",
      category_name: null,
      topics: [],
      default_language: "en",
      made_for_kids: false,
      availability_status: "available",
      alternative_url: null,
      recovered_at: null,
      recovery_source: null,
      transcript_summary: {
        count: 2,
        languages: ["en", "es"],
        has_manual: true,
        has_corrections: false,
      },
    };

    beforeEach(() => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult(mockVideoData)
      );
    });

    it("should have hover state on channel link (FR-014)", () => {
      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      const channelLink = screen.getByRole("link", { name: "Test Channel" });
      // Check for hover class indicating hover state
      expect(channelLink).toHaveClass("hover:text-blue-600");
    });

    it('should display "Unknown Channel" without link when channel is null (FR-015)', () => {
      vi.mocked(useVideoDetail).mockReturnValue(
        makeVideoDetailResult({
          ...mockVideoData,
          channel_id: null,
          channel_title: null,
        })
      );

      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      // Should display "Unknown Channel" text
      expect(screen.getByText("Unknown Channel")).toBeInTheDocument();

      // Should NOT be a link
      const unknownChannelText = screen.getByText("Unknown Channel");
      expect(unknownChannelText.tagName).not.toBe("A");
    });

    it("should be keyboard accessible", async () => {
      const user = userEvent.setup();

      renderVideoDetailPage("/videos/dQw4w9WgXcQ");

      const channelLink = screen.getByRole("link", { name: "Test Channel" });

      // Tab to the channel link
      await user.tab();

      // Channel link should be focusable
      expect(channelLink).toBeVisible();
    });
  });
});
