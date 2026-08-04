/**
 * Every ARIA combobox must set `autoComplete="off"`.
 *
 * These components own their suggestion listbox. Without the attribute the
 * browser stacks its own form-history dropdown on top of that listbox — two
 * competing lists over one input, and the native one replays whatever was typed
 * into the field before, on a surface the app has no control over.
 *
 * Reported from a demo recording: focusing the entity filter with an empty
 * input surfaced previously typed searches, which the app itself cannot do (it
 * requires two characters before it suggests anything).
 *
 * One test per combobox rather than a shared loop, because each has a different
 * mock surface — and a loop that silently skipped a component would defeat the
 * purpose.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EntityMultiSelect } from '../../components/EntityMultiSelect';
import { EntityAutocomplete } from '../../components/batch/EntityAutocomplete';

vi.mock('../../hooks/useEntitySearch', () => ({
  useEntitySearch: () => ({
    entities: [],
    isLoading: false,
    isBelowMinChars: true,
    isError: false,
  }),
}));

describe('ARIA comboboxes suppress the browser autofill dropdown', () => {
  it('EntityMultiSelect — the videos-list entity filter', () => {
    render(
      <EntityMultiSelect
        selected={[]}
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        max={10}
        label="Mentions all of"
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('autocomplete', 'off');
    // The pairing is the point: a component declaring it owns a listbox must
    // not also invite the browser to draw one.
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
  });

  it('EntityAutocomplete — the batch-correction entity picker', () => {
    render(
      <EntityAutocomplete
        searchText=""
        selectedEntity={null}
        onEntitySelect={vi.fn()}
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
  });
});
