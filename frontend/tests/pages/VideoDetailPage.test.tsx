/**
 * Tests for VideoDetailPage component.
 *
 * Covers:
 * - Loading state rendering
 * - Video data display with all metadata
 * - 404 error display when video not found
 * - Error state with retry functionality
 * - Back to Videos navigation link
 * - Watch on YouTube external link
 * - Tag display (hidden when no tags)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { VideoDetailPage } from '../../src/pages/VideoDetailPage';
import type { VideoDetail } from '../../src/types/video';

// Mock hooks
vi.mock('../../src/hooks/useVideoDetail');
vi.mock('../../src/components/transcript', () => ({
  TranscriptPanel: ({ videoId }: { videoId: string }) => (
    <div data-testid="transcript-panel">TranscriptPanel: {videoId}</div>
  ),
}));

import { useVideoDetail } from '../../src/hooks/useVideoDetail';

const mockUseVideoDetail = vi.mocked(useVideoDetail);

describe('VideoDetailPage', () => {
  const mockVideoData: VideoDetail = {
    video_id: 'dQw4w9WgXcQ',
    title: 'Test Video Title',
    description: 'This is a test video description.',
    channel_id: 'UC123456',
    channel_title: 'Test Channel',
    upload_date: '2024-01-15T10:30:00Z',
    duration: 245, // 4:05
    view_count: 1234567,
    like_count: 98765,
    comment_count: 4321,
    tags: ['test', 'video', 'example'],
    category_id: '22',
    default_language: 'en',
    made_for_kids: false,
    transcript_summary: {
      count: 2,
      languages: ['en', 'es'],
      has_manual: true,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading State', () => {
    it('should render loading state when data is being fetched', () => {
      mockUseVideoDetail.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      // LoadingState component should be rendered
      expect(screen.getByRole('status')).toBeInTheDocument();
    });
  });

  describe('Video Data Display', () => {
    beforeEach(() => {
      mockUseVideoDetail.mockReturnValue({
        data: mockVideoData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);
    });

    it('should render video title', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByRole('heading', { name: 'Test Video Title' })).toBeInTheDocument();
    });

    it('should render channel name', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });

    it('should render formatted view count', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('1.2M views')).toBeInTheDocument();
    });

    it('should render formatted like count', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('98.8K likes')).toBeInTheDocument();
    });

    it('should render formatted duration', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('4:05')).toBeInTheDocument();
    });

    it('should render description', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('This is a test video description.')).toBeInTheDocument();
    });

    it('should render tags as badges', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByText('test')).toBeInTheDocument();
      expect(screen.getByText('video')).toBeInTheDocument();
      expect(screen.getByText('example')).toBeInTheDocument();
    });

    it('should hide tags section when no tags present', () => {
      mockUseVideoDetail.mockReturnValue({
        data: { ...mockVideoData, tags: [] },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.queryByText('Tags')).not.toBeInTheDocument();
    });

    it('should render TranscriptPanel with correct videoId', () => {
      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByTestId('transcript-panel')).toHaveTextContent('TranscriptPanel: dQw4w9WgXcQ');
    });
  });

  describe('404 Error Display', () => {
    it('should render 404 state when video is null', () => {
      mockUseVideoDetail.mockReturnValue({
        data: null,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/invalid-id'],
        path: '/videos/:videoId',
      });

      expect(screen.getByRole('heading', { name: 'Video Not Found' })).toBeInTheDocument();
      expect(screen.getByText(/doesn't exist or has been removed/i)).toBeInTheDocument();
    });

    it('should render Back to Videos link in 404 state', () => {
      mockUseVideoDetail.mockReturnValue({
        data: null,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/invalid-id'],
        path: '/videos/:videoId',
      });

      const backLink = screen.getAllByRole('link', { name: /back to videos/i })[0];
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute('href', '/videos');
    });
  });

  describe('Error State', () => {
    it('should render error state when fetch fails', () => {
      mockUseVideoDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Could not load video.')).toBeInTheDocument();
    });

    it('should render Retry button in error state', () => {
      const mockRefetch = vi.fn();
      mockUseVideoDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      expect(retryButton).toBeInTheDocument();
    });

    it('should call refetch when Retry button is clicked', async () => {
      const mockRefetch = vi.fn();
      mockUseVideoDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      const { user } = renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1);
      });
    });

    it('should NOT render TranscriptPanel in error state', () => {
      mockUseVideoDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      expect(screen.queryByTestId('transcript-panel')).not.toBeInTheDocument();
    });
  });

  describe('Back to Videos Link', () => {
    it('should render Back to Videos link in header', () => {
      mockUseVideoDetail.mockReturnValue({
        data: mockVideoData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      const backLinks = screen.getAllByRole('link', { name: /back to videos/i });
      expect(backLinks.length).toBeGreaterThan(0);
      expect(backLinks[0]).toHaveAttribute('href', '/videos');
    });
  });

  describe('Watch on YouTube Link', () => {
    it('should render Watch on YouTube link', () => {
      mockUseVideoDetail.mockReturnValue({
        data: mockVideoData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<VideoDetailPage />, {
        initialEntries: ['/videos/dQw4w9WgXcQ'],
        path: '/videos/:videoId',
      });

      const youtubeLink = screen.getByRole('link', { name: /watch on youtube/i });
      expect(youtubeLink).toBeInTheDocument();
      expect(youtubeLink).toHaveAttribute('href', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
      expect(youtubeLink).toHaveAttribute('target', '_blank');
      expect(youtubeLink).toHaveAttribute('rel', 'noopener noreferrer');
    });
  });
});
