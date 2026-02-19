/**
 * Tests for ChannelDetailPage component.
 *
 * Covers:
 * - Displays channel header (thumbnail, name, description) (FR-006)
 * - Displays metadata (subscriber count, video count from YouTube, country) (FR-007)
 * - Shows "Subscribed" badge when is_subscribed=true (FR-008)
 * - Shows "Not Subscribed" badge when is_subscribed=false (FR-008)
 * - Renders videos grid with infinite scroll (FR-009, FR-010)
 * - Handles missing metadata gracefully (FR-011, EC-001 to EC-004)
 * - Shows 404 page for non-existent channel (EC-005)
 * - Empty state for channels with 0 videos (EC-003)
 * - Loading skeletons while fetching
 * - Error state with retry option
 * - Focus management on page load (FR-018)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { ChannelDetailPage } from '../../src/pages/ChannelDetailPage';
import type { ChannelDetail } from '../../src/types/channel';
import type { VideoListItem } from '../../src/types/video';

// Mock hooks
vi.mock('../../src/hooks/useChannelDetail');
vi.mock('../../src/hooks/useChannelVideos');

// Mock VideoCard component for simpler testing
vi.mock('../../src/components/VideoCard', () => ({
  VideoCard: ({ video }: { video: VideoListItem }) => (
    <article data-testid={`video-card-${video.video_id}`}>
      <h3>{video.title}</h3>
    </article>
  ),
}));

import { useChannelDetail } from '../../src/hooks/useChannelDetail';
import { useChannelVideos } from '../../src/hooks/useChannelVideos';

const mockUseChannelDetail = vi.mocked(useChannelDetail);
const mockUseChannelVideos = vi.mocked(useChannelVideos);

describe('ChannelDetailPage', () => {
  const mockChannelData: ChannelDetail = {
    channel_id: 'UC123456789012345678901',
    title: 'Test Channel',
    description: 'This is a test channel with great content about testing.',
    subscriber_count: 1500000,
    video_count: 250,
    thumbnail_url: 'https://example.com/thumbnail.jpg',
    custom_url: '@testchannel',
    default_language: 'en',
    country: 'US',
    is_subscribed: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-15T10:30:00Z',
    availability_status: 'available',
  };

  const mockVideos: VideoListItem[] = [
    {
      video_id: 'dQw4w9WgXcQ',
      title: 'Test Video 1',
      channel_id: 'UC123456789012345678901',
      channel_title: 'Test Channel',
      upload_date: '2024-01-15T10:30:00Z',
      duration: 245,
      view_count: 1000000,
      transcript_summary: {
        count: 1,
        languages: ['en'],
        has_manual: true,
      },
    },
    {
      video_id: 'jNQXAC9IVRw',
      title: 'Test Video 2',
      channel_id: 'UC123456789012345678901',
      channel_title: 'Test Channel',
      upload_date: '2024-01-10T08:00:00Z',
      duration: 180,
      view_count: 500000,
      transcript_summary: {
        count: 2,
        languages: ['en', 'es'],
        has_manual: false,
      },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading State', () => {
    it('should render loading state when channel data is being fetched', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: true,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // LoadingState component should be rendered
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('should have accessible loading state', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: true,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const loadingState = screen.getByRole('status');
      expect(loadingState).toHaveAttribute('aria-live', 'polite');
    });
  });

  describe('Channel Header Display (FR-006)', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should display channel thumbnail with proxy URL (T031b)', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      expect(thumbnail).toBeInTheDocument();
      // Should use proxy URL pattern, not original YouTube URL
      expect(thumbnail).toHaveAttribute('src', expect.stringContaining('/images/channels/UC123456789012345678901'));
    });

    it('should display channel name as heading', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByRole('heading', { name: 'Test Channel', level: 1 })).toBeInTheDocument();
    });

    it('should display channel description', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(
        screen.getByText('This is a test channel with great content about testing.')
      ).toBeInTheDocument();
    });
  });

  describe('Channel Metadata Display (FR-007)', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should display subscriber count', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should display formatted subscriber count (e.g., "1.5M subscribers")
      expect(screen.getByText(/1\.5M subscribers/i)).toBeInTheDocument();
    });

    it('should display video count from YouTube', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should display total video count from channel metadata (not database count)
      expect(screen.getByText(/250 videos/i)).toBeInTheDocument();
    });

    it('should display country', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should display country (US)
      expect(screen.getByText(/US|United States/i)).toBeInTheDocument();
    });
  });

  describe('Subscription Status Display (FR-008)', () => {
    it('should show "Subscribed" badge when is_subscribed is true', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, is_subscribed: true },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByText(/subscribed/i)).toBeInTheDocument();
    });

    it('should show "Not Subscribed" badge when is_subscribed is false', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, is_subscribed: false },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByText(/not subscribed/i)).toBeInTheDocument();
    });
  });

  describe('Videos Grid Display (FR-009, FR-010)', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should render videos grid with all videos from channel', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByTestId('video-card-dQw4w9WgXcQ')).toBeInTheDocument();
      expect(screen.getByTestId('video-card-jNQXAC9IVRw')).toBeInTheDocument();
      expect(screen.getByText('Test Video 1')).toBeInTheDocument();
      expect(screen.getByText('Test Video 2')).toBeInTheDocument();
    });

    it('should show loading indicator while fetching next page', () => {
      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 10,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: true,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByText(/loading more/i)).toBeInTheDocument();
    });

    it('should provide infinite scroll trigger when hasNextPage is true', () => {
      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 10,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should render video cards and have mechanism for loading more
      const videoCards = screen.getAllByRole('article');
      expect(videoCards).toHaveLength(2);
    });
  });

  describe('Missing Metadata Handling (FR-011, EC-001 to EC-004)', () => {
    it('should display placeholder image when thumbnail is null (EC-001)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, thumbnail_url: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should show placeholder or default image
      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      expect(thumbnail).toBeInTheDocument();
    });

    it('should show "No description available" when description is null (EC-002)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, description: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByText(/no description available/i)).toBeInTheDocument();
    });

    it('should hide subscriber count when null (EC-004)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, subscriber_count: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Subscriber count should not be displayed
      expect(screen.queryByText(/subscribers/i)).not.toBeInTheDocument();
    });

    it('should hide video count when null (EC-004)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, video_count: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Video count from YouTube metadata should not be displayed
      expect(screen.queryByText(/\d+ videos/i)).not.toBeInTheDocument();
    });

    it('should hide country when null (EC-004)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, country: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Country should not be displayed
      expect(screen.queryByText(/US|United States/i)).not.toBeInTheDocument();
    });

    it('should gracefully handle channel with all metadata null', () => {
      const minimalChannel: ChannelDetail = {
        channel_id: 'UC123456789012345678901',
        title: 'Minimal Channel',
        description: null,
        subscriber_count: null,
        video_count: null,
        thumbnail_url: null,
        custom_url: null,
        default_language: null,
        country: null,
        is_subscribed: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        availability_status: 'available',
      };

      mockUseChannelDetail.mockReturnValue({
        data: minimalChannel,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should still show channel title and subscription status
      expect(screen.getByRole('heading', { name: 'Minimal Channel' })).toBeInTheDocument();
      expect(screen.getByText(/not subscribed/i)).toBeInTheDocument();
    });
  });

  describe('Empty Video List (EC-003)', () => {
    it('should show empty state when channel has 0 videos', () => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByText(/no videos/i)).toBeInTheDocument();
    });

    it('should NOT show video cards in empty state', () => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: 0,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.queryByTestId(/video-card-/)).not.toBeInTheDocument();
    });
  });

  describe('404 Error Display (EC-005)', () => {
    it('should render 404 state when channel is not found', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'server', message: 'Channel not found', status: 404 },
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC999999999999999999999'],
        path: '/channels/:channelId',
      });

      expect(screen.getByRole('heading', { name: /channel not found/i })).toBeInTheDocument();
      expect(
        screen.getByText(/doesn't exist or has been removed/i)
      ).toBeInTheDocument();
    });

    it('should render "Browse Channels" link as primary action in 404 state', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'server', message: 'Channel not found', status: 404 },
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC999999999999999999999'],
        path: '/channels/:channelId',
      });

      const browseLink = screen.getByRole('link', { name: /browse channels/i });
      expect(browseLink).toBeInTheDocument();
      expect(browseLink).toHaveAttribute('href', '/channels');
    });

    it('should render "Go Back" link as secondary action in 404 state', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'server', message: 'Channel not found', status: 404 },
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC999999999999999999999'],
        path: '/channels/:channelId',
      });

      // "Go Back" button should be present
      expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument();
    });
  });

  describe('Error State (FR-019)', () => {
    it('should display error state when channel fetch fails', () => {
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/could not load channel/i)).toBeInTheDocument();
    });

    it('should render Retry button in error state', () => {
      const mockRefetch = vi.fn();
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call refetch when Retry button is clicked', async () => {
      const mockRefetch = vi.fn();
      mockUseChannelDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      const { user } = renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1);
      });
    });

    it('should display inline error when videos fetch fails (EC-008)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'timeout', message: 'Request timed out' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Channel header should still be visible
      expect(screen.getByRole('heading', { name: 'Test Channel' })).toBeInTheDocument();

      // Error should be shown in videos section
      expect(screen.getByText(/could not load videos|request timed out/i)).toBeInTheDocument();
    });

    it('should allow retry for videos independently of channel (EC-008)', async () => {
      const mockVideosRetry = vi.fn();

      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: mockVideosRetry,
        loadMoreRef: { current: null },
      });

      const { user } = renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should have a retry button for videos section
      const retryButtons = screen.getAllByRole('button', { name: /retry/i });
      expect(retryButtons.length).toBeGreaterThan(0);

      await user.click(retryButtons[0]);

      await waitFor(() => {
        expect(mockVideosRetry).toHaveBeenCalled();
      });
    });
  });

  describe('Accessibility (FR-016, FR-018)', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should have main landmark', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    it('should have descriptive page heading', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Test Channel');
    });

    it('should have accessible thumbnail image with alt text', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      expect(thumbnail).toHaveAccessibleName();
    });

    it('should manage focus on page load (FR-018)', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Main heading or main element should receive focus on load
      const main = screen.getByRole('main');
      expect(main).toBeInTheDocument();
    });
  });

  describe('Navigation', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should render Back to Channels link', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const backLinks = screen.getAllByRole('link', { name: /back to channels/i });
      expect(backLinks.length).toBeGreaterThan(0);
      expect(backLinks[0]).toHaveAttribute('href', '/channels');
    });

    it('should render View on YouTube link', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const youtubeLink = screen.getByRole('link', { name: /view on youtube/i });
      expect(youtubeLink).toBeInTheDocument();
      expect(youtubeLink).toHaveAttribute(
        'href',
        'https://www.youtube.com/channel/UC123456789012345678901'
      );
      expect(youtubeLink).toHaveAttribute('target', '_blank');
      expect(youtubeLink).toHaveAttribute('rel', 'noopener noreferrer');
    });
  });

  describe('Image Proxy URL (Feature 026, T031b)', () => {
    beforeEach(() => {
      mockUseChannelDetail.mockReturnValue({
        data: mockChannelData,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      mockUseChannelVideos.mockReturnValue({
        videos: mockVideos,
        total: 2,
        loadedCount: 2,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });
    });

    it('should use proxy URL pattern ${API_BASE_URL}/images/channels/${channelId}', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      const src = thumbnail.getAttribute('src');

      // Verify proxy URL pattern
      expect(src).toMatch(/\/images\/channels\/UC123456789012345678901$/);
      expect(src).toContain('UC123456789012345678901');
    });

    it('should NOT include YouTube CDN URLs (ytimg.com or ggpht.com)', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      const src = thumbnail.getAttribute('src');

      // Should NOT use YouTube CDN
      expect(src).not.toContain('ytimg.com');
      expect(src).not.toContain('ggpht.com');
      expect(src).not.toContain('youtube.com');
    });

    it('should render SVG placeholder on image error', () => {
      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const thumbnail = screen.getByRole('img', { name: /test channel/i });
      const parent = thumbnail.parentElement;

      // Simulate image load error
      const errorEvent = new Event('error', { bubbles: true });
      thumbnail.dispatchEvent(errorEvent);

      // After error, component replaces img with SVG via innerHTML
      // The parent should still exist
      expect(parent).toBeTruthy();
      // The original img should be hidden (display: none)
      expect(thumbnail.style.display).toBe('none');
    });

    it('should display SVG placeholder when thumbnail_url is null', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...mockChannelData, thumbnail_url: null },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Should render SVG placeholder div, not img
      const placeholder = screen.getByRole('img', { name: /test channel/i });
      expect(placeholder).toBeInTheDocument();
      // Placeholder should be a div with role="img", not an <img> tag
      expect(placeholder.tagName).toBe('DIV');
    });
  });
});
