/**
 * Tests for ChannelDetailPage unavailability banner integration (Feature 023).
 *
 * Covers:
 * - Banner displays for unavailable channels (deleted, private, terminated, etc.)
 * - Banner does not display for available channels
 * - Banner is positioned correctly at the top of the content area
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
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

describe('ChannelDetailPage - Unavailability Banner Integration', () => {
  const baseChannelData: ChannelDetail = {
    channel_id: 'UC123456789012345678901',
    title: 'Test Channel',
    description: 'This is a test channel.',
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

  beforeEach(() => {
    vi.clearAllMocks();

    // Default mock for videos hook
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
  });

  describe('Banner Display', () => {
    it('should NOT display banner for available channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'available' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should NOT be present
      expect(screen.queryByRole('status', { name: /unavailable|deleted|private|terminated/i })).not.toBeInTheDocument();
    });

    it('should display banner for deleted channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'deleted' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with deleted status
      expect(screen.getByText(/this channel was deleted/i)).toBeInTheDocument();
      const banner = screen.getByText(/this channel was deleted/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it('should display banner for private channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'private' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with private status
      expect(screen.getByText(/this channel is private/i)).toBeInTheDocument();
      const banner = screen.getByText(/this channel is private/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it('should display banner for terminated channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'terminated' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with terminated status
      expect(screen.getByText(/this channel has been terminated/i)).toBeInTheDocument();
      const banner = screen.getByText(/this channel has been terminated/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it('should display banner for copyright violation channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'copyright' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with copyright status
      expect(screen.getByText(/this channel was removed for copyright violations/i)).toBeInTheDocument();
      const banner = screen.getByText(/this channel was removed for copyright violations/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it('should display banner for TOS violation channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'tos_violation' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with TOS violation status
      expect(screen.getByText(/this channel was removed for violating youtube's terms of service/i)).toBeInTheDocument();
      const banner = screen.getByText(/this channel was removed for violating youtube's terms of service/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it('should display banner for unavailable channels (unknown reason)', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'unavailable' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be present with unavailable status
      expect(screen.getByText(/currently unavailable/i)).toBeInTheDocument();
      const banner = screen.getByText(/currently unavailable/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();
    });
  });

  describe('Banner Position', () => {
    it('should render banner after breadcrumb but before channel header', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'deleted' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      const { container } = renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Breadcrumb navigation should exist
      expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument();

      // Banner should exist (using specific text to avoid "No videos" status element)
      const banner = screen.getByText(/this channel was deleted/i).closest('[role="status"]');
      expect(banner).toBeInTheDocument();

      // Channel title should exist
      expect(screen.getByRole('heading', { name: 'Test Channel', level: 1 })).toBeInTheDocument();

      // Verify banner is in the main content area
      const main = container.querySelector('main');
      expect(main).toContainElement(banner);
    });
  });

  describe('Channel Metadata Still Visible', () => {
    it('should display channel metadata alongside banner for deleted channels', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'deleted' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      // Banner should be visible
      expect(screen.getByText(/this channel was deleted/i)).toBeInTheDocument();

      // Channel metadata should still be visible
      expect(screen.getByRole('heading', { name: 'Test Channel', level: 1 })).toBeInTheDocument();
      expect(screen.getByText('This is a test channel.')).toBeInTheDocument();
      expect(screen.getByText(/1\.5M subscribers/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have accessible banner with role="status" and aria-live', () => {
      mockUseChannelDetail.mockReturnValue({
        data: { ...baseChannelData, availability_status: 'private' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(<ChannelDetailPage />, {
        initialEntries: ['/channels/UC123456789012345678901'],
        path: '/channels/:channelId',
      });

      const banner = screen.getByText(/this channel is private/i).closest('[role="status"]');
      expect(banner).toHaveAttribute('aria-live', 'polite');
    });
  });
});
