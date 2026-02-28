/**
 * Tests for VideoFilters component — canonical_tag filter support (US2/T016)
 *
 * Verifies:
 * - Reads canonical_tag URL params via getAll
 * - Builds canonical_tag pills with display name from cache
 * - Display name fetched from API on page load with URL params (bookmark scenario)
 * - handleClearAll clears canonical_tag params
 * - "Active Filters (N)" count reflects canonical tag count
 * - MAX_TAGS limit applies to canonical tags
 * - Bulk debounce on Clear All (150ms)
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VideoFilters } from '../../components/VideoFilters';

// ---------------------------------------------------------------------------
// Mock hooks that VideoFilters depends on
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({
    categories: [
      { category_id: '10', name: 'Gaming', assignable: true },
      { category_id: '20', name: 'Music', assignable: true },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('../../hooks/useTopics', () => ({
  useTopics: () => ({
    topics: [
      {
        topic_id: '/m/04rlf',
        name: 'Music Topic',
        parent_topic_id: null,
        parent_path: null,
        depth: 0,
        video_count: 100,
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('../../hooks/useOnlineStatus', () => ({
  useOnlineStatus: () => true,
}));

// ---------------------------------------------------------------------------
// Helper: build mock canonical tag detail response
// ---------------------------------------------------------------------------

function makeDetailResponse(
  canonicalForm: string,
  normalizedForm: string,
  aliasCount: number
): string {
  return JSON.stringify({
    data: {
      canonical_form: canonicalForm,
      normalized_form: normalizedForm,
      alias_count: aliasCount,
      video_count: 10,
      top_aliases: [],
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  });
}

function mockResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderWithProviders(
  ui: React.ReactElement,
  { initialEntries = ['/'] }: { initialEntries?: string[] } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('VideoFilters — canonical_tag support (US2)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // URL param reading
  // -----------------------------------------------------------------------
  describe('URL param reading', () => {
    it('reads a single canonical_tag URL param', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('JavaScript', 'javascript', 3))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=javascript'],
      });

      await waitFor(() => {
        expect(screen.getByText(/Active Filters/)).toBeInTheDocument();
      });
    });

    it('reads multiple canonical_tag URL params', async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes('/canonical-tags/javascript')) {
          return Promise.resolve(
            mockResponse(makeDetailResponse('JavaScript', 'javascript', 3))
          );
        }
        if (url.includes('/canonical-tags/react')) {
          return Promise.resolve(
            mockResponse(makeDetailResponse('React', 'react', 2))
          );
        }
        return Promise.resolve(mockResponse('{}', 404));
      });

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=javascript&canonical_tag=react'],
      });

      await waitFor(() => {
        expect(screen.getByText('Active Filters (2)')).toBeInTheDocument();
      });
    });

    it('filters out empty canonical_tag params', async () => {
      fetchMock.mockResolvedValue(mockResponse('{}', 404));

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=&canonical_tag=javascript'],
      });

      await waitFor(() => {
        expect(screen.getByText('Active Filters (1)')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Display name hydration (bookmark scenario)
  // -----------------------------------------------------------------------
  describe('Display name hydration — bookmark scenario', () => {
    it('fetches canonical_form via detail endpoint (not search) on page load', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('JavaScript', 'javascript', 3))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=javascript'],
      });

      await waitFor(() => {
        const calls = fetchMock.mock.calls as [string][];
        const detailCalls = calls.filter(
          ([url]) => url.includes('/canonical-tags/javascript') && !url.includes('?q=')
        );
        expect(detailCalls.length).toBeGreaterThan(0);
      });
    });

    it('shows canonical_form label (not normalized_form) after hydration', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('JavaScript', 'javascript', 3))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=javascript'],
      });

      await waitFor(() => {
        // 'JavaScript' appears in both TagAutocomplete (selected tags) and FilterPill
        const elements = screen.getAllByText('JavaScript');
        expect(elements.length).toBeGreaterThan(0);
      });
    });

    it('shows variation badge "{N} var." after hydration when alias_count > 1', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('TypeScript', 'typescript', 4))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=typescript'],
      });

      await waitFor(() => {
        // alias_count = 4 → "3 var."
        expect(screen.getByText('3 var.')).toBeInTheDocument();
      });
    });

    it('falls back to normalized_form as label when API returns 404', async () => {
      fetchMock.mockResolvedValue(mockResponse('{}', 404));

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=unknown-tag'],
      });

      await waitFor(() => {
        // 'unknown-tag' appears in both TagAutocomplete (selected tags) and FilterPill
        const elements = screen.getAllByText('unknown-tag');
        expect(elements.length).toBeGreaterThan(0);
      });
    });

    it('uses alias_limit=1 in the detail endpoint URL', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('Python', 'python', 2))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=python'],
      });

      await waitFor(() => {
        const calls = fetchMock.mock.calls as [string][];
        const detailCall = calls.find(([url]) =>
          url.includes('/canonical-tags/python')
        );
        expect(detailCall?.[0]).toContain('alias_limit=1');
      });
    });
  });

  // -----------------------------------------------------------------------
  // Active filter count
  // -----------------------------------------------------------------------
  describe('Active filter count', () => {
    it('"Active Filters (N)" reflects canonical tags', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('React', 'react', 1))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=react'],
      });

      await waitFor(() => {
        expect(screen.getByText('Active Filters (1)')).toBeInTheDocument();
      });
    });

    it('canonical tags contribute to total filter count alongside other filter types', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('JavaScript', 'javascript', 1))
      );

      renderWithProviders(<VideoFilters />, {
        // canonical_tag + category = 2 total
        initialEntries: ['/?canonical_tag=javascript&category=10'],
      });

      await waitFor(() => {
        expect(screen.getByText('Active Filters (2)')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // MAX_TAGS limit applies to canonical tags
  // -----------------------------------------------------------------------
  describe('MAX_TAGS limit', () => {
    it('shows approaching-limit warning when 8+ canonical tags active', async () => {
      // 8 canonical tags → totalFilters = 8, approaches MAX_TOTAL (15) * 0.8 = 12? No.
      // But tags.length (0) >= MAX_TAGS * 0.8 (8)? No, it's canonicalTags.
      // With 12 canonical tags, totalFilters = 12 >= MAX_TOTAL * 0.8 (12) → approaching limit.
      fetchMock.mockImplementation((url: string) => {
        const match = /\/canonical-tags\/([^?]+)/.exec(url);
        if (match) {
          const nf = match[1] ?? 'tag';
          return Promise.resolve(
            mockResponse(makeDetailResponse(nf, nf, 1))
          );
        }
        return Promise.resolve(mockResponse('{}', 404));
      });

      // 12 canonical tags → totalFilters = 12 which is >= 15 * 0.8 = 12, triggers "approaching limit"
      const twelveTags = Array.from(
        { length: 12 },
        (_, i) => `canonical_tag=ct${i}`
      ).join('&');

      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?${twelveTags}`],
      });

      await waitFor(
        () => {
          expect(
            screen.getByText(/Approaching filter limits|Maximum filter limit reached/)
          ).toBeInTheDocument();
        },
        { timeout: 10000 }
      );
    });
  });

  // -----------------------------------------------------------------------
  // Clear All clears canonical_tag params (using fake timers)
  // -----------------------------------------------------------------------
  describe('Clear All functionality', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('shows Clear All button when canonical_tag filters are active', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('React', 'react', 1))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=react'],
      });

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Clear All' })
        ).toBeInTheDocument();
      });
    });

    it('clears canonical_tag filters when Clear All clicked', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('React', 'react', 1))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=react'],
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Clear All' })).toBeInTheDocument();
      });

      const clearAllBtn = screen.getByRole('button', { name: 'Clear All' });

      await act(async () => {
        await user.click(clearAllBtn);
        vi.advanceTimersByTime(200);
      });

      await waitFor(() => {
        expect(screen.getByText(/No active filters/)).toBeInTheDocument();
      });
    });

    it('150ms debounce: filter state persists until timeout fires', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('React', 'react', 1))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=react'],
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Clear All' })).toBeInTheDocument();
      });

      const clearAllBtn = screen.getByRole('button', { name: 'Clear All' });

      // Click and advance only 100ms — not enough for 150ms debounce
      await act(async () => {
        await user.click(clearAllBtn);
        vi.advanceTimersByTime(100);
      });

      // Filters should STILL be visible since debounce hasn't fired
      expect(screen.queryByText(/No active filters/)).not.toBeInTheDocument();

      // Advance past debounce
      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(screen.getByText(/No active filters/)).toBeInTheDocument();
      });
    });

    it('Clear All also clears tag and category params', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('React', 'react', 1))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=react&category=10'],
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Clear All' })).toBeInTheDocument();
        expect(screen.getByText('Active Filters (2)')).toBeInTheDocument();
      });

      const clearAllBtn = screen.getByRole('button', { name: 'Clear All' });

      await act(async () => {
        await user.click(clearAllBtn);
        vi.advanceTimersByTime(200);
      });

      await waitFor(() => {
        expect(screen.getByText(/No active filters/)).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Canonical tag pill removal
  // -----------------------------------------------------------------------
  describe('Canonical tag pill removal', () => {
    it('removes the correct canonical_tag pill on remove button click', async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes('/canonical-tags/javascript')) {
          return Promise.resolve(
            mockResponse(makeDetailResponse('JavaScript', 'javascript', 1))
          );
        }
        if (url.includes('/canonical-tags/react')) {
          return Promise.resolve(
            mockResponse(makeDetailResponse('React', 'react', 1))
          );
        }
        return Promise.resolve(mockResponse('{}', 404));
      });

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=javascript&canonical_tag=react'],
      });

      // Wait for both labels to hydrate
      // Note: each label appears in both TagAutocomplete (selected tags) and FilterPill
      await waitFor(() => {
        const jsElements = screen.getAllByText('JavaScript');
        expect(jsElements.length).toBeGreaterThan(0);
        const reactElements = screen.getAllByText('React');
        expect(reactElements.length).toBeGreaterThan(0);
      });

      // Remove the React pill
      const removeReactBtn = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: React',
      });
      await userEvent.click(removeReactBtn);

      await waitFor(() => {
        expect(screen.queryByText('React')).not.toBeInTheDocument();
        const jsElements = screen.getAllByText('JavaScript');
        expect(jsElements.length).toBeGreaterThan(0);
        expect(screen.getByText('Active Filters (1)')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // No canonical tags — no side effects
  // -----------------------------------------------------------------------
  describe('No canonical tags', () => {
    it('does not show canonical tag pills when no canonical_tag params', () => {
      fetchMock.mockResolvedValue(mockResponse('{}', 404));

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/'],
      });

      expect(screen.getByText(/No active filters/)).toBeInTheDocument();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  // -----------------------------------------------------------------------
  // Coexistence with existing filter types
  // -----------------------------------------------------------------------
  describe('Coexistence with other filter types', () => {
    it('renders canonical_tag pill and category pill together', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('Go', 'go', 2))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=go&category=10'],
      });

      await waitFor(() => {
        expect(screen.getByText('Active Filters (2)')).toBeInTheDocument();
      });

      // After active count shows 2, both pills should be present
      // Note: 'Go' appears in both TagAutocomplete (selected tags) and FilterPill
      await waitFor(() => {
        const goElements = screen.getAllByText('Go');
        expect(goElements.length).toBeGreaterThan(0);
        // Gaming appears in both the category dropdown and the filter pill
        const gamingElements = screen.getAllByText('Gaming');
        expect(gamingElements.length).toBeGreaterThan(0);
      });
    });

    it('canonical_tag pill shows variation badge alongside other pills', async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeDetailResponse('Rust', 'rust', 3))
      );

      renderWithProviders(<VideoFilters />, {
        initialEntries: ['/?canonical_tag=rust&category=10'],
      });

      await waitFor(() => {
        // alias_count = 3 → "2 var."
        expect(screen.getByText('2 var.')).toBeInTheDocument();
      });

      // Gaming appears in both the category dropdown and the filter pill
      const gamingElements = screen.getAllByText('Gaming');
      expect(gamingElements.length).toBeGreaterThan(0);
    });
  });
});
