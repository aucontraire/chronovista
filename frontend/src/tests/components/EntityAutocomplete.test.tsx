/**
 * EntityAutocomplete — batch-correction single-select surface (FR-039).
 *
 * Feature 062 needed a multi-select entity picker for the videos list filter
 * panel. It got a NEW component (`EntityMultiSelect`) rather than a
 * generalisation of this one, because this component does not own its query —
 * its input is driven by a `searchText` prop from the parent correction field —
 * and it links exactly one entity.
 *
 * So the strongest form of "do not regress the batch surface" is that this file
 * was never edited. These tests pin the contract anyway: the next person
 * tempted to fold the two components together will find out here rather than in
 * production.
 *
 * There were no tests for this component before Feature 062.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EntityAutocomplete } from '../../components/batch/EntityAutocomplete';
import type { EntityOption } from '../../components/batch/EntityAutocomplete';

const RESULTS = [
  {
    entity_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    canonical_name: 'Ada Lovelace',
    entity_type: 'person',
  },
  {
    entity_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    canonical_name: 'Chomsky Hierarchy',
    entity_type: 'technical_term',
  },
];

vi.mock('../../hooks/useEntitySearch', () => ({
  useEntitySearch: (search: string) => ({
    entities: search.trim().length >= 2 ? RESULTS : [],
    isLoading: false,
    isBelowMinChars: search.trim().length < 2,
    isError: false,
  }),
}));

const SELECTED: EntityOption = {
  id: RESULTS[0]!.entity_id,
  name: RESULTS[0]!.canonical_name,
  type: 'person',
};

describe('EntityAutocomplete — batch correction contract (FR-039)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('parent-driven query', () => {
    it('takes its search text from the parent, not from its own state', () => {
      // This is the property that makes it unsuitable as a filter picker: the
      // input reflects the correction field the user is editing elsewhere.
      render(
        <EntityAutocomplete
          searchText="Chomsky"
          selectedEntity={null}
          onEntitySelect={vi.fn()}
        />
      );
      expect(screen.getByRole('combobox')).toHaveValue('Chomsky');
    });

    it('shows suggestions once the parent text reaches the minimum length', () => {
      render(
        <EntityAutocomplete
          searchText="Ch"
          selectedEntity={null}
          onEntitySelect={vi.fn()}
        />
      );
      expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    });

    it('shows none below the minimum length', () => {
      render(
        <EntityAutocomplete
          searchText="C"
          selectedEntity={null}
          onEntitySelect={vi.fn()}
        />
      );
      expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    });
  });

  describe('single selection', () => {
    it('reports the chosen entity to the parent', async () => {
      const user = userEvent.setup();
      const onEntitySelect = vi.fn();
      render(
        <EntityAutocomplete
          searchText="Chomsky"
          selectedEntity={null}
          onEntitySelect={onEntitySelect}
        />
      );

      await user.click(screen.getByText('Ada Lovelace'));

      expect(onEntitySelect).toHaveBeenCalledTimes(1);
      expect(onEntitySelect.mock.calls[0]?.[0]).toMatchObject({
        id: RESULTS[0]!.entity_id,
        name: 'Ada Lovelace',
      });
    });

    it('renders exactly one selection, never a set', () => {
      // The contract this component keeps and EntityMultiSelect deliberately
      // does not: one entity, cleared with null rather than removed by id.
      render(
        <EntityAutocomplete
          searchText=""
          selectedEntity={SELECTED}
          onEntitySelect={vi.fn()}
        />
      );
      expect(screen.getAllByText('Ada Lovelace')).toHaveLength(1);
    });

    it('clears with null rather than an id', async () => {
      const user = userEvent.setup();
      const onEntitySelect = vi.fn();
      render(
        <EntityAutocomplete
          searchText=""
          selectedEntity={SELECTED}
          onEntitySelect={onEntitySelect}
        />
      );

      const clear = screen
        .getAllByRole('button')
        .find((button) => /unlink|remove|clear/i.test(button.getAttribute('aria-label') ?? ''));
      expect(clear).toBeDefined();
      await user.click(clear!);

      expect(onEntitySelect).toHaveBeenCalledWith(null);
    });
  });

  describe('batch-specific affordances', () => {
    it('disables every control when the parent says so', () => {
      render(
        <EntityAutocomplete
          searchText="Chomsky"
          selectedEntity={null}
          onEntitySelect={vi.fn()}
          disabled
        />
      );
      expect(screen.getByRole('combobox')).toBeDisabled();
    });

    it('surfaces the replacement-text mismatch warning', () => {
      // `hasMismatch` exists only for the correction workflow — the replacement
      // text no longer matches the linked entity's name. A filter picker has no
      // such concept, which is the clearest sign these are two components.
      render(
        <EntityAutocomplete
          searchText="Chomskey"
          selectedEntity={SELECTED}
          onEntitySelect={vi.fn()}
          hasMismatch
        />
      );
      expect(screen.getByText(/match/i)).toBeInTheDocument();
    });
  });
});
