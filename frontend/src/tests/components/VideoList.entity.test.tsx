/**
 * VideoList / VideoCard — entity intersection result rendering (Feature 062).
 *
 * Covers the result half of US1: per-entity evidence on each row (FR-008a),
 * the empty state distinguishable from an error and from an unfiltered library
 * (FR-012), and a rejected filter presented as recoverable rather than as a
 * dead end (FR-016a).
 *
 * Kept under `src/tests/` so it is typechecked — see the note in
 * VideoFilters.entity.test.tsx.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { VideoList } from '../../components/VideoList';
import type { VideoListItem } from '../../types/video';

vi.mock('../../hooks/useOnlineStatus', () => ({
  useOnlineStatus: () => true,
}));

const useVideosMock = vi.fn();
vi.mock('../../hooks/useVideos', () => ({
  useVideos: (...args: unknown[]) => useVideosMock(...args),
}));

function makeVideo(overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    video_id: 'vid00000001',
    title: 'Fixture Video',
    channel_id: 'UC00000000000000000001',
    channel_title: 'Fixture Channel',
    upload_date: '2024-05-01T00:00:00Z',
    duration: 610,
    view_count: 100,
    transcript_summary: {
      count: 0,
      languages: [],
      has_manual: false,
      has_corrections: false,
    },
    tags: [],
    category_id: null,
    category_name: null,
    topics: [],
    availability_status: 'available',
    ...overrides,
  } as VideoListItem;
}

function baseHookReturn(overrides: Record<string, unknown> = {}) {
  return {
    videos: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    retry: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
    ...overrides,
  };
}

function renderList(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <VideoList {...props} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('VideoList — entity intersection (Feature 062)', () => {
  beforeEach(() => {
    useVideosMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('per-entity evidence (FR-008a)', () => {
    it('shows each required entity with its mention count and first timestamp', () => {
      useVideosMock.mockReturnValue(
        baseHookReturn({
          videos: [
            makeVideo({
              entity_matches: [
                {
                  entity_id: 'e1',
                  entity_type: 'person',
                  canonical_name: 'Ada Lovelace',
                  mention_count: 3,
                  first_timestamp: 65,
                },
              ],
              total_mentions: 3,
            }),
          ],
          total: 1,
        })
      );
      renderList({ entityIds: ['e1'] });

      expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
      // Shown as `(3)` inside the pill, matching the video detail page's
      // entity chips; spoken in full so a screen reader is not left reading
      // punctuation.
      expect(screen.getByText('(3)')).toBeInTheDocument();
      expect(screen.getByText(', 3 mentions')).toHaveClass('sr-only');
      expect(screen.getByText('from 1:05')).toBeInTheDocument();
    });

    it('omits the timestamp entirely when the entity has none', () => {
      // An entity present only in the title or description has no segment and
      // therefore no position in time. Rendering 0:00 would assert it was
      // mentioned at the very start, which is a different and false claim.
      useVideosMock.mockReturnValue(
        baseHookReturn({
          videos: [
            makeVideo({
              entity_matches: [
                {
                  entity_id: 'e1',
                  entity_type: 'place',
                  canonical_name: 'Bletchley',
                  mention_count: 1,
                  first_timestamp: null,
                },
              ],
              total_mentions: 1,
            }),
          ],
          total: 1,
        })
      );
      renderList({ entityIds: ['e1'] });

      expect(screen.getByText('Bletchley')).toBeInTheDocument();
      expect(screen.getByText('(1)')).toBeInTheDocument();
      // Singular when the count is one, in the spoken form.
      expect(screen.getByText(', 1 mention')).toHaveClass('sr-only');
      expect(screen.queryByText(/^from /)).not.toBeInTheDocument();
      expect(screen.queryByText('0:00')).not.toBeInTheDocument();
    });

    it('draws no entity section when no entity filter is active', () => {
      useVideosMock.mockReturnValue(
        baseHookReturn({
          videos: [makeVideo({ entity_matches: null, total_mentions: null })],
          total: 1,
        })
      );
      renderList();
      expect(screen.queryByText(/mentions?$/)).not.toBeInTheDocument();
    });

    it('draws no entity section for an exclusion-only filter', () => {
      // entity_matches is present-and-EMPTY here, which marks an active filter
      // with no required entities. An empty section header would be noise.
      useVideosMock.mockReturnValue(
        baseHookReturn({
          videos: [makeVideo({ entity_matches: [], total_mentions: 0 })],
          total: 1,
        })
      );
      renderList({ excludedEntityIds: ['e9'] });
      expect(screen.queryByText(/mentions?$/)).not.toBeInTheDocument();
    });
  });

  describe('empty state (FR-012)', () => {
    it('distinguishes an empty intersection from an empty library', () => {
      useVideosMock.mockReturnValue(baseHookReturn({ videos: [], total: 0 }));
      renderList({ entityIds: ['e1', 'e2'] });

      expect(screen.getByTestId('empty-intersection')).toBeInTheDocument();
      expect(
        screen.getByText('No videos mention all of these entities')
      ).toBeInTheDocument();
      // And it suggests the action that actually helps at this set size.
      expect(screen.getByText(/Try removing one/)).toBeInTheDocument();
    });

    it('mentions the active scope when transcript-only is narrowing results', () => {
      useVideosMock.mockReturnValue(baseHookReturn({ videos: [], total: 0 }));
      renderList({ entityIds: ['e1'], minEvidence: 'transcript' });

      expect(screen.getByText(/Transcript-only is active/)).toBeInTheDocument();
    });

    it('falls back to the ordinary empty state with no entity filter', () => {
      useVideosMock.mockReturnValue(baseHookReturn({ videos: [], total: 0 }));
      renderList();

      expect(screen.queryByTestId('empty-intersection')).not.toBeInTheDocument();
    });
  });

  describe('rejected filter (FR-016a)', () => {
    it('presents a 400 as recoverable, naming the offending value', () => {
      useVideosMock.mockReturnValue(
        baseHookReturn({
          isError: true,
          error: {
            type: 'unknown',
            message: 'An unexpected error occurred.',
            status: 400,
            detail: 'Unknown entity id(s): 11111111-1111-4111-8111-111111111111.',
          },
        })
      );
      renderList({ entityIds: ['11111111-1111-4111-8111-111111111111'] });

      const panel = screen.getByTestId('filter-rejected');
      expect(panel).toBeInTheDocument();
      // The server's explanation must survive to the user; the generic
      // type-keyed message cannot say WHICH value was rejected.
      expect(panel).toHaveTextContent('11111111-1111-4111-8111-111111111111');
      expect(panel).toHaveTextContent(/other filters are still active/i);
    });

    it('does not offer retry for a rejection, since retrying cannot help', () => {
      useVideosMock.mockReturnValue(
        baseHookReturn({
          isError: true,
          error: { type: 'unknown', message: 'x', status: 400 },
        })
      );
      renderList({ entityIds: ['e1'] });

      expect(screen.getByTestId('filter-rejected')).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: /retry|try again/i })
      ).not.toBeInTheDocument();
    });

    it('still shows the ordinary error state for a server failure', () => {
      // A 500 IS worth retrying, so it must not be absorbed into the
      // recoverable-filter panel.
      useVideosMock.mockReturnValue(
        baseHookReturn({
          isError: true,
          error: { type: 'server', message: 'boom', status: 500 },
        })
      );
      renderList({ entityIds: ['e1'] });

      expect(screen.queryByTestId('filter-rejected')).not.toBeInTheDocument();
    });
  });

  describe('parameter pass-through', () => {
    it('forwards entity filters to the videos query', () => {
      useVideosMock.mockReturnValue(baseHookReturn({ videos: [], total: 0 }));
      renderList({
        entityIds: ['e1', 'e2'],
        excludedEntityIds: ['e3'],
        minEvidence: 'transcript',
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          entityIds: ['e1', 'e2'],
          excludedEntityIds: ['e3'],
          minEvidence: 'transcript',
        })
      );
    });
  });
});
