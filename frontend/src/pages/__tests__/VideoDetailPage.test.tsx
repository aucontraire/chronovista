/**
 * Tests for VideoDetailPage component.
 *
 * Tests deep link parameter passing from useDeepLinkParams hook to TranscriptPanel component.
 * Verifies that URL query parameters (lang, seg, t) are correctly extracted and passed down.
 *
 * Key behaviors tested:
 * - Deep link params (lang, seg, t) correctly passed to TranscriptPanel
 * - Null values converted to undefined via ?? operator
 * - clearDeepLinkParams callback passed as onDeepLinkComplete
 * - Invalid params (from hook validation) result in undefined props
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { VideoDetailPage } from '../VideoDetailPage';
import type { VideoDetail } from '../../types/video';

// Mock the deep link params hook
const mockClearDeepLinkParams = vi.fn();
vi.mock('../../hooks/useDeepLinkParams', () => ({
  useDeepLinkParams: vi.fn(),
}));

// Mock useVideoDetail to return test video data
vi.mock('../../hooks/useVideoDetail', () => ({
  useVideoDetail: vi.fn(),
}));

// Mock useVideoPlaylists
vi.mock('../../hooks/useVideoPlaylists', () => ({
  useVideoPlaylists: vi.fn(() => ({ playlists: [] })),
}));

// Mock TranscriptPanel to capture props
vi.mock('../../components/transcript', () => ({
  TranscriptPanel: vi.fn((props: Record<string, unknown>) => (
    <div data-testid="transcript-panel" data-props={JSON.stringify(props)} />
  )),
}));

// Mock ClassificationSection
vi.mock('../../components/ClassificationSection', () => ({
  ClassificationSection: () => <div data-testid="classification-section" />,
}));

// Mock LoadingState
vi.mock('../../components/LoadingState', () => ({
  LoadingState: () => <div data-testid="loading-state" />,
}));

// Import mocked functions after mock declarations
import { useDeepLinkParams } from '../../hooks/useDeepLinkParams';
import { useVideoDetail } from '../../hooks/useVideoDetail';
import { TranscriptPanel } from '../../components/transcript';

/**
 * Mock video data matching VideoDetail interface.
 */
const mockVideo: VideoDetail = {
  video_id: 'test-video-123',
  title: 'Test Video Title',
  description: 'Test video description',
  channel_id: 'channel-1',
  channel_title: 'Test Channel',
  upload_date: '2024-01-15T00:00:00Z',
  duration: 300,
  view_count: 1000,
  like_count: 50,
  comment_count: 25,
  tags: ['test', 'video'],
  category_id: '22',
  category_name: 'People & Blogs',
  topics: [],
  default_language: 'en',
  made_for_kids: false,
  transcript_summary: {
    count: 2,
    languages: ['en', 'es'],
    has_manual: true,
  },
  availability_status: 'available',
  alternative_url: null,
};

/**
 * Renders VideoDetailPage with MemoryRouter and QueryClientProvider.
 *
 * @param url - Initial URL for MemoryRouter (default: '/videos/test-video-123')
 * @returns Render result from @testing-library/react
 */
