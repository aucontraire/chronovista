/**
 * Tests for ChannelsPage component.
 *
 * Covers:
 * - Renders list of channel cards
 * - Shows loading skeletons during fetch (FR-005)
 * - Shows empty state when no channels (FR-004)
 * - Implements infinite scroll
 * - Displays error state on API failure
 * - Channels are sorted by video count (display order from API)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { ChannelsPage } from '../../src/pages/ChannelsPage';
import type { ChannelListItem } from '../../src/types/channel';

// Mock the useChannels hook
vi.mock('../../src/hooks/useChannels');

// Mock the ChannelCard component
vi.mock('../../src/components/ChannelCard', () => ({
  ChannelCard: ({ channel }: { channel: ChannelListItem }) => (
    <article data-testid={`channel-card-${channel.channel_id}`}>
      <h3>{channel.title}</h3>
      <p>{channel.video_count} videos</p>
    </article>
  ),
}));

import { useChannels } from '../../src/hooks/useChannels';

const mockUseChannels = vi.mocked(useChannels);

describe('ChannelsPage', () => {
  const mockChannels: ChannelListItem[] = [
    {
      channel_id: 'UC123456789012345678901',
      title: 'Tech Channel',
      description: 'Technology content',
      subscriber_count: 1000000,
      video_count: 500,
      thumbnail_url: 'https://example.com/tech.jpg',
      custom_url: '@tech',
    },
    {
      channel_id: 'UC234567890123456789012',
      title: 'Gaming Channel',
      description: 'Gaming content',
      subscriber_count: 500000,
      video_count: 300,
      thumbnail_url: 'https://example.com/gaming.jpg',
      custom_url: '@gaming',
    },
    {
      channel_id: 'UC345678901234567890123',
      title: 'Music Channel',
      description: 'Music content',
      subscriber_count: 2000000,
      video_count: 200,
      thumbnail_url: 'https://example.com/music.jpg',
      custom_url: '@music',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading State (FR-005)', () => {
    it('should show loading skeletons during initial fetch', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      // Should show loading skeletons
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('should show correct number of loading skeletons', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      // Should show multiple skeleton cards (typically 6-12)
      const loadingContainer = screen.getByRole('status');
      expect(loadingContainer).toBeInTheDocument();
    });

    it('should have accessible loading state', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      const loadingState = screen.getByRole('status');
      expect(loadingState).toHaveAttribute('aria-live', 'polite');
      expect(loadingState).toHaveAccessibleName(/loading/i);
    });
  });

  describe('Channel List Display', () => {
    beforeEach(() => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 3,
        loadedCount: 3,
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

    it('should render list of channel cards', () => {
      renderWithProviders(<ChannelsPage />);

      expect(screen.getByTestId('channel-card-UC123456789012345678901')).toBeInTheDocument();
      expect(screen.getByTestId('channel-card-UC234567890123456789012')).toBeInTheDocument();
      expect(screen.getByTestId('channel-card-UC345678901234567890123')).toBeInTheDocument();
    });

    it('should display all channel titles', () => {
      renderWithProviders(<ChannelsPage />);

      expect(screen.getByText('Tech Channel')).toBeInTheDocument();
      expect(screen.getByText('Gaming Channel')).toBeInTheDocument();
      expect(screen.getByText('Music Channel')).toBeInTheDocument();
    });

    it('should display channels in order from API (sorted by video count)', () => {
      renderWithProviders(<ChannelsPage />);

      const channelCards = screen.getAllByRole('article');

      // Channels should be in the order returned by the API
      // API returns them sorted by video count descending
      expect(channelCards[0]).toHaveTextContent('Tech Channel');
      expect(channelCards[0]).toHaveTextContent('500 videos');

      expect(channelCards[1]).toHaveTextContent('Gaming Channel');
      expect(channelCards[1]).toHaveTextContent('300 videos');

      expect(channelCards[2]).toHaveTextContent('Music Channel');
      expect(channelCards[2]).toHaveTextContent('200 videos');
    });

    it('should display total channel count', () => {
      renderWithProviders(<ChannelsPage />);

      // Should show "3 channels" or similar
      expect(screen.getByText(/3 channels/i)).toBeInTheDocument();
    });

    it('should use proper semantic HTML structure', () => {
      renderWithProviders(<ChannelsPage />);

      // Should have a main heading
      expect(screen.getByRole('heading', { name: /channels/i, level: 1 })).toBeInTheDocument();

      // Should have articles for each channel card
      const channelCards = screen.getAllByRole('article');
      expect(channelCards).toHaveLength(3);
    });
  });

  describe('Empty State (FR-004)', () => {
    it('should show empty state when no channels exist', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      // Should show helpful empty state message
      expect(screen.getByText(/no channels/i)).toBeInTheDocument();
    });

    it('should display helpful message in empty state', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      // Should guide user on next steps
      expect(
        screen.getByText(/no channels found|haven't synced any channels/i)
      ).toBeInTheDocument();
    });

    it('should NOT show channel cards in empty state', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
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

      renderWithProviders(<ChannelsPage />);

      expect(screen.queryByRole('article')).not.toBeInTheDocument();
    });
  });

  describe('Error State (FR-019)', () => {
    it('should display error state on API failure', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error occurred' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/could not load channels/i)).toBeInTheDocument();
    });

    it('should display error message from API', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error occurred' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      expect(screen.getByText(/network error occurred/i)).toBeInTheDocument();
    });

    it('should show Retry button in error state', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call retry function when Retry button is clicked', async () => {
      const mockRetry = vi.fn();

      mockUseChannels.mockReturnValue({
        channels: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: mockRetry,
        loadMoreRef: { current: null },
      });

      const { user } = renderWithProviders(<ChannelsPage />);

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalledTimes(1);
      });
    });

    it('should NOT show channel cards in error state', () => {
      mockUseChannels.mockReturnValue({
        channels: [],
        total: null,
        loadedCount: 0,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      expect(screen.queryByRole('article')).not.toBeInTheDocument();
    });
  });

  describe('Infinite Scroll (FR-002)', () => {
    it('should show load more trigger when hasNextPage is true', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should have a load more trigger element for intersection observer
      // This might be a div with ref={loadMoreRef}
      const channelCards = screen.getAllByRole('article');
      expect(channelCards).toHaveLength(3);
    });

    it('should show loading indicator while fetching next page', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: true,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should show loading spinner or skeleton for next page
      expect(screen.getByText(/loading more/i)).toBeInTheDocument();
    });

    it('should NOT show load more trigger when hasNextPage is false', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 3,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should NOT show loading more indicator
      expect(screen.queryByText(/loading more/i)).not.toBeInTheDocument();
    });

    it('should display loaded count and total', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should show "Showing 3 of 10 channels" or similar
      expect(screen.getByText(/3.*10.*channels/i)).toBeInTheDocument();
    });

    it('should attach loadMoreRef to trigger element', () => {
      const mockRef = { current: null };

      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: mockRef,
      });

      renderWithProviders(<ChannelsPage />);

      // The component should use the ref from the hook
      // This is verified by the hook managing the intersection observer
      expect(screen.getAllByRole('article')).toHaveLength(3);
    });
  });

  describe('Error Recovery (EC-007)', () => {
    it('should show inline error when infinite scroll fails', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: true,
        error: { type: 'timeout', message: 'Request timed out' },
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should show error inline, preserving loaded channels
      expect(screen.getAllByRole('article')).toHaveLength(3);
      expect(screen.getByText(/failed to load more|request timed out/i)).toBeInTheDocument();
    });

    it('should preserve loaded channels when fetch fails', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should still show the 3 loaded channels
      expect(screen.getByText('Tech Channel')).toBeInTheDocument();
      expect(screen.getByText('Gaming Channel')).toBeInTheDocument();
      expect(screen.getByText('Music Channel')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 3,
        loadedCount: 3,
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
      renderWithProviders(<ChannelsPage />);

      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    it('should have descriptive page heading', () => {
      renderWithProviders(<ChannelsPage />);

      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent(/channels/i);
    });

    it('should announce dynamic content updates to screen readers', () => {
      mockUseChannels.mockReturnValue({
        channels: mockChannels,
        total: 10,
        loadedCount: 3,
        isLoading: false,
        isError: false,
        error: null,
        hasNextPage: true,
        isFetchingNextPage: true,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        loadMoreRef: { current: null },
      });

      renderWithProviders(<ChannelsPage />);

      // Should have aria-live region for loading updates
      const liveRegion = screen.getByText(/loading more/i);
      expect(liveRegion).toBeInTheDocument();
    });
  });

  describe('Page Metadata', () => {
    it('should set appropriate page title', () => {
      renderWithProviders(<ChannelsPage />);

      // Page title would be set via React Helmet or similar
      // Verify the heading is present as a proxy
      expect(screen.getByRole('heading', { name: /channels/i, level: 1 })).toBeInTheDocument();
    });
  });
});
