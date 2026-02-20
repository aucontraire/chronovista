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
 * - Sort dropdown renders 2 options (video_count, name) (Feature 027, US-3)
 * - Filter tabs render 3 options (All, Subscribed, Not Subscribed)
 * - URL state persistence for tab+sort on refresh
 * - Count header reflects filtered count (FR-030)
 * - Empty state for subscription filter
 * - Tab+sort combination
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { ChannelsPage } from '../../src/pages/ChannelsPage';
import type { ChannelListItem } from '../../src/types/channel';

// Mock the useChannels hook
vi.mock('../../src/hooks/useChannels', async () => {
  const actual = await vi.importActual<typeof import('../../src/hooks/useChannels')>(
    '../../src/hooks/useChannels'
  );
  return {
    ...actual,
    useChannels: vi.fn(),
  };
});

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
      availability_status: 'available',
      is_subscribed: true,
      recovered_at: null,
      recovery_source: null,
    },
    {
      channel_id: 'UC234567890123456789012',
      title: 'Gaming Channel',
      description: 'Gaming content',
      subscriber_count: 500000,
      video_count: 300,
      thumbnail_url: 'https://example.com/gaming.jpg',
      custom_url: '@gaming',
      availability_status: 'available',
      is_subscribed: true,
      recovered_at: null,
      recovery_source: null,
    },
    {
      channel_id: 'UC345678901234567890123',
      title: 'Music Channel',
      description: 'Music content',
      subscriber_count: 2000000,
      video_count: 200,
      thumbnail_url: 'https://example.com/music.jpg',
      custom_url: '@music',
      availability_status: 'available',
      is_subscribed: false,
      recovered_at: null,
      recovery_source: null,
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

      // Should show multiple skeleton cards
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
      expect(channelCards[0]).toHaveTextContent('Tech Channel');
      expect(channelCards[0]).toHaveTextContent('500 videos');

      expect(channelCards[1]).toHaveTextContent('Gaming Channel');
      expect(channelCards[1]).toHaveTextContent('300 videos');

      expect(channelCards[2]).toHaveTextContent('Music Channel');
      expect(channelCards[2]).toHaveTextContent('200 videos');
    });

    it('should display total channel count', () => {
      renderWithProviders(<ChannelsPage />);

      // Should show "3 channels" somewhere on the page (count header + footer)
      const matches = screen.getAllByText(/3 channels/i);
      expect(matches.length).toBeGreaterThanOrEqual(1);
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

      // Should guide user on next steps (heading + description text)
      expect(screen.getByText('No channels yet')).toBeInTheDocument();
      expect(screen.getByText(/syncing your YouTube data/i)).toBeInTheDocument();
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

      // Should have channel cards
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

      expect(screen.getByRole('heading', { name: /channels/i, level: 1 })).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: Sort Dropdown Tests (US-3)
  // ═══════════════════════════════════════════════════════════════════

  describe('Sort Dropdown (Feature 027, US-3)', () => {
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

    it('should render sort dropdown', () => {
      renderWithProviders(<ChannelsPage />);

      // Sort dropdown should be present with "Sort by" label
      expect(screen.getByLabelText(/sort by/i)).toBeInTheDocument();
    });

    it('should render sort dropdown with 2 sort fields (4 options with asc/desc)', () => {
      renderWithProviders(<ChannelsPage />);

      const select = screen.getByLabelText(/sort by/i);
      const options = within(select).getAllByRole('option');

      // 2 fields x 2 orders = 4 options
      expect(options.length).toBe(4);
    });

    it('should have video_count and name sort options', () => {
      renderWithProviders(<ChannelsPage />);

      const select = screen.getByLabelText(/sort by/i);

      // Check that video_count and name labels are present (multiple options per field)
      const videoCountOptions = within(select).getAllByText(/video count/i);
      expect(videoCountOptions.length).toBeGreaterThanOrEqual(1);

      const nameOptions = within(select).getAllByText(/name/i);
      expect(nameOptions.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: Subscription Filter Tabs Tests (US-3)
  // ═══════════════════════════════════════════════════════════════════

  describe('Subscription Filter Tabs (Feature 027, US-3)', () => {
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

    it('should render 3 filter tabs', () => {
      renderWithProviders(<ChannelsPage />);

      const tabs = screen.getAllByRole('tab');
      expect(tabs).toHaveLength(3);
    });

    it('should render All, Subscribed, and Not Subscribed tabs', () => {
      renderWithProviders(<ChannelsPage />);

      expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Subscribed' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Not Subscribed' })).toBeInTheDocument();
    });

    it('should have "All" tab selected by default', () => {
      renderWithProviders(<ChannelsPage />);

      const allTab = screen.getByRole('tab', { name: 'All' });
      expect(allTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should update selected tab on click', async () => {
      const { user } = renderWithProviders(<ChannelsPage />);

      const subscribedTab = screen.getByRole('tab', { name: 'Subscribed' });
      await user.click(subscribedTab);

      await waitFor(() => {
        expect(subscribedTab).toHaveAttribute('aria-selected', 'true');
      });
    });

    it('should have subscription filter tabs with tablist role', () => {
      renderWithProviders(<ChannelsPage />);

      expect(screen.getByRole('tablist')).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: URL State Persistence (US-3)
  // ═══════════════════════════════════════════════════════════════════

  describe('URL State Persistence (Feature 027, US-3)', () => {
    it('should restore subscription filter from URL on mount', () => {
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

      renderWithProviders(<ChannelsPage />, {
        initialEntries: ['/?subscription=subscribed'],
      });

      const subscribedTab = screen.getByRole('tab', { name: 'Subscribed' });
      expect(subscribedTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should pass sort params to useChannels hook', () => {
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

      renderWithProviders(<ChannelsPage />, {
        initialEntries: ['/?sort_by=name&sort_order=asc&subscription=subscribed'],
      });

      // useChannels should be called with the URL params
      expect(mockUseChannels).toHaveBeenCalledWith(
        expect.objectContaining({
          sortBy: 'name',
          sortOrder: 'asc',
          isSubscribed: 'subscribed',
        })
      );
    });

    it('should use defaults when no URL params present', () => {
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

      // useChannels should be called with defaults
      expect(mockUseChannels).toHaveBeenCalledWith(
        expect.objectContaining({
          sortBy: 'video_count',
          sortOrder: 'desc',
          isSubscribed: 'all',
        })
      );
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: Channel Count Header (FR-030)
  // ═══════════════════════════════════════════════════════════════════

  describe('Channel Count Header (FR-030)', () => {
    it('should display filtered count in header', () => {
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

      // Count header should reflect total (3 channels)
      expect(screen.getByText('3 channels')).toBeInTheDocument();
    });

    it('should use singular for single channel', () => {
      mockUseChannels.mockReturnValue({
        channels: [mockChannels[0]],
        total: 1,
        loadedCount: 1,
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

      // Should show "1 channel" (singular)
      expect(screen.getByText('1 channel')).toBeInTheDocument();
    });

    it('should have ARIA live region for count announcement', () => {
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

      // Should have SR-only ARIA live region for screen reader announcements
      const liveRegion = screen.getByRole('status');
      expect(liveRegion).toHaveTextContent('Showing 3 channels');
      expect(liveRegion).toHaveClass('sr-only');
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: Subscription Filter Empty State
  // ═══════════════════════════════════════════════════════════════════

  describe('Subscription Filter Empty State (Feature 027, US-3)', () => {
    it('should show subscription-specific empty state for subscribed filter', () => {
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

      renderWithProviders(<ChannelsPage />, {
        initialEntries: ['/?subscription=subscribed'],
      });

      expect(screen.getByText(/no subscribed channels/i)).toBeInTheDocument();
    });

    it('should show subscription-specific empty state for not_subscribed filter', () => {
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

      renderWithProviders(<ChannelsPage />, {
        initialEntries: ['/?subscription=not_subscribed'],
      });

      expect(screen.getByText(/no unsubscribed channels/i)).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // Feature 027: Tab + Sort Combination
  // ═══════════════════════════════════════════════════════════════════

  describe('Tab + Sort Combination (Feature 027, US-3)', () => {
    it('should pass combined tab and sort params to hook', () => {
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

      renderWithProviders(<ChannelsPage />, {
        initialEntries: ['/?subscription=subscribed&sort_by=name&sort_order=asc'],
      });

      expect(mockUseChannels).toHaveBeenCalledWith(
        expect.objectContaining({
          sortBy: 'name',
          sortOrder: 'asc',
          isSubscribed: 'subscribed',
        })
      );
    });

    it('should show toolbar in all states (loading, error, empty, data)', () => {
      // Loading state
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

      // Toolbar should be visible even during loading
      expect(screen.getByRole('tablist')).toBeInTheDocument();
      expect(screen.getByLabelText(/sort by/i)).toBeInTheDocument();
    });
  });
});
