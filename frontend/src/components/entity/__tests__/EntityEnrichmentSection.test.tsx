/**
 * Tests for EntityEnrichmentSection's "Change link" re-grounding dialog
 * (Feature 073, US1).
 *
 * WikidataGroundingPicker's own contract (candidate rendering/selection,
 * auto-search, disabled/optional/allowSkip props) is covered by
 * `WikidataGroundingPicker.test.tsx`. This file covers the dialog that wraps
 * it:
 * - "Change link" opens an editor with a search field, the picker, and an
 *   editable description field
 * - FR-011: selecting a candidate pre-fills the description field with that
 *   candidate's description; when the candidate has none, the field is left
 *   EMPTY — never falling back to the entity's current (possibly non-empty)
 *   description
 * - The pre-fill never overwrites text the user already typed
 * - Confirm is disabled until a candidate is selected
 * - Confirm calls `useRegroundEntity` with `{ approved_identifier, description }`
 *   matching the selected candidate and the confirmed description text
 * - A successful confirm closes the editor; a failed one keeps it open with
 *   the user's input preserved
 *
 * `useDebounce` is mocked as a pass-through identity function so the
 * picker's auto-search effect fires synchronously with `fireEvent`, and
 * `useWikidataCandidates` / `useRegroundEntity` are mocked at the hook
 * boundary, mirroring `CreateEntityModal.candidates.test.tsx`.
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

vi.mock('@/hooks/useRegroundEntity', () => ({
  useRegroundEntity: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { EntityEnrichmentSection } from '../EntityEnrichmentSection';
import type { EntityEnrichmentSectionProps } from '../EntityEnrichmentSection';
import { useWikidataCandidates } from '@/hooks/useEntityMentions';
import { useRegroundEntity } from '@/hooks/useRegroundEntity';
import type { EntityEnrichment, WikidataCandidate } from '@/api/entityMentions';
import type { Mock } from 'vitest';

// ---------------------------------------------------------------------------
// DOM query helpers
// ---------------------------------------------------------------------------

const getDescriptionField = () =>
  screen.getByRole('textbox', { name: /description/i }) as HTMLTextAreaElement;

const getConfirmButton = () => screen.getByRole('button', { name: /confirm link/i });

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

function mockWikidata(
  overrides: {
    candidates?: WikidataCandidate[];
    unavailable?: boolean;
    hasSearched?: boolean;
    isLoading?: boolean;
  } = {}
) {
  const hook = {
    candidates: [],
    unavailable: false,
    hasSearched: true,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    search: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
  (useWikidataCandidates as Mock).mockReturnValue(hook);
  return hook;
}

function mockReground(overrides: { mutate?: Mock; isPending?: boolean } = {}) {
  const mutation = {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
  (useRegroundEntity as Mock).mockReturnValue(mutation);
  return mutation;
}

function makeEnrichment(overrides: Partial<EntityEnrichment> = {}): EntityEnrichment {
  return {
    grounded: true,
    properties: {},
    identifiers: [
      { source: 'wikidata', id: 'Q00000001', url: 'https://www.wikidata.org/wiki/Q00000001', verified: true },
    ],
    ...overrides,
  };
}

function renderSection(overrides: Partial<EntityEnrichmentSectionProps> = {}) {
  const props: EntityEnrichmentSectionProps = {
    entityId: 'ent-00000000-0000-0000-0000-000000000001',
    entityType: 'person',
    canonicalName: 'Test Person',
    ...overrides,
  };
  return render(<EntityEnrichmentSection {...props} />);
}

function openEditor() {
  fireEvent.click(screen.getByRole('button', { name: /change wikidata link/i }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EntityEnrichmentSection — Change link (Feature 073, US1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWikidata();
    mockReground();
  });

  it('renders a "Change link" button', () => {
    renderSection();
    expect(screen.getByRole('button', { name: /change wikidata link/i })).toBeInTheDocument();
  });

  it('opens an editor with a search field, the picker, and a description field', () => {
    mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
    renderSection();

    openEditor();

    expect(screen.getByLabelText(/search wikidata for/i)).toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: /wikidata candidates/i })).toBeInTheDocument();
    expect(getDescriptionField()).toBeInTheDocument();
  });

  it('pre-fills the search field with the entity’s current canonical name', () => {
    renderSection({ canonicalName: 'Test Person' });
    openEditor();

    expect(screen.getByLabelText(/search wikidata for/i)).toHaveValue('Test Person');
  });

  it('disables Confirm until a candidate is selected', () => {
    mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
    renderSection();
    openEditor();

    expect(getConfirmButton()).toBeDisabled();

    fireEvent.click(screen.getByRole('radio'));

    expect(getConfirmButton()).not.toBeDisabled();
  });

  describe('FR-011: description pre-fill', () => {
    it('pre-fills an empty description with the selected candidate’s description', () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: 'a placeholder description' })],
      });
      renderSection();
      openEditor();

      fireEvent.click(screen.getByRole('radio'));

      expect(getDescriptionField()).toHaveValue('a placeholder description');
    });

    it('leaves the description EMPTY when the selected candidate has no description — never falls back to the entity’s current description', () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: null })],
      });
      renderSection();
      openEditor();

      fireEvent.click(screen.getByRole('radio'));

      expect(getDescriptionField()).toHaveValue('');
    });

    it('does not overwrite a description the user already typed', () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: 'a placeholder description' })],
      });
      renderSection();
      openEditor();

      fireEvent.change(getDescriptionField(), { target: { value: 'My own description' } });
      fireEvent.click(screen.getByRole('radio'));

      expect(getDescriptionField()).toHaveValue('My own description');
    });
  });

  describe('Confirming the link', () => {
    it('calls useRegroundEntity with the selected candidate’s qid and the confirmed description', () => {
      const mutate = vi.fn();
      mockReground({ mutate });
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ qid: 'Q00000042', description: 'a placeholder description' })],
      });
      renderSection({ entityId: 'ent-00000000-0000-0000-0000-0000000000ab' });
      openEditor();

      fireEvent.click(screen.getByRole('radio'));
      fireEvent.change(getDescriptionField(), { target: { value: 'curator-confirmed text' } });
      fireEvent.click(getConfirmButton());

      expect(mutate).toHaveBeenCalledWith(
        {
          entityId: 'ent-00000000-0000-0000-0000-0000000000ab',
          data: {
            approved_identifier: { source: 'wikidata', id: 'Q00000042' },
            description: 'curator-confirmed text',
          },
        },
        expect.any(Object)
      );
    });

    it('closes the editor on a successful confirm', () => {
      const mutate = vi.fn((_vars, callbacks: { onSuccess?: () => void }) => {
        callbacks.onSuccess?.();
      });
      mockReground({ mutate });
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
      renderSection();
      openEditor();

      fireEvent.click(screen.getByRole('radio'));
      fireEvent.click(getConfirmButton());

      expect(screen.queryByLabelText(/search wikidata for/i)).not.toBeInTheDocument();
    });

    it('keeps the editor open and shows an error message when the mutation fails', () => {
      const mutate = vi.fn((_vars, callbacks: { onError?: (err: unknown) => void }) => {
        callbacks.onError?.({ type: 'server', message: 'boom', status: 404 });
      });
      mockReground({ mutate });
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
      renderSection();
      openEditor();

      fireEvent.click(screen.getByRole('radio'));
      fireEvent.click(getConfirmButton());

      expect(screen.getByRole('alert')).toHaveTextContent(/entity not found/i);
      // Editor stays open — the search field is still visible.
      expect(screen.getByLabelText(/search wikidata for/i)).toBeInTheDocument();
    });
  });

  describe('Cancel', () => {
    it('closes the editor without calling the mutation', () => {
      const mutate = vi.fn();
      mockReground({ mutate });
      renderSection();
      openEditor();

      fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

      expect(screen.queryByLabelText(/search wikidata for/i)).not.toBeInTheDocument();
      expect(mutate).not.toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// Refresh (Feature 073, US2, T018/T019)
// ---------------------------------------------------------------------------

describe('EntityEnrichmentSection — Refresh (Feature 073, US2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWikidata();
    mockReground();
  });

  it('is NOT shown when the entity is ungrounded (no enrichment at all)', () => {
    renderSection();
    expect(screen.queryByRole('button', { name: /refresh wikidata data/i })).not.toBeInTheDocument();
  });

  it('is NOT shown when enrichment has identifiers but none is a wikidata source', () => {
    renderSection({
      enrichment: makeEnrichment({
        identifiers: [{ source: 'dbpedia', id: 'Test_Person', url: 'https://dbpedia.org/page/Test_Person', verified: false }],
      }),
    });
    expect(screen.queryByRole('button', { name: /refresh wikidata data/i })).not.toBeInTheDocument();
  });

  it('is shown when the entity currently has a wikidata link', () => {
    renderSection({ enrichment: makeEnrichment() });
    expect(screen.getByRole('button', { name: /refresh wikidata data/i })).toBeInTheDocument();
  });

  it('fires the mutation with NO approved_identifier and NO description key — a refresh, not a re-link', () => {
    const mutate = vi.fn();
    mockReground({ mutate });
    renderSection({
      entityId: 'ent-00000000-0000-0000-0000-0000000000cd',
      enrichment: makeEnrichment(),
    });

    fireEvent.click(screen.getByRole('button', { name: /refresh wikidata data/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    const [variables] = mutate.mock.calls[0] as [{ entityId: string; data: Record<string, unknown> }];
    expect(variables.entityId).toBe('ent-00000000-0000-0000-0000-0000000000cd');
    expect(variables.data).not.toHaveProperty('approved_identifier');
    expect(variables.data).not.toHaveProperty('description');
  });

  it('does not open the "Change link" editor or the Wikidata picker', () => {
    renderSection({ enrichment: makeEnrichment() });

    fireEvent.click(screen.getByRole('button', { name: /refresh wikidata data/i }));

    expect(screen.queryByLabelText(/search wikidata for/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('radiogroup', { name: /wikidata candidates/i })).not.toBeInTheDocument();
  });

  it('does not alter the description field state', () => {
    // Opening the editor afterward should still show the untouched, freshly
    // reset description field (empty) — Refresh must not have written into
    // description state that the "Change link" editor also reads.
    renderSection({ enrichment: makeEnrichment() });

    fireEvent.click(screen.getByRole('button', { name: /refresh wikidata data/i }));
    openEditor();

    expect(getDescriptionField()).toHaveValue('');
  });

  it('disables the Refresh button while the mutation is pending — no double-submit', () => {
    mockReground({ isPending: true });
    renderSection({ enrichment: makeEnrichment() });

    expect(screen.getByRole('button', { name: /refresh wikidata data/i })).toBeDisabled();
  });

  it('shows an error message on a 400 (no current link to refresh)', () => {
    const mutate = vi.fn((_vars, callbacks: { onError?: (err: unknown) => void }) => {
      callbacks.onError?.({ type: 'server', message: 'boom', status: 400 });
    });
    mockReground({ mutate });
    renderSection({ enrichment: makeEnrichment() });

    fireEvent.click(screen.getByRole('button', { name: /refresh wikidata data/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/no current wikidata link/i);
  });

  it('shows a transient status message on success', () => {
    const mutate = vi.fn((_vars, callbacks: { onSuccess?: () => void }) => {
      callbacks.onSuccess?.();
    });
    mockReground({ mutate });
    renderSection({ enrichment: makeEnrichment() });

    fireEvent.click(screen.getByRole('button', { name: /refresh wikidata data/i }));

    expect(screen.getByRole('status')).toHaveTextContent(/refreshing wikidata facts/i);
  });
});
