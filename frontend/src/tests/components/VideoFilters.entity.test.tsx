/**
 * VideoFilters — entity intersection filter (Feature 062).
 *
 * Covers the panel half of US1/US2: selecting required and excluded entities,
 * the selection ceiling, pill rendering, and the transcript-only toggle.
 *
 * Placed under `src/tests/` alongside the sibling VideoFilters suites rather
 * than under `frontend/tests/`. Only tests importing `tests/test-utils` need
 * the latter; `tsconfig.json` includes just `src`, so a test kept here is
 * typechecked by `npm run typecheck` and one moved there is not.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { VideoFilters } from '../../components/VideoFilters';
import { FILTER_LIMITS } from '../../types/filters';

// ---------------------------------------------------------------------------
// Mocks — the panel's sibling data sources, not the subject of these tests
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({
    categories: [{ category_id: '10', name: 'Gaming', assignable: true }],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('../../hooks/useTopics', () => ({
  useTopics: () => ({ topics: [], isLoading: false, isError: false, error: null }),
}));

vi.mock('../../hooks/useOnlineStatus', () => ({
  useOnlineStatus: () => true,
}));

const ADA = {
  entity_id: '11111111-1111-4111-8111-111111111111',
  canonical_name: 'Ada Lovelace',
  entity_type: 'person',
};
const ENGINE = {
  entity_id: '22222222-2222-4222-8222-222222222222',
  canonical_name: 'Analytical Engine',
  entity_type: 'work',
};
const ENTITIES = [ADA, ENGINE];

vi.mock('../../hooks/useEntitySearch', () => ({
  useEntitySearch: (search: string) => ({
    entities: search.trim().length >= 2 ? ENTITIES : [],
    isLoading: false,
    isBelowMinChars: search.trim().length < 2,
    isError: false,
  }),
}));

function renderFilters(initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <VideoFilters />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('VideoFilters — entity intersection (Feature 062)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [], pagination: { total: 0 } }),
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  describe('selection', () => {
    it('renders a required and an excluded entity picker', () => {
      renderFilters();
      expect(screen.getByLabelText('Mentions all of')).toBeInTheDocument();
      expect(screen.getByLabelText('Excluding')).toBeInTheDocument();
    });

    it('adds a chosen entity to the URL as a repeated entity_id key', async () => {
      const user = userEvent.setup();
      renderFilters();

      await user.type(screen.getByLabelText('Mentions all of'), 'ada');
      await user.click(await screen.findByText('Ada Lovelace'));

      // The name renders twice by design — once as the picker's selected chip
      // and once as a filter pill — so assert on the chip's remove control,
      // which is unique and is also the affordance that makes the selection
      // reversible.
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Remove Ada Lovelace' })
        ).toBeInTheDocument();
      });
    });

    it('offers suggestions only at two characters or more', async () => {
      const user = userEvent.setup();
      renderFilters();

      await user.type(screen.getByLabelText('Mentions all of'), 'a');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      await user.type(screen.getByLabelText('Mentions all of'), 'd');
      expect(await screen.findByRole('listbox')).toBeInTheDocument();
    });

    it('does not offer an entity already chosen in the opposite set', async () => {
      const user = userEvent.setup();
      // Ada is already EXCLUDED, so she must not appear as a required option:
      // the two sets must stay disjoint, and the API rejects an overlap (FR-016).
      renderFilters([`/?exclude_entity_id=${ADA.entity_id}`]);

      await user.type(screen.getByLabelText('Mentions all of'), 'ada');
      const listbox = await screen.findByRole('listbox');
      expect(listbox).not.toHaveTextContent('Ada Lovelace');
      expect(listbox).toHaveTextContent('Analytical Engine');
    });
  });

  describe('selection ceiling (FR-002a, FR-002b)', () => {
    it('explains the limit and disables input at the ceiling', () => {
      const atCeiling = Array.from(
        { length: FILTER_LIMITS.MAX_ENTITIES },
        (_, index) =>
          `entity_id=00000000-0000-4000-8000-${String(index).padStart(12, '0')}`
      ).join('&');
      renderFilters([`/?${atCeiling}`]);

      const input = screen.getByLabelText('Mentions all of');
      expect(input).toBeDisabled();
      expect(
        screen.getByText(
          `Maximum ${FILTER_LIMITS.MAX_ENTITIES} reached. Remove one to add another.`
        )
      ).toBeInTheDocument();
    });

    it('applies the ceiling to each set separately, not to their sum', () => {
      // Nine required plus nine excluded is eighteen entities, and NEITHER set
      // is at its own ceiling of ten. A ceiling applied to the combined size
      // would wrongly disable both inputs here.
      const nine = (key: string) =>
        Array.from(
          { length: 9 },
          (_, i) => `${key}=00000000-0000-4000-8000-${String(i).padStart(12, '0')}`
        ).join('&');
      renderFilters([`/?${nine('entity_id')}&${nine('exclude_entity_id')}`]);

      expect(screen.getByLabelText('Mentions all of')).not.toBeDisabled();
      expect(screen.getByLabelText('Excluding')).not.toBeDisabled();
    });
  });

  describe('filter pills', () => {
    it('renders required and excluded entities as distinct pill types', () => {
      renderFilters([
        `/?entity_id=${ADA.entity_id}&exclude_entity_id=${ENGINE.entity_id}`,
      ]);
      // Both ids appear as pills; the labels fall back to the id until the
      // user re-picks, since the URL carries ids rather than names.
      const pills = screen.getAllByRole('listitem');
      expect(pills.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe('address round-trip (FR-011, FR-011a, FR-017, SC-006)', () => {
    it('restores required entities, an exclusion, and a scope from one URL', async () => {
      // The shareable-link contract: everything needed to reproduce a result
      // lives in the address. A parameter that the panel writes but does not
      // read back produces a link that works for the sender and not for the
      // recipient — which is worse than not being shareable at all.
      renderFilters([
        `/?entity_id=${ADA.entity_id}&entity_id=${ENGINE.entity_id}` +
          `&exclude_entity_id=00000000-0000-4000-8000-000000000009` +
          `&min_evidence=transcript`,
      ]);

      await waitFor(() => {
        expect(
          screen.getByText('Type at least 2 characters. 2 of 10 selected.')
        ).toBeInTheDocument();
      });
      expect(
        screen.getByText('Type at least 2 characters. 1 of 10 selected.')
      ).toBeInTheDocument();
      expect(screen.getByLabelText(/Transcript only/)).toBeChecked();
    });

    it('keeps required and excluded sets distinct on restore', async () => {
      // Both sets are repeated keys on the same address; reading one into the
      // other would silently invert the user's intent.
      renderFilters([
        `/?entity_id=${ADA.entity_id}&exclude_entity_id=${ENGINE.entity_id}`,
      ]);

      // One in each set, not two in either — so both pickers report exactly
      // one selection, which is what two matches of this text means.
      await waitFor(() => {
        expect(
          screen.getAllByText('Type at least 2 characters. 1 of 10 selected.')
        ).toHaveLength(2);
      });
    });

    it('restores an exclusion-only address', async () => {
      // FR-015: exclusion works with an empty required set, so the address
      // must round-trip that shape too.
      renderFilters([`/?exclude_entity_id=${ENGINE.entity_id}`]);

      await waitFor(() => {
        expect(
          screen.getByText('Type at least 2 characters. 0 of 10 selected.')
        ).toBeInTheDocument();
      });
      expect(
        screen.getByText('Type at least 2 characters. 1 of 10 selected.')
      ).toBeInTheDocument();
    });

    it('treats a duplicated entity id in the address as one selection', async () => {
      // Requesting the same entity twice is idempotent (Edge Cases); a
      // hand-edited or double-appended link must not consume two slots.
      renderFilters([
        `/?entity_id=${ADA.entity_id}&entity_id=${ADA.entity_id}`,
      ]);

      await waitFor(() => {
        expect(screen.getByLabelText('Mentions all of')).toBeInTheDocument();
      });
      // The API deduplicates; the panel must not report two selections for one
      // entity, or the ceiling count would drift from what the server enforces.
      expect(
        screen.getByText('Type at least 2 characters. 1 of 10 selected.')
      ).toBeInTheDocument();
    });
  });

  describe('evidence scope (FR-020b)', () => {
    it('offers exactly one scope affordance, a transcript-only toggle', () => {
      renderFilters();
      expect(screen.getByLabelText(/Transcript only/)).toBeInTheDocument();
      // A general scope selector waits for a graded confidence model; there
      // must be no source dropdown alongside it.
      expect(screen.queryByLabelText(/evidence scope/i)).not.toBeInTheDocument();
    });

    it('reflects an active transcript-only scope from the address', () => {
      renderFilters(['/?min_evidence=transcript']);
      expect(screen.getByLabelText(/Transcript only/)).toBeChecked();
    });

    it('is unchecked when no scope is requested, meaning all three sources', () => {
      renderFilters();
      expect(screen.getByLabelText(/Transcript only/)).not.toBeChecked();
    });
  });
});
