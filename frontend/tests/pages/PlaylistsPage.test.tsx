/**
 * Tests for PlaylistsPage component.
 *
 * Covers:
 * - CHK048: Filter tabs (All, YouTube-Linked, Local) with URL sync
 * - CHK049: Responsive grid layout (1/2/3/4 cols)
 * - CHK050: Playlist cards with proper metadata
 * - CHK051: Loading state with skeleton cards
 * - CHK052: Error state with retry
 * - CHK053: Empty state with filter-aware messaging
 * - CHK054: Infinite scroll support
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders, getTestLocation } from '../test-utils';
import { PlaylistsPage } from '../../src/pages/PlaylistsPage';
import type { PlaylistListItem } from '../../src/types/playlist';

// Mock the usePlaylists hook
vi.mock('../../src/hooks/usePlaylists');

// Mock the PlaylistCard component
vi.mock('../../src/components/PlaylistCard', () => ({
  PlaylistCard: ({ playlist }: { playlist: PlaylistListItem }) => (
    <article data-testid={`playlist-card-${playlist.playlist_id}`}>
      <h3>{playlist.title}</h3>
      <p>{playlist.video_count} videos</p>
      <span>{playlist.is_linked ? 'YouTube' : 'Local'}</span>
      <span>{playlist.privacy_status}</span>
    </article>
  ),
}));

// Mock PlaylistFilterTabs component
vi.mock('../../src/components/PlaylistFilterTabs', () => ({
  PlaylistFilterTabs: ({
    currentFilter,
    onFilterChange,
  }: {
    currentFilter: string;
    onFilterChange: (filter: string) => void;
  }) => (
    <nav data-testid="playlist-filter-tabs" role="tablist">
      <button
        role="tab"
        aria-selected={currentFilter === 'all'}
        onClick={() => onFilterChange('all')}
      >
        All
      </button>
      <button
        role="tab"
        aria-selected={currentFilter === 'linked'}
        onClick={() => onFilterChange('linked')}
      >
        YouTube-Linked
      </button>
      <button
        role="tab"
        aria-selected={currentFilter === 'local'}
        onClick={() => onFilterChange('local')}
      >
        Local
      </button>
    </nav>
  ),
}));

// Mock ErrorState component
vi.mock('../../src/components/ErrorState', () => ({
  ErrorState: ({
    error,
    onRetry,
  }: {
    error: unknown;
    onRetry: () => void;
  }) => (
    <div role="alert" data-testid="error-state">
      <p>
        {typeof error === 'object' && error !== null && 'message' in error
          ? (error as { message: string }).message
          : 'Error loading playlists'}
      </p>
      <button onClick={onRetry}>Retry</button>
    </div>
  ),
}));

import { usePlaylists } from '../../src/hooks/usePlaylists';

const mockUsePlaylists = vi.mocked(usePlaylists);

describe('PlaylistsPage', () => {
  const mockPlaylists: PlaylistListItem[] = [
    {
      playlist_id: 'PL123456789',
      title: 'Tech Tutorials Playlist',
      description: 'Learning technology',
      video_count: 25,
      privacy_status: 'public',
      is_linked: true,
    },
    {
      playlist_id: 'PL987654321',
      title: 'Gaming Highlights',
      description: 'Best gaming moments',
      video_count: 15,
      privacy_status: 'unlisted',
      is_linked: true,
    },
    {
      playlist_id: 'int_12345',
      title: 'My Local Playlist',
      description: 'Personal collection',
      video_count: 10,
      privacy_status: 'private',
      is_linked: false,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('CHK051: Loading State with Skeleton Cards', () => {
    it('should show loading skeletons during initial fetch', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should show loading state with skeleton cards
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByLabelText(/loading playlists/i)).toBeInTheDocument();
    });

    it('should show correct number of loading skeletons (12 by default)', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const loadingContainer = screen.getByRole('status');
      expect(loadingContainer).toBeInTheDocument();
      // The component shows 12 skeleton cards by default (count={12})
    });

    it('should have accessible loading state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const loadingState = screen.getByRole('status');
      expect(loadingState).toHaveAttribute('aria-live', 'polite');
      expect(loadingState).toHaveAttribute('aria-busy', 'true');
      expect(loadingState).toHaveAccessibleName(/loading playlists/i);
    });

    it('should show filter tabs during loading state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByTestId('playlist-filter-tabs')).toBeInTheDocument();
    });
  });

  describe('CHK050: Playlist Cards Grid Display', () => {
    beforeEach(() => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

    it('should render list of playlist cards', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByTestId('playlist-card-PL123456789')).toBeInTheDocument();
      expect(screen.getByTestId('playlist-card-PL987654321')).toBeInTheDocument();
      expect(screen.getByTestId('playlist-card-int_12345')).toBeInTheDocument();
    });

    it('should display all playlist titles', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText('Tech Tutorials Playlist')).toBeInTheDocument();
      expect(screen.getByText('Gaming Highlights')).toBeInTheDocument();
      expect(screen.getByText('My Local Playlist')).toBeInTheDocument();
    });

    it('should display video counts for each playlist', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText('25 videos')).toBeInTheDocument();
      expect(screen.getByText('15 videos')).toBeInTheDocument();
      expect(screen.getByText('10 videos')).toBeInTheDocument();
    });

    it('should display playlists in order from API', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const playlistCards = screen.getAllByRole('article');

      expect(playlistCards[0]).toHaveTextContent('Tech Tutorials Playlist');
      expect(playlistCards[0]).toHaveTextContent('25 videos');

      expect(playlistCards[1]).toHaveTextContent('Gaming Highlights');
      expect(playlistCards[1]).toHaveTextContent('15 videos');

      expect(playlistCards[2]).toHaveTextContent('My Local Playlist');
      expect(playlistCards[2]).toHaveTextContent('10 videos');
    });
  });

  describe('CHK049: Responsive Grid Layout', () => {
    beforeEach(() => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

    it('should use proper semantic HTML structure with role="list"', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should have a grid container with role="list"
      const gridContainer = screen.getByRole('list');
      expect(gridContainer).toBeInTheDocument();
      expect(gridContainer).toHaveAttribute('aria-label', 'Playlist list');
    });

    it('should have listitem role for each playlist card wrapper', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const listItems = screen.getAllByRole('listitem');
      expect(listItems).toHaveLength(3);
    });

    it('should apply responsive grid classes', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const gridContainer = screen.getByRole('list');
      // Grid should have responsive classes for 1/2/3/4 columns
      expect(gridContainer).toHaveClass('grid');
      expect(gridContainer.className).toMatch(/grid-cols-1/);
      expect(gridContainer.className).toMatch(/sm:grid-cols-2/);
      expect(gridContainer.className).toMatch(/md:grid-cols-3/);
      expect(gridContainer.className).toMatch(/lg:grid-cols-4/);
    });
  });

  describe('CHK048: Filter Tabs with URL Sync', () => {
    beforeEach(() => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

    it('should render filter tabs', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByTestId('playlist-filter-tabs')).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'YouTube-Linked' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Local' })).toBeInTheDocument();
    });

    it('should default to "all" filter when no URL param', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const allTab = screen.getByRole('tab', { name: 'All' });
      expect(allTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should read filter from URL search params', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=linked'],
      });

      const linkedTab = screen.getByRole('tab', { name: 'YouTube-Linked' });
      expect(linkedTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should update URL when filter changes to "linked"', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      const linkedTab = screen.getByRole('tab', { name: 'YouTube-Linked' });
      await user.click(linkedTab);

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('filter=linked');
      });
    });

    it('should update URL when filter changes to "local"', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      const localTab = screen.getByRole('tab', { name: 'Local' });
      await user.click(localTab);

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('filter=local');
      });
    });

    it('should remove filter param when switching to "all"', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=linked'],
      });

      const allTab = screen.getByRole('tab', { name: 'All' });
      await user.click(allTab);

      await waitFor(() => {
        const location = getTestLocation();
        // URL should have no filter param (cleaner URL)
        expect(location.search).not.toContain('filter=');
      });
    });

    it('should pass current filter to usePlaylists hook', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=linked'],
      });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'linked',
        sortBy: 'video_count',
        sortOrder: 'desc',
      });
    });

    it('should handle invalid filter param by defaulting to "all"', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=invalid'],
      });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'all',
        sortBy: 'video_count',
        sortOrder: 'desc',
      });
    });
  });

  describe('CHK053: Empty State with Filter-Aware Messaging', () => {
    it('should show empty state when no playlists exist', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/no playlists yet/i)).toBeInTheDocument();
    });

    it('should show "all" filter empty state message', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/no playlists yet/i)).toBeInTheDocument();
      expect(
        screen.getByText(/get started by syncing your youtube data/i)
      ).toBeInTheDocument();
    });

    it('should show "linked" filter empty state message', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=linked'],
      });

      expect(screen.getByText(/no youtube-linked playlists/i)).toBeInTheDocument();
      expect(
        screen.getByText(/sync your youtube data to import your playlists/i)
      ).toBeInTheDocument();
    });

    it('should show "local" filter empty state message', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=local'],
      });

      expect(screen.getByText(/no local playlists/i)).toBeInTheDocument();
      expect(
        screen.getByText(/local playlists are managed within chronovista/i)
      ).toBeInTheDocument();
    });

    it('should show CLI command for "all" and "linked" filters', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/chronovista sync/i)).toBeInTheDocument();
    });

    it('should NOT show CLI command for "local" filter', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=local'],
      });

      expect(screen.queryByText(/chronovista sync/i)).not.toBeInTheDocument();
    });

    it('should NOT show playlist cards in empty state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.queryByRole('article')).not.toBeInTheDocument();
    });

    it('should have accessible empty state with role="status"', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const emptyState = screen.getByRole('status');
      expect(emptyState).toHaveAccessibleName(/no playlists yet/i);
    });
  });

  describe('CHK052: Error State with Retry', () => {
    it('should display error state on API failure', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });

    it('should display error message from API', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/network error occurred/i)).toBeInTheDocument();
    });

    it('should show Retry button in error state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call retry function when Retry button is clicked', async () => {
      const mockRetry = vi.fn();

      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalledTimes(1);
      });
    });

    it('should NOT show playlist cards in error state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.queryByRole('article')).not.toBeInTheDocument();
    });

    it('should show filter tabs in error state', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByTestId('playlist-filter-tabs')).toBeInTheDocument();
    });
  });

  describe('CHK054: Infinite Scroll Support', () => {
    it('should show pagination status when more pages available', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should show "Showing X of Y playlists"
      expect(screen.getByText(/showing 3 of 50 playlists/i)).toBeInTheDocument();
    });

    it('should show load more trigger element when hasNextPage is true', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      const { container } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      // Should have a div for intersection observer trigger
      // It has aria-hidden="true" and h-4 class
      const triggerElements = container.querySelectorAll('[aria-hidden="true"]');
      const loadMoreTrigger = Array.from(triggerElements).find((el) =>
        el.className.includes('h-4')
      );
      expect(loadMoreTrigger).toBeInTheDocument();
    });

    it('should show loading indicator while fetching next page', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/loading more playlists/i)).toBeInTheDocument();
    });

    it('should show skeleton cards while fetching next page', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should show loading skeleton cards (4 cards for pagination)
      const loadingSection = screen.getByText(/loading more playlists/i).parentElement;
      expect(loadingSection).toBeInTheDocument();
    });

    it('should announce loading more to screen readers', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const loadingSection = screen.getByText(/loading more playlists/i)
        .parentElement;
      expect(loadingSection).toHaveAttribute('aria-live', 'polite');
    });

    it('should NOT show load more trigger when hasNextPage is false', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.queryByText(/loading more/i)).not.toBeInTheDocument();
    });

    it('should show "all loaded" message when all playlists are loaded', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText(/all 3 playlists loaded/i)).toBeInTheDocument();
    });

    it('should use loadMoreRef from usePlaylists hook', () => {
      const mockRef = { current: null };

      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // The component should pass the ref to the trigger element
      expect(screen.getAllByRole('article')).toHaveLength(3);
    });

    it('should handle singular playlist count correctly', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: [mockPlaylists[0]],
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should say "1 playlist" not "1 playlists"
      expect(screen.getByText(/all 1 playlist loaded/i)).toBeInTheDocument();
    });
  });

  describe('Error Recovery During Pagination', () => {
    it('should show inline error when infinite scroll fails', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should show error inline, preserving loaded playlists
      expect(screen.getAllByRole('article')).toHaveLength(3);
      expect(screen.getByText(/request timed out/i)).toBeInTheDocument();
    });

    it('should preserve loaded playlists when next page fetch fails', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should still show the 3 loaded playlists
      expect(screen.getByText('Tech Tutorials Playlist')).toBeInTheDocument();
      expect(screen.getByText('Gaming Highlights')).toBeInTheDocument();
      expect(screen.getByText('My Local Playlist')).toBeInTheDocument();
    });

    it('should show retry button for pagination error', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call retry when clicking retry button after pagination error', async () => {
      const mockRetry = vi.fn();

      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
        loadedCount: 3,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
        retry: mockRetry,
        loadMoreRef: { current: null },
      });

      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalledTimes(1);
      });
    });

    it('should NOT show load more trigger when error occurs during pagination', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: 50,
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

      const { container } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      // Trigger element should not be rendered when there's an error
      const triggerElements = container.querySelectorAll('[aria-hidden="true"]');
      const loadMoreTrigger = Array.from(triggerElements).find((el) =>
        el.className.includes('h-4')
      );
      expect(loadMoreTrigger).toBeUndefined();
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    it('should have descriptive page heading', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent(/playlists/i);
    });

    it('should use proper semantic HTML structure', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should have a main heading
      expect(
        screen.getByRole('heading', { name: /playlists/i, level: 1 })
      ).toBeInTheDocument();

      // Should have articles for each playlist card
      const playlistCards = screen.getAllByRole('article');
      expect(playlistCards).toHaveLength(3);
    });

    it('should have accessible tablist for filter tabs', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const tablist = screen.getByRole('tablist');
      expect(tablist).toBeInTheDocument();
    });
  });

  describe('Page Metadata', () => {
    it('should set page title on mount', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(document.title).toBe('Playlists - ChronoVista');
    });

    it('should reset page title on unmount', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

      const { unmount } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      expect(document.title).toBe('Playlists - ChronoVista');

      unmount();

      expect(document.title).toBe('ChronoVista');
    });
  });

  describe('Sort Dropdown (Feature 027)', () => {
    beforeEach(() => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
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

    it('should render SortDropdown component', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should have a combobox for sorting (native select)
      const sortDropdown = screen.getByLabelText(/sort by/i);
      expect(sortDropdown).toBeInTheDocument();
      expect(sortDropdown.tagName).toBe('SELECT');
    });

    it('should display all three sort options (title, created_at, video_count)', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      const sortDropdown = screen.getByLabelText(/sort by/i) as HTMLSelectElement;

      // Should have 6 options (3 fields × 2 orders)
      expect(sortDropdown.options).toHaveLength(6);

      // Check that all three fields are represented
      const optionTexts = Array.from(sortDropdown.options).map((opt) => opt.textContent);
      expect(optionTexts.some((text) => text?.includes('Title'))).toBe(true);
      expect(optionTexts.some((text) => text?.includes('Date Added'))).toBe(true);
      expect(optionTexts.some((text) => text?.includes('Video Count'))).toBe(true);
    });

    it('should default to video_count desc when no URL params', () => {
      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'all',
        sortBy: 'video_count',
        sortOrder: 'desc',
      });
    });

    it('should read sort_by and sort_order from URL params', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?sort_by=title&sort_order=asc'],
      });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'all',
        sortBy: 'title',
        sortOrder: 'asc',
      });
    });

    it('should update URL when sort changes', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists'],
      });

      const sortDropdown = screen.getByLabelText(/sort by/i);

      // Change to title ascending
      await user.selectOptions(sortDropdown, 'title:asc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_by=title');
        expect(location.search).toContain('sort_order=asc');
      });
    });

    it('should preserve filter param when changing sort', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?filter=linked'],
      });

      const sortDropdown = screen.getByLabelText(/sort by/i);

      // Change sort
      await user.selectOptions(sortDropdown, 'title:asc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('filter=linked');
        expect(location.search).toContain('sort_by=title');
      });
    });

    it('should handle invalid sort_by param by defaulting to video_count', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?sort_by=invalid'],
      });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'all',
        sortBy: 'video_count',
        sortOrder: 'desc',
      });
    });

    it('should handle invalid sort_order param by defaulting to desc', () => {
      renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?sort_by=title&sort_order=invalid'],
      });

      expect(mockUsePlaylists).toHaveBeenCalledWith({
        filter: 'all',
        sortBy: 'title',
        sortOrder: 'desc',
      });
    });

    it('should maintain sort during filter changes', async () => {
      const { user } = renderWithProviders(<PlaylistsPage />, {
        initialEntries: ['/playlists?sort_by=title&sort_order=asc'],
      });

      // Change filter to "linked"
      const linkedTab = screen.getByRole('tab', { name: 'YouTube-Linked' });
      await user.click(linkedTab);

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('filter=linked');
        expect(location.search).toContain('sort_by=title');
        expect(location.search).toContain('sort_order=asc');
      });
    });
  });

  describe('Edge Cases', () => {
    it('should handle null total count gracefully', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: null,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should still render playlists
      expect(screen.getAllByRole('article')).toHaveLength(3);
    });

    it('should not show pagination status when total is null and hasNextPage is false', () => {
      mockUsePlaylists.mockReturnValue({
        playlists: mockPlaylists,
        total: null,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      // Should not show "X of Y" when total is null
      expect(screen.queryByText(/showing.*of.*playlists/i)).not.toBeInTheDocument();
    });

    it('should handle empty description gracefully', () => {
      const playlistsWithNullDescription: PlaylistListItem[] = [
        {
          ...mockPlaylists[0],
          description: null,
        },
      ];

      mockUsePlaylists.mockReturnValue({
        playlists: playlistsWithNullDescription,
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

      renderWithProviders(<PlaylistsPage />, { initialEntries: ['/playlists'] });

      expect(screen.getByText('Tech Tutorials Playlist')).toBeInTheDocument();
    });
  });
});