function renderVideoDetailPage(url = '/videos/test-video-123') {
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

describe('VideoDetailPage', () => {
  beforeEach(() => {
    // Reset all mocks before each test
    vi.clearAllMocks();

    // Default mock implementation for useVideoDetail
    vi.mocked(useVideoDetail).mockReturnValue({
      data: mockVideo,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: true,
      status: "success",
      isFetching: false,
      isPending: false,
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
      fetchStatus: "idle" as const,
      isFetched: true,
      isFetchedAfterMount: true,
      isInitialLoading: false,
      isEnabled: true,
      promise: Promise.resolve(mockVideo),
    } as ReturnType<typeof useVideoDetail>);
  });

  describe('Deep Link Parameter Passing', () => {
    it('passes all deep link params to TranscriptPanel when URL has ?lang=en-US&seg=42&t=125', () => {
      // Mock hook to return all params
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en-US',
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en-US&seg=42&t=125');

      // Verify TranscriptPanel was rendered
      expect(screen.getByTestId('transcript-panel')).toBeInTheDocument();

      // Verify all props were passed correctly
      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: 'en-US',
          targetSegmentId: 42,
          targetTimestamp: 125,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined // React internal ref
      );
    });

    it('passes onDeepLinkComplete callback from clearDeepLinkParams', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'es',
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=es');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it('passes only lang param when URL has ?lang=en-US without seg/t', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en-US',
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en-US');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: 'en-US',
          targetSegmentId: undefined, // null converted to undefined
          targetTimestamp: undefined, // null converted to undefined
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it('passes only seg and t params when URL has ?seg=10&t=50 without lang', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 10,
        timestamp: 50,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?seg=10&t=50');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: undefined, // null converted to undefined
          targetSegmentId: 10,
          targetTimestamp: 50,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined,
      );
    });
  });

  describe('Without Deep Link Parameters', () => {
    it('passes undefined for all optional params when URL has no query params', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: undefined,
          targetSegmentId: undefined,
          targetTimestamp: undefined,
          onDeepLinkComplete: mockClearDeepLinkParams,
        }),
        undefined
      );
    });

    it('still passes clearDeepLinkParams even when no params are present', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs).toBeDefined();
      expect(callArgs?.onDeepLinkComplete).toBe(mockClearDeepLinkParams);
    });
  });

  describe('Invalid Parameter Handling', () => {
    it('passes undefined for segmentId when hook returns null (invalid seg param)', () => {
      // Hook returns null when seg param is invalid (e.g., seg=abc)
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: null, // Invalid seg=abc becomes null from hook
        timestamp: 100,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en&seg=abc&t=100');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: 'en',
          targetSegmentId: undefined, // null converted to undefined
          targetTimestamp: 100,
        }),
        undefined
      );
    });

    it('passes undefined for timestamp when hook returns null (invalid t param)', () => {
      // Hook returns null when t param is invalid (e.g., t=xyz)
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'fr',
        segmentId: 5,
        timestamp: null, // Invalid t=xyz becomes null from hook
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=fr&seg=5&t=xyz');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: 'fr',
          targetSegmentId: 5,
          targetTimestamp: undefined, // null converted to undefined
        }),
        undefined
      );
    });

    it('passes undefined for all params when all are invalid', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null, // Empty/whitespace lang becomes null
        segmentId: null, // Invalid seg becomes null
        timestamp: null, // Invalid t becomes null
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=&seg=0&t=-1');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
          initialLanguage: undefined,
          targetSegmentId: undefined,
          targetTimestamp: undefined,
        }),
        undefined
      );
    });
  });

  describe('Null to Undefined Conversion', () => {
    it('converts null lang to undefined via ?? operator', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.initialLanguage).toBeUndefined();
      expect(callArgs?.initialLanguage).not.toBeNull();
    });

    it('converts null segmentId to undefined via ?? operator', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: null,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.targetSegmentId).toBeUndefined();
      expect(callArgs?.targetSegmentId).not.toBeNull();
    });

    it('converts null timestamp to undefined via ?? operator', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: 42,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      const callArgs = mockTranscriptPanel.mock.calls[0]?.[0];
      expect(callArgs?.targetTimestamp).toBeUndefined();
      expect(callArgs?.targetTimestamp).not.toBeNull();
    });
  });

  describe('Edge Cases', () => {
    it('passes timestamp=0 when hook returns 0 (valid zero value)', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: 1,
        timestamp: 0, // Zero is valid for timestamp
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en&seg=1&t=0');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetTimestamp: 0,
        }),
        undefined
      );
    });

    it('passes BCP-47 language codes with variants correctly', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'zh-Hans-CN',
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=zh-Hans-CN');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          initialLanguage: 'zh-Hans-CN',
        }),
        undefined
      );
    });

    it('passes large segment IDs correctly', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: 999999,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?seg=999999');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetSegmentId: 999999,
        }),
        undefined
      );
    });

    it('passes large timestamps correctly', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: 9999999,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?t=9999999');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          targetTimestamp: 9999999,
        }),
        undefined
      );
    });
  });

  describe('Guard Clauses - TranscriptPanel Not Rendered', () => {
    it('does not render TranscriptPanel when video is loading', () => {
      vi.mocked(useVideoDetail).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isSuccess: false,
        status: "pending",
        isFetching: true,
        isPending: true,
        isRefetching: false,
        isLoadingError: false,
        isRefetchError: false,
        isPaused: false,
        isPlaceholderData: false,
        isStale: false,
        dataUpdatedAt: 0,
        errorUpdatedAt: 0,
        failureCount: 0,
        failureReason: null,
        errorUpdateCount: 0,
        fetchStatus: "fetching" as const,
        isFetched: false,
        isFetchedAfterMount: false,
        isInitialLoading: true,
        isEnabled: true,
        promise: new Promise(() => {}),
      } as ReturnType<typeof useVideoDetail>);

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en&seg=42&t=125');

      expect(screen.queryByTestId('transcript-panel')).not.toBeInTheDocument();
      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    });

    it('does not render TranscriptPanel when video fetch errors', () => {
      const rejectedPromise = Promise.reject({ message: 'Failed to fetch', status: 500 });
      // Catch the rejection to prevent unhandled rejection warnings
      rejectedPromise.catch(() => {});

      vi.mocked(useVideoDetail).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { message: 'Failed to fetch', status: 500 },
        refetch: vi.fn(),
        isSuccess: false,
        status: "error",
        isFetching: false,
        isPending: false,
        isRefetching: false,
        isLoadingError: true,
        isRefetchError: false,
        isPaused: false,
        isPlaceholderData: false,
        isStale: false,
        dataUpdatedAt: 0,
        errorUpdatedAt: Date.now(),
        failureCount: 1,
        failureReason: { message: 'Failed to fetch', status: 500 },
        errorUpdateCount: 1,
        fetchStatus: "idle" as const,
        isFetched: true,
        isFetchedAfterMount: false,
        isInitialLoading: false,
        isEnabled: true,
        promise: rejectedPromise,
      } as unknown as ReturnType<typeof useVideoDetail>);

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en&seg=42&t=125');

      expect(screen.queryByTestId('transcript-panel')).not.toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Could not load video.')).toBeInTheDocument();
    });

    it('does not render TranscriptPanel when video is not found', () => {
      vi.mocked(useVideoDetail).mockReturnValue({
        data: undefined, // No data
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isSuccess: true,
        status: "success",
        isFetching: false,
        isPending: false,
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
        fetchStatus: "idle" as const,
        isFetched: true,
        isFetchedAfterMount: true,
        isInitialLoading: false,
        isEnabled: true,
        promise: Promise.resolve(undefined),
      } as unknown as ReturnType<typeof useVideoDetail>);

      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: 'en',
        segmentId: 42,
        timestamp: 125,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123?lang=en&seg=42&t=125');

      expect(screen.queryByTestId('transcript-panel')).not.toBeInTheDocument();
      expect(screen.getByText('Video Not Found')).toBeInTheDocument();
    });
  });

  describe('TranscriptPanel Always Receives videoId', () => {
    it('passes videoId from route params to TranscriptPanel', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      renderVideoDetailPage('/videos/test-video-123');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'test-video-123',
        }),
        undefined
      );
    });

    it('passes different videoId for different routes', () => {
      vi.mocked(useDeepLinkParams).mockReturnValue({
        lang: null,
        segmentId: null,
        timestamp: null,
        clearDeepLinkParams: mockClearDeepLinkParams,
      });

      // Update mock video to match the new ID
      const newMockVideo = { ...mockVideo, video_id: 'another-video-456' };
      vi.mocked(useVideoDetail).mockReturnValue({
        data: newMockVideo,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isSuccess: true,
        status: "success",
        isFetching: false,
        isPending: false,
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
        fetchStatus: "idle" as const,
        isFetched: true,
        isFetchedAfterMount: true,
        isInitialLoading: false,
        isEnabled: true,
        promise: Promise.resolve(newMockVideo),
      } as ReturnType<typeof useVideoDetail>);

      renderVideoDetailPage('/videos/another-video-456');

      const mockTranscriptPanel = TranscriptPanel as ReturnType<typeof vi.fn>;
      expect(mockTranscriptPanel).toHaveBeenCalledWith(
        expect.objectContaining({
          videoId: 'another-video-456',
        }),
        undefined
      );
    });
  });
});
