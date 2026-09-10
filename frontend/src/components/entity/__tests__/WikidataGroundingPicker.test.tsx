/**
 * Tests for WikidataGroundingPicker (Feature 073, T007/T015).
 *
 * WikidataGroundingPicker was extracted from CreateEntityModal's inline
 * grounding block so it can be reused by the entity-detail "Change link"
 * re-grounding dialog (Feature 073, US1) without duplicating the debounce,
 * auto-search, and stale-search-discard logic. CreateEntityModal's own
 * grounding behavior continues to be covered by
 * `src/components/entity/__tests__/CreateEntityModal.candidates.test.tsx`
 * (which passed unchanged after the extraction).
 *
 * Coverage here is the picker's own contract in isolation:
 * - Auto-searches once name/type are present (no manual trigger)
 * - Renders the ranked shortlist with type-match/statement/sitelink signals
 *   and a stub warning
 * - Selecting a candidate calls `onSelectCandidate` with that candidate
 *   (fully controlled — `selectedCandidate` drives the checked radio)
 * - Clearing the "Grounded to" chip calls `onSelectCandidate(null)`
 * - Changing `name`/`entityType` discards the stale search and calls
 *   `onSelectCandidate(null)` (a candidate approved for one name/type must
 *   not silently carry over to another)
 * - `disabled` disables every interactive control
 * - `optional`/`allowSkip`/`heading` let a caller (e.g. the re-link dialog)
 *   drop the "optional" framing and the skip affordance, since a re-link
 *   requires picking a match
 *
 * The description pre-fill (FR-011) and the `useRegroundEntity` mutation
 * payload/invalidation are the re-link dialog's own responsibility, not the
 * picker's — see `EntityEnrichmentSection.test.tsx`.
 *
 * `useDebounce` is mocked as a pass-through identity function so the
 * auto-search effect fires synchronously within `fireEvent`-driven
 * assertions instead of racing the real 450ms timer — mirroring
 * `CreateEntityModal.candidates.test.tsx`.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks — must be declared before component imports (vi.mock hoisting)
// ---------------------------------------------------------------------------

vi.mock('@/hooks/useDebounce', () => ({
  useDebounce: (value: unknown) => value,
}));

vi.mock('@/hooks/useEntityMentions', () => ({
  useWikidataCandidates: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { WikidataGroundingPicker } from '../WikidataGroundingPicker';
import type { WikidataGroundingPickerProps } from '../WikidataGroundingPicker';
import { useWikidataCandidates } from '@/hooks/useEntityMentions';
import type { WikidataCandidate } from '@/api/entityMentions';
import type { Mock } from 'vitest';

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeCandidate(overrides: Partial<WikidataCandidate> = {}): WikidataCandidate {
  return {
    qid: 'Q00000001',
    label: 'Test Person',
    description: 'A placeholder entity used for testing',
    instance_of: ['Q5'],
    statement_count: 42,
    sitelink_count: 3,
    is_stub: false,
    type_matches: true,
    ...overrides,
  };
}

function makeWikidataHook(
  overrides: {
    candidates?: WikidataCandidate[];
    unavailable?: boolean;
    hasSearched?: boolean;
    isLoading?: boolean;
    isFetching?: boolean;
    search?: Mock;
    reset?: Mock;
  } = {}
) {
  return {
    candidates: [],
    unavailable: false,
    hasSearched: false,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    search: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
}

function mockWikidata(overrides: Parameters<typeof makeWikidataHook>[0] = {}) {
  const hook = makeWikidataHook(overrides);
  (useWikidataCandidates as Mock).mockReturnValue(hook);
  return hook;
}

function renderPicker(overrides: Partial<WikidataGroundingPickerProps> = {}) {
  const onSelectCandidate = vi.fn();
  const props: WikidataGroundingPickerProps = {
    name: 'Test Person',
    entityType: 'person',
    selectedCandidate: null,
    onSelectCandidate,
    ...overrides,
  };
  return {
    onSelectCandidate,
    ...render(<WikidataGroundingPicker {...props} />),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WikidataGroundingPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWikidata();
  });

  describe('Auto-search', () => {
    it('automatically triggers a Wikidata search once mounted with a name and type', () => {
      const hook = mockWikidata();
      renderPicker();

      expect(hook.search).toHaveBeenCalled();
    });

    it('shows a "Search again" affordance once a search has completed', () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      renderPicker();

      expect(screen.getByRole('button', { name: /search again/i })).toBeInTheDocument();
    });

    it('does not show "Search again" before any search has completed', () => {
      mockWikidata({ hasSearched: false });
      renderPicker();

      expect(screen.queryByRole('button', { name: /search again/i })).not.toBeInTheDocument();
    });
  });

  describe('Shortlist rendering', () => {
    it('renders each candidate with label, description, statement/sitelink counts and a type-match indicator', () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ statement_count: 42, sitelink_count: 3, type_matches: true })],
      });

      renderPicker();

      expect(screen.getByRole('radiogroup', { name: /wikidata candidates/i })).toBeInTheDocument();
      expect(screen.getByText('Test Person')).toBeInTheDocument();
      expect(screen.getByText('A placeholder entity used for testing')).toBeInTheDocument();
      expect(screen.getByText(/42 statements/)).toBeInTheDocument();
      expect(screen.getByText(/3 sitelinks/)).toBeInTheDocument();
      expect(screen.getByText(/type match/i)).toBeInTheDocument();
    });

    it('shows a stub warning when a candidate has is_stub true', () => {
      mockWikidata({ hasSearched: true, candidates: [makeCandidate({ is_stub: true })] });
      renderPicker();

      expect(screen.getByRole('note')).toHaveTextContent(/stub/i);
    });

    it('shows a "type may differ" indicator when type_matches is false', () => {
      mockWikidata({ hasSearched: true, candidates: [makeCandidate({ type_matches: false })] });
      renderPicker();

      expect(screen.getByText(/type may differ/i)).toBeInTheDocument();
      expect(screen.queryByText(/^type match$/i)).not.toBeInTheDocument();
    });

    it('never checks a radio unless selectedCandidate matches its qid — the caller controls selection', () => {
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
      renderPicker({ selectedCandidate: null });

      expect((screen.getByRole('radio') as HTMLInputElement).checked).toBe(false);
    });

    it('checks the radio matching the controlled selectedCandidate', () => {
      const candidate = makeCandidate({ qid: 'Q00000002' });
      mockWikidata({ hasSearched: true, candidates: [candidate] });
      renderPicker({ selectedCandidate: candidate });

      expect((screen.getByRole('radio') as HTMLInputElement).checked).toBe(true);
      expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
    });
  });

  describe('Selection callback', () => {
    it('calls onSelectCandidate with the chosen candidate when a radio is clicked', () => {
      const candidate = makeCandidate({ qid: 'Q00000003', label: 'Test Person Three' });
      mockWikidata({ hasSearched: true, candidates: [candidate] });
      const { onSelectCandidate } = renderPicker();

      fireEvent.click(screen.getByRole('radio'));

      expect(onSelectCandidate).toHaveBeenCalledWith(candidate);
    });

    it('calls onSelectCandidate(null) when the "Grounded to" chip is cleared', () => {
      const candidate = makeCandidate({ qid: 'Q00000004', label: 'Test Person Four' });
      mockWikidata({ hasSearched: true, candidates: [candidate] });
      const { onSelectCandidate } = renderPicker({ selectedCandidate: candidate });

      fireEvent.click(
        screen.getByRole('button', { name: /remove grounding to test person four/i })
      );

      expect(onSelectCandidate).toHaveBeenLastCalledWith(null);
    });
  });

  describe('Stale search discard', () => {
    it('calls onSelectCandidate(null) and resets the search when name changes', () => {
      const wikidata = mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
      const onSelectCandidate = vi.fn();
      const { rerender } = render(
        <WikidataGroundingPicker
          name="Test Person"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={onSelectCandidate}
        />
      );
      onSelectCandidate.mockClear();
      wikidata.reset.mockClear();

      rerender(
        <WikidataGroundingPicker
          name="Different Name"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={onSelectCandidate}
        />
      );

      expect(onSelectCandidate).toHaveBeenCalledWith(null);
      expect(wikidata.reset).toHaveBeenCalled();
    });
  });

  describe('No match / unavailable states', () => {
    it('renders a distinct "no matching entries" message', () => {
      mockWikidata({ hasSearched: true, unavailable: false, candidates: [] });
      renderPicker();

      expect(screen.getByText(/no matching entries found/i)).toBeInTheDocument();
    });

    it('renders a distinct "could not reach Wikidata" message when unavailable', () => {
      mockWikidata({ hasSearched: true, unavailable: true, candidates: [] });
      renderPicker();

      expect(screen.getByText(/couldn.t reach wikidata/i)).toBeInTheDocument();
      expect(screen.queryByText(/no matching entries found/i)).not.toBeInTheDocument();
    });
  });

  describe('disabled prop', () => {
    it('disables the radio inputs and the remove-grounding button', () => {
      const candidate = makeCandidate();
      mockWikidata({ hasSearched: true, candidates: [candidate] });
      renderPicker({ selectedCandidate: candidate, disabled: true });

      expect(screen.getByRole('radio')).toBeDisabled();
      expect(
        screen.getByRole('button', { name: /remove grounding to test person/i })
      ).toBeDisabled();
    });
  });

  describe('Customization props (for the re-link dialog)', () => {
    it('renders a custom heading and hides the "— optional" qualifier when optional=false', () => {
      renderPicker({ heading: 'Wikidata matches', optional: false });

      expect(screen.getByText('Wikidata matches')).toBeInTheDocument();
      expect(screen.queryByText(/— optional/)).not.toBeInTheDocument();
    });

    it('hides the "Create without grounding" skip affordance when allowSkip=false', () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      renderPicker({ allowSkip: false });

      expect(
        screen.queryByRole('button', { name: /create without grounding/i })
      ).not.toBeInTheDocument();
    });

    it('shows the "Create without grounding" skip affordance by default', () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      renderPicker();

      expect(
        screen.getByRole('button', { name: /create without grounding/i })
      ).toBeInTheDocument();
    });
  });
});
