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
 *
 * Feature 079 (US3) property rendering (image, relations, social links,
 * display-only reference blocks) is covered in a separate describe block
 * below; `useWikidataEntityMap` is mocked the same way as the other data
 * hooks. `renderSection` wraps in a `MemoryRouter` so the relation-link
 * assertions (`<Link>` to a local entity page) work without extra setup.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks — must be declared before component imports (vi.mock hoisting)
// ---------------------------------------------------------------------------

vi.mock('@/hooks/useDebounce', () => ({
  useDebounce: (value: unknown) => value,
}));

vi.mock('@/hooks/useEntityMentions', () => ({
  useWikidataCandidates: vi.fn(),
  useWikidataEntityMap: vi.fn(),
}));

vi.mock('@/hooks/useRegroundEntity', () => ({
  useRegroundEntity: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { EntityEnrichmentSection } from '../EntityEnrichmentSection';
import type { EntityEnrichmentSectionProps } from '../EntityEnrichmentSection';
import { useWikidataCandidates, useWikidataEntityMap } from '@/hooks/useEntityMentions';
import { useRegroundEntity } from '@/hooks/useRegroundEntity';
import type { EntityEnrichment, EntityPropertyValue, WikidataCandidate } from '@/api/entityMentions';
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

function mockWikidataEntityMap(
  overrides: { data?: Record<string, { entity_id: string; canonical_name: string }> } = {}
) {
  const hook = {
    data: {},
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
  (useWikidataEntityMap as Mock).mockReturnValue(hook);
  return hook;
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
  return render(
    <MemoryRouter>
      <EntityEnrichmentSection {...props} />
    </MemoryRouter>
  );
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
    mockWikidataEntityMap();
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
    mockWikidataEntityMap();
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

// ---------------------------------------------------------------------------
// Property rendering (Feature 079, US3)
// ---------------------------------------------------------------------------

function propBlock(
  values: string[],
  overrides: Partial<EntityPropertyValue> = {}
): EntityPropertyValue {
  return {
    values,
    source: 'wikidata',
    set_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('EntityEnrichmentSection — property rendering (Feature 079, US3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWikidata();
    mockReground();
    mockWikidataEntityMap();
    // jsdom defines navigator.clipboard as a getter-only property — redefine
    // it so we can spy on writeText (mirrors MergeResultBanner's tests).
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  describe('portrait image', () => {
    it('renders a portrait when an `image` property is present', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { image: propBlock(['Placeholder_File.jpg']) },
        }),
      });

      const img = screen.getByRole('img', { name: 'Test Person' });
      expect(img).toHaveAttribute(
        'src',
        expect.stringContaining('/images/entities/ent-00000000-0000-0000-0000-000000000001')
      );
    });

    it('appends the image `set_at` as a `?v=` cache-buster', () => {
      // The version changes only on (re-)enrichment, so the backend's immutable cache still
      // applies, while a stale placeholder pinned during an upstream rate-limit blip is bypassed.
      renderSection({
        enrichment: makeEnrichment({
          properties: {
            image: propBlock(['Placeholder_File.jpg'], { set_at: '2026-02-03T04:05:06Z' }),
          },
        }),
      });

      const img = screen.getByRole('img', { name: 'Test Person' });
      expect(img.getAttribute('src')).toContain(
        `?v=${encodeURIComponent('2026-02-03T04:05:06Z')}`
      );
    });

    it('renders nothing when no `image` property is present', () => {
      renderSection({
        enrichment: makeEnrichment({ properties: { occupation: propBlock(['Placeholder Job']) } }),
      });

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('renders nothing after the portrait fails to load', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { image: propBlock(['Placeholder_File.jpg']) },
        }),
      });

      const img = screen.getByRole('img', { name: 'Test Person' });
      fireEvent.error(img);

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });
  });

  describe('relation properties', () => {
    it('links a relation value to its local entity page when the QID resolves', () => {
      mockWikidataEntityMap({
        data: { Q00000101: { entity_id: 'ent-local-match', canonical_name: 'Placeholder Spouse' } },
      });
      renderSection({
        enrichment: makeEnrichment({
          properties: {
            spouse: propBlock(['Placeholder Spouse'], { qids: ['Q00000101'] }),
          },
        }),
      });

      const link = screen.getByRole('link', { name: 'Placeholder Spouse' });
      expect(link).toHaveAttribute('href', '/entities/ent-local-match');
    });

    it('links a relation value to wikidata.org when the QID does not resolve locally', () => {
      mockWikidataEntityMap({ data: {} });
      renderSection({
        enrichment: makeEnrichment({
          properties: {
            father: propBlock(['Placeholder Father'], { qids: ['Q00000202'] }),
          },
        }),
      });

      const link = screen.getByRole('link', { name: 'Placeholder Father' });
      expect(link).toHaveAttribute('href', 'https://www.wikidata.org/wiki/Q00000202');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('renders plain text when a relation value has no aligned QID', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { sibling: propBlock(['Placeholder Sibling']) },
        }),
      });

      expect(screen.getByText('Placeholder Sibling')).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Placeholder Sibling' })).not.toBeInTheDocument();
    });

    it('resolves each value against its positionally-aligned QID independently', () => {
      mockWikidataEntityMap({
        data: { Q00000301: { entity_id: 'ent-local-match', canonical_name: 'Matched' } },
      });
      renderSection({
        enrichment: makeEnrichment({
          properties: {
            child: propBlock(['Matched Child', 'Unmatched Child'], {
              qids: ['Q00000301', 'Q00000302'],
            }),
          },
        }),
      });

      expect(screen.getByRole('link', { name: 'Matched Child' })).toHaveAttribute(
        'href',
        '/entities/ent-local-match'
      );
      expect(screen.getByRole('link', { name: 'Unmatched Child' })).toHaveAttribute(
        'href',
        'https://www.wikidata.org/wiki/Q00000302'
      );
    });
  });

  describe('social/web properties', () => {
    it('links a known social property via its fixed URL pattern', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { x_username: propBlock(['placeholderhandle']) },
        }),
      });

      const link = screen.getByRole('link', { name: /x username: placeholderhandle/i });
      expect(link).toHaveAttribute('href', 'https://x.com/placeholderhandle');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('builds the mastodon URL from a user@server address', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { mastodon_address: propBlock(['placeholderuser@example.social']) },
        }),
      });

      const link = screen.getByRole('link', { name: /mastodon address/i });
      expect(link).toHaveAttribute('href', 'https://example.social/@placeholderuser');
    });

    it('renders plain text (not a link) for a malformed mastodon address', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { mastodon_address: propBlock(['not-a-valid-address']) },
        }),
      });

      expect(screen.getByText(/mastodon address: not-a-valid-address/i)).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /mastodon address/i })).not.toBeInTheDocument();
    });
  });

  describe('display-only reference blocks (wikidata_description / wikidata_aliases)', () => {
    it('renders wikidata_description with a Copy control and no editable input', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { wikidata_description: propBlock(['a placeholder reference description']) },
        }),
      });

      expect(screen.getByText('a placeholder reference description')).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /copy wikidata description/i })
      ).toBeInTheDocument();
      // Display-only: no textbox for this value anywhere in the section.
      expect(
        screen.queryByRole('textbox', { name: /wikidata description/i })
      ).not.toBeInTheDocument();
    });

    it('joins multiple wikidata_aliases values with a comma', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { wikidata_aliases: propBlock(['Alias One', 'Alias Two']) },
        }),
      });

      expect(screen.getByText('Alias One, Alias Two')).toBeInTheDocument();
    });

    it('copies the reference text to the clipboard and shows a confirmation', async () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { wikidata_description: propBlock(['a placeholder reference description']) },
        }),
      });

      const button = screen.getByRole('button', { name: /copy wikidata description/i });
      fireEvent.click(button);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'a placeholder reference description'
      );
      await waitFor(() => expect(button).toHaveTextContent(/copied/i));
    });

    it('never renders a control that edits the curated description', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { wikidata_description: propBlock(['a placeholder reference description']) },
        }),
      });

      // The only editable description field in this component belongs to the
      // "Change link" editor, which is closed by default (T022 requirement:
      // reference blocks offer no control that edits the curated description).
      expect(screen.queryByLabelText(/^description$/i)).not.toBeInTheDocument();
    });
  });

  describe('clean empty/ungrounded degradation', () => {
    it('renders none of the new sections when the entity is ungrounded', () => {
      renderSection();

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
      expect(screen.queryByText('Relations')).not.toBeInTheDocument();
      expect(screen.queryByText('Social & web')).not.toBeInTheDocument();
      expect(screen.queryByText(/wikidata reference/i)).not.toBeInTheDocument();
      expect(screen.getByTestId('enrichment-not-grounded')).toBeInTheDocument();
    });

    it('omits a section entirely when its key is absent, without stray empty labels', () => {
      renderSection({
        enrichment: makeEnrichment({
          properties: { occupation: propBlock(['Placeholder Occupation']) },
        }),
      });

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
      expect(screen.queryByText('Relations')).not.toBeInTheDocument();
      expect(screen.queryByText('Social & web')).not.toBeInTheDocument();
      expect(screen.queryByText(/wikidata reference/i)).not.toBeInTheDocument();
      expect(screen.getByText('Placeholder Occupation')).toBeInTheDocument();
    });
  });
});
