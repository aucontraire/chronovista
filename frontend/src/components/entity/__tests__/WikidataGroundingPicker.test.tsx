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

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
    canShowMore?: boolean;
    isFetchingMore?: boolean;
    showMore?: Mock;
    resolveByQid?: Mock;
    isResolvingQid?: boolean;
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
    canShowMore: false,
    isFetchingMore: false,
    showMore: vi.fn(),
    resolveByQid: vi.fn(),
    isResolvingQid: false,
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

    it('clears the pasted QID field and any resolve result when name changes', () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      const onSelectCandidate = vi.fn();
      const { rerender } = render(
        <WikidataGroundingPicker
          name="Test Person"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={onSelectCandidate}
        />
      );

      fireEvent.change(screen.getByLabelText(/paste a wikidata qid/i), {
        target: { value: 'Q42' },
      });
      expect(screen.getByLabelText(/paste a wikidata qid/i)).toHaveValue('Q42');

      rerender(
        <WikidataGroundingPicker
          name="Different Name"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={onSelectCandidate}
        />
      );

      expect(screen.getByLabelText(/paste a wikidata qid/i)).toHaveValue('');
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

    it('disables the QID input and resolve button', () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      renderPicker({ disabled: true });

      expect(screen.getByLabelText(/paste a wikidata qid/i)).toBeDisabled();
      expect(screen.getByRole('button', { name: /use this qid/i })).toBeDisabled();
    });
  });

  describe('Show more pagination', () => {
    it('shows a "Show more" button when canShowMore is true', () => {
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()], canShowMore: true });
      renderPicker();

      expect(screen.getByRole('button', { name: /^show more$/i })).toBeInTheDocument();
    });

    it('hides the "Show more" button once canShowMore is false and no fetch is in flight', () => {
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()], canShowMore: false });
      renderPicker();

      expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
    });

    it('calls showMore when clicked, appending the next page', () => {
      const hook = mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate()],
        canShowMore: true,
      });
      renderPicker();

      fireEvent.click(screen.getByRole('button', { name: /^show more$/i }));

      expect(hook.showMore).toHaveBeenCalled();
    });

    it('shows a spinner and disables the button while isFetchingMore, even if canShowMore has gone false', () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate()],
        canShowMore: false,
        isFetchingMore: true,
      });
      renderPicker();

      const button = screen.getByRole('button', { name: /loading more/i });
      expect(button).toBeDisabled();
    });

    it('does not show "Show more" before any candidates are rendered', () => {
      mockWikidata({ hasSearched: true, candidates: [], canShowMore: true });
      renderPicker();

      expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
    });
  });

  describe('QID paste fallback', () => {
    function pasteQid(value: string) {
      fireEvent.change(screen.getByLabelText(/paste a wikidata qid/i), {
        target: { value },
      });
    }

    it('keeps the resolve button disabled until the QID format is valid', () => {
      renderPicker();

      pasteQid('not-a-qid');
      expect(screen.getByRole('button', { name: /use this qid/i })).toBeDisabled();

      pasteQid('Q42');
      expect(screen.getByRole('button', { name: /use this qid/i })).not.toBeDisabled();
    });

    it('rejects a leading-zero QID as invalid format', () => {
      renderPicker();

      pasteQid('Q007');
      expect(screen.getByRole('button', { name: /use this qid/i })).toBeDisabled();
    });

    it('rejects a non-wikidata URL as invalid, with no resolve call', () => {
      const resolveByQid = vi.fn();
      mockWikidata({ resolveByQid });
      renderPicker();

      pasteQid('https://example.com/wiki/Q42');
      expect(screen.getByRole('button', { name: /use this qid/i })).toBeDisabled();

      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));
      expect(resolveByQid).not.toHaveBeenCalled();
    });

    it('rejects a plain number as invalid', () => {
      renderPicker();

      pasteQid('42');
      expect(screen.getByRole('button', { name: /use this qid/i })).toBeDisabled();
    });

    it('extracts the QID from a pasted wikidata.org item URL and resolves with it', async () => {
      const candidate = makeCandidate({ qid: 'Q42', label: 'Placeholder Match' });
      const resolveByQid = vi.fn().mockResolvedValue({ candidate, unavailable: false });
      mockWikidata({ resolveByQid });
      const { onSelectCandidate } = renderPicker();

      pasteQid('https://www.wikidata.org/wiki/Q42');
      expect(screen.getByRole('button', { name: /use this qid/i })).not.toBeDisabled();

      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));

      expect(resolveByQid).toHaveBeenCalledWith('Q42');
      await waitFor(() => {
        expect(onSelectCandidate).toHaveBeenCalledWith(candidate);
      });
    });

    it('resolves and selects the candidate on success', async () => {
      const candidate = makeCandidate({ qid: 'Q42', label: 'Placeholder Match' });
      const resolveByQid = vi.fn().mockResolvedValue({ candidate, unavailable: false });
      mockWikidata({ resolveByQid });
      const { onSelectCandidate } = renderPicker();

      pasteQid('Q42');
      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));

      expect(resolveByQid).toHaveBeenCalledWith('Q42');
      await waitFor(() => {
        expect(onSelectCandidate).toHaveBeenCalledWith(candidate);
      });
    });

    it('resolves on pressing Enter in the QID field', async () => {
      const candidate = makeCandidate({ qid: 'Q42', label: 'Placeholder Match' });
      const resolveByQid = vi.fn().mockResolvedValue({ candidate, unavailable: false });
      mockWikidata({ resolveByQid });
      const { onSelectCandidate } = renderPicker();

      pasteQid('Q42');
      fireEvent.keyDown(screen.getByLabelText(/paste a wikidata qid/i), { key: 'Enter' });

      await waitFor(() => {
        expect(onSelectCandidate).toHaveBeenCalledWith(candidate);
      });
    });

    it('shows a "no item" message when the QID does not resolve to a candidate', async () => {
      const resolveByQid = vi.fn().mockResolvedValue({ candidate: null, unavailable: false });
      mockWikidata({ resolveByQid });
      renderPicker();

      pasteQid('Q999999999');
      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));

      expect(await screen.findByText(/no wikidata item with that id/i)).toBeInTheDocument();
    });

    it('shows the unavailable message when the QID lookup itself fails', async () => {
      const resolveByQid = vi.fn().mockResolvedValue({ candidate: null, unavailable: true });
      mockWikidata({ resolveByQid });
      renderPicker();

      pasteQid('Q42');
      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));

      expect(await screen.findByText(/couldn.t reach wikidata/i)).toBeInTheDocument();
    });
  });

  describe('Invalid-format hint', () => {
    function pasteQid(value: string) {
      fireEvent.change(screen.getByLabelText(/paste a wikidata qid/i), {
        target: { value },
      });
    }

    it('shows a hint when the field is non-empty but not a valid QID or URL', () => {
      renderPicker();

      pasteQid('not-a-qid');

      expect(
        screen.getByText(/enter a wikidata qid like q42, or paste its wikidata\.org link/i)
      ).toBeInTheDocument();
    });

    it('renders the hint with the same amber warning treatment as the post-resolve messages', () => {
      renderPicker();

      pasteQid('not-a-qid');

      const hint = screen.getByText(
        /enter a wikidata qid like q42, or paste its wikidata\.org link/i
      );
      expect(hint.className).toContain('text-amber-700');
      expect(hint.className).not.toContain('text-gray-500');
    });

    it('hides the hint when the field is empty', () => {
      renderPicker();

      expect(screen.queryByText(/enter a wikidata qid like q42/i)).not.toBeInTheDocument();
    });

    it('hides the hint once the field holds a valid QID', () => {
      renderPicker();

      pasteQid('not-a-qid');
      expect(screen.getByText(/enter a wikidata qid like q42/i)).toBeInTheDocument();

      pasteQid('Q42');
      expect(screen.queryByText(/enter a wikidata qid like q42/i)).not.toBeInTheDocument();
    });

    it('hides the hint once the field holds a valid wikidata.org URL', () => {
      renderPicker();

      pasteQid('https://www.wikidata.org/wiki/Q42');
      expect(screen.queryByText(/enter a wikidata qid like q42/i)).not.toBeInTheDocument();
    });

    it('does not show at the same time as the post-resolve "no item" message', async () => {
      const resolveByQid = vi.fn().mockResolvedValue({ candidate: null, unavailable: false });
      mockWikidata({ resolveByQid });
      renderPicker();

      pasteQid('Q999999999');
      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));
      expect(await screen.findByText(/no wikidata item with that id/i)).toBeInTheDocument();

      // Typing an invalid value afterward clears the stale result message and
      // shows the hint instead — never both at once.
      pasteQid('not-a-qid');
      expect(screen.queryByText(/no wikidata item with that id/i)).not.toBeInTheDocument();
      expect(screen.getByText(/enter a wikidata qid like q42/i)).toBeInTheDocument();
    });
  });

  describe('onPendingInvalidQidChange', () => {
    function pasteQid(value: string) {
      fireEvent.change(screen.getByLabelText(/paste a wikidata qid/i), {
        target: { value },
      });
    }

    it('fires with the trimmed typed text once it fails to resolve to a QID', () => {
      const onPendingInvalidQidChange = vi.fn();
      renderPicker({ onPendingInvalidQidChange });

      pasteQid('  not-a-qid  ');

      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('not-a-qid');
    });

    it('fires with "" when the field is empty', () => {
      const onPendingInvalidQidChange = vi.fn();
      renderPicker({ onPendingInvalidQidChange });

      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('');
    });

    it('fires with "" once the field holds a valid QID or URL — a valid-but-unapplied QID is not "invalid"', () => {
      const onPendingInvalidQidChange = vi.fn();
      renderPicker({ onPendingInvalidQidChange });

      pasteQid('not-a-qid');
      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('not-a-qid');

      pasteQid('Q42');
      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('');
    });

    it('fires with "" after a successful resolve clears the field', async () => {
      const candidate = makeCandidate({ qid: 'Q42', label: 'Placeholder Match' });
      const resolveByQid = vi.fn().mockResolvedValue({ candidate, unavailable: false });
      const onPendingInvalidQidChange = vi.fn();
      mockWikidata({ resolveByQid });
      renderPicker({ onPendingInvalidQidChange });

      pasteQid('not-a-qid');
      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('not-a-qid');

      pasteQid('Q42');
      fireEvent.click(screen.getByRole('button', { name: /use this qid/i }));

      await waitFor(() => {
        expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('');
      });
    });

    it('fires with "" after a name/type change resets the field', () => {
      const onPendingInvalidQidChange = vi.fn();
      const { rerender } = render(
        <WikidataGroundingPicker
          name="Test Person"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={vi.fn()}
          onPendingInvalidQidChange={onPendingInvalidQidChange}
        />
      );

      pasteQid('not-a-qid');
      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('not-a-qid');

      rerender(
        <WikidataGroundingPicker
          name="Different Name"
          entityType="person"
          selectedCandidate={null}
          onSelectCandidate={vi.fn()}
          onPendingInvalidQidChange={onPendingInvalidQidChange}
        />
      );

      expect(onPendingInvalidQidChange).toHaveBeenLastCalledWith('');
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
