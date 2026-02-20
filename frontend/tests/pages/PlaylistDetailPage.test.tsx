/**
 * Tests for PlaylistDetailPage sort and filter features (T019).
 *
 * Covers:
 * - Sort dropdown renders 3 options with correct labels
 * - Filter toggles render (unavailable_only, liked_only, has_transcript)
 * - URL state persistence on refresh
 * - Empty state messages (single-filter specific + multi-filter combined)
 * - Focus remains on control after change
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders, getTestLocation } from '../test-utils';
import { PlaylistDetailPage } from '../../src/pages/PlaylistDetailPage';
import type { PlaylistVideoItem } from '../../src/types/playlist';

// Mock the hooks
vi.mock('../../src/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/hooks')>();
  return {
    ...original,
    usePlaylistDetail: vi.fn(),
    usePlaylistVideos: vi.fn(),
  };
});

// Mock PlaylistVideoCard
vi.mock('../../src/components/PlaylistVideoCard', () => ({
  PlaylistVideoCard: ({ video }: { video: PlaylistVideoItem }) => (
    <article data-testid={`video-card-${video.video_id}`}>
      <h3>{video.title}</h3>
      <span>Position: {video.position}</span>
    </article>
  ),
}));

// Mock LoadingState
vi.mock('../../src/components/LoadingState', () => ({
  LoadingState: ({ count }: { count: number }) => (
    <div role="status" aria-label="Loading content">
      Loading {count} items...
    </div>
  ),
}));

import { usePlaylistDetail, usePlaylistVideos } from '../../src/hooks';

const mockUsePlaylistDetail = vi.mocked(usePlaylistDetail);
const mockUsePlaylistVideos = vi.mocked(usePlaylistVideos);

const mockPlaylist = {
  playlist_id: 'PLtest123456789',
  title: 'Test Playlist',
  description: 'A test playlist description',
  video_count: 5,
  privacy_status: 'public' as const,
  is_linked: true,
  default_language: 'en',
  channel_id: 'UCtest123',
  published_at: '2024-01-15T00:00:00Z',
  deleted_flag: false,
  playlist_type: 'regular',
  created_at: '2024-01-15T00:00:00Z',
  updated_at: '2024-01-15T00:00:00Z',
};

const mockVideos: PlaylistVideoItem[] = [
  {
    video_id: 'vid001',
    title: 'Alpha Video',
    channel_id: 'UCtest123',
    channel_title: 'Test Channel',
    upload_date: '2024-01-15T00:00:00Z',
    duration: 300,
    view_count: 1000,
    transcript_summary: { count: 1, languages: ['en'], has_manual: false },
    position: 0,
    availability_status: 'available',
  },
  {
    video_id: 'vid002',
    title: 'Beta Video',
    channel_id: 'UCtest123',
    channel_title: 'Test Channel',
    upload_date: '2024-02-20T00:00:00Z',
    duration: 450,
    view_count: 2000,
    transcript_summary: { count: 0, languages: [], has_manual: false },
    position: 1,
    availability_status: 'available',
  },
];

function setupDefaultMocks(options: {
  videos?: PlaylistVideoItem[];
  isLoading?: boolean;
  total?: number | null;
} = {}) {
  const { videos = mockVideos, isLoading = false, total = 2 } = options;

  mockUsePlaylistDetail.mockReturnValue({
    playlist: mockPlaylist,
    isLoading: false,
    isError: false,
    error: null,
    retry: vi.fn(),
  });

  mockUsePlaylistVideos.mockReturnValue({
    videos,
    total,
    loadedCount: videos.length,
    isLoading,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  });
}

describe('PlaylistDetailPage Sort & Filter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Sort Dropdown Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('Sort Dropdown', () => {
    it('should render the sort dropdown with "Sort by" label', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('Sort by')).toBeInTheDocument();
    });

    it('should render a select element for sorting', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const select = screen.getByRole('combobox', { name: /sort by/i });
      expect(select).toBeInTheDocument();
    });

    it('should render sort options for position, upload date, and title', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const select = screen.getByRole('combobox', { name: /sort by/i });
      const options = within(select).getAllByRole('option');

      // 3 fields x 2 directions = 6 option entries
      expect(options.length).toBe(6);

      // Check option labels contain expected field names
      const optionTexts = options.map((opt) => opt.textContent);
      expect(optionTexts.some((t) => t?.includes('Position'))).toBe(true);
      expect(optionTexts.some((t) => t?.includes('Upload Date'))).toBe(true);
      expect(optionTexts.some((t) => t?.includes('Title'))).toBe(true);
    });

    it('should have position ascending as default selected value', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const select = screen.getByRole('combobox', { name: /sort by/i }) as HTMLSelectElement;
      // Default: position:asc
      expect(select.value).toBe('position:asc');
    });

    it('should update URL when sort option is changed', async () => {
      setupDefaultMocks();
      const { user } = renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const select = screen.getByRole('combobox', { name: /sort by/i });
      await user.selectOptions(select, 'upload_date:desc');

      const location = getTestLocation();
      expect(location.search).toContain('sort_by=upload_date');
      expect(location.search).toContain('sort_order=desc');
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Filter Toggle Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('Filter Toggles', () => {
    it('should render unavailable_only filter toggle', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByLabelText('Unavailable only')).toBeInTheDocument();
    });

    it('should render liked_only filter toggle', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByLabelText('Liked only')).toBeInTheDocument();
    });

    it('should render has_transcript filter toggle', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByLabelText('Has transcript')).toBeInTheDocument();
    });

    it('should have all filter toggles unchecked by default', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const unavailable = screen.getByLabelText('Unavailable only') as HTMLInputElement;
      const liked = screen.getByLabelText('Liked only') as HTMLInputElement;
      const transcript = screen.getByLabelText('Has transcript') as HTMLInputElement;

      expect(unavailable.checked).toBe(false);
      expect(liked.checked).toBe(false);
      expect(transcript.checked).toBe(false);
    });

    it('should update URL when filter is toggled on', async () => {
      setupDefaultMocks();
      const { user } = renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const likedCheckbox = screen.getByLabelText('Liked only');
      await user.click(likedCheckbox);

      const location = getTestLocation();
      expect(location.search).toContain('liked_only=true');
    });

    it('should pass sort/filter params to usePlaylistVideos hook', async () => {
      setupDefaultMocks();
      const { user } = renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?liked_only=true&sort_by=title&sort_order=asc'],
        path: '/playlists/:playlistId',
      });

      // Verify the hook was called with sort/filter params
      expect(mockUsePlaylistVideos).toHaveBeenCalledWith(
        'PLtest123456789',
        expect.objectContaining({
          sortBy: 'title',
          sortOrder: 'asc',
          likedOnly: true,
        })
      );
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // URL State Persistence Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('URL State Persistence', () => {
    it('should restore sort params from URL on mount', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?sort_by=title&sort_order=desc'],
        path: '/playlists/:playlistId',
      });

      const select = screen.getByRole('combobox', { name: /sort by/i }) as HTMLSelectElement;
      expect(select.value).toBe('title:desc');
    });

    it('should restore filter params from URL on mount', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?has_transcript=true'],
        path: '/playlists/:playlistId',
      });

      const transcript = screen.getByLabelText('Has transcript') as HTMLInputElement;
      expect(transcript.checked).toBe(true);
    });

    it('should restore multiple filter params from URL on mount', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?liked_only=true&has_transcript=true'],
        path: '/playlists/:playlistId',
      });

      const liked = screen.getByLabelText('Liked only') as HTMLInputElement;
      const transcript = screen.getByLabelText('Has transcript') as HTMLInputElement;
      expect(liked.checked).toBe(true);
      expect(transcript.checked).toBe(true);
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Empty State Messages Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('Empty State Messages', () => {
    it('should show default empty message when no filters active', () => {
      setupDefaultMocks({ videos: [], total: 0 });
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('No videos in this playlist')).toBeInTheDocument();
    });

    it('should show liked-specific empty message when liked_only filter active', () => {
      setupDefaultMocks({ videos: [], total: 0 });
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?liked_only=true'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('No matching videos')).toBeInTheDocument();
      expect(screen.getByText('No liked videos in this playlist.')).toBeInTheDocument();
    });

    it('should show transcript-specific empty message when has_transcript filter active', () => {
      setupDefaultMocks({ videos: [], total: 0 });
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?has_transcript=true'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('No matching videos')).toBeInTheDocument();
      expect(
        screen.getByText('No videos with transcripts in this playlist.')
      ).toBeInTheDocument();
    });

    it('should show unavailable-specific empty message when unavailable_only filter active', () => {
      setupDefaultMocks({ videos: [], total: 0 });
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789?unavailable_only=true'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('No matching videos')).toBeInTheDocument();
      expect(
        screen.getByText('No unavailable videos in this playlist.')
      ).toBeInTheDocument();
    });

    it('should show combined filter empty message when multiple filters active', () => {
      setupDefaultMocks({ videos: [], total: 0 });
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: [
          '/playlists/PLtest123456789?liked_only=true&has_transcript=true',
        ],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByText('No matching videos')).toBeInTheDocument();
      expect(
        screen.getByText(
          'No videos match the selected filters. Try removing some filters.'
        )
      ).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Focus Management Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('Focus Management', () => {
    it('should keep focus on checkbox after toggling filter', async () => {
      setupDefaultMocks();
      const { user } = renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const likedCheckbox = screen.getByLabelText('Liked only');
      await user.click(likedCheckbox);

      // After clicking, focus should remain on the checkbox
      expect(document.activeElement).toBe(likedCheckbox);
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // ARIA Live Region Tests
  // ═══════════════════════════════════════════════════════════════════════

  describe('ARIA Live Region', () => {
    it('should have ARIA live region for filtered count', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      const liveRegion = screen.getByRole('status', { name: '' });
      expect(liveRegion).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Video List Rendering
  // ═══════════════════════════════════════════════════════════════════════

  describe('Video List', () => {
    it('should render video cards when videos are available', () => {
      setupDefaultMocks();
      renderWithProviders(<PlaylistDetailPage />, {
        initialEntries: ['/playlists/PLtest123456789'],
        path: '/playlists/:playlistId',
      });

      expect(screen.getByTestId('video-card-vid001')).toBeInTheDocument();
      expect(screen.getByTestId('video-card-vid002')).toBeInTheDocument();
    });
  });
});
