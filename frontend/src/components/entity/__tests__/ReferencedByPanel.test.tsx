/**
 * ReferencedByPanel — grouping, attribution, links, and states (Feature 087).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ReferencedByPanel } from '../ReferencedByPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useReferencedBy', () => ({
  useReferencedBy: (...args: unknown[]) => hookMock(...args),
}));

const SUBJECT = '11111111-1111-4111-8111-111111111111';
const MEMBER_A = '22222222-2222-4222-8222-222222222222';
const MEMBER_B = '33333333-3333-4333-8333-333333333333';

function group(overrides: Record<string, unknown> = {}) {
  return {
    key: 'membership',
    label: 'Member',
    attribution: 'Listed by Wikidata as a member or part of this entity',
    members: [
      { entity_id: MEMBER_A, entity_type: 'person', canonical_name: 'Placeholder Person A' },
      { entity_id: MEMBER_B, entity_type: 'person', canonical_name: 'Placeholder Person B' },
    ],
    member_count: 2,
    ...overrides,
  };
}

function state(overrides: Record<string, unknown> = {}) {
  return { groups: [], isLoading: false, isError: false, error: null, ...overrides };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <ReferencedByPanel entityId={SUBJECT} />
    </MemoryRouter>
  );
}

describe('ReferencedByPanel', () => {
  beforeEach(() => hookMock.mockReset());

  it('renders each group with its label and attribution', () => {
    hookMock.mockReturnValue(
      state({
        groups: [
          group(),
          group({
            key: 'founder',
            label: 'Founder',
            attribution: 'Listed by Wikidata as a founder of this entity',
          }),
        ],
      })
    );
    renderPanel();

    expect(screen.getByRole('heading', { name: 'Referenced by' })).toBeInTheDocument();
    const membership = screen.getByTestId('referenced-by-group-membership');
    expect(within(membership).getByRole('heading', { name: 'Member' })).toBeInTheDocument();
    expect(
      within(membership).getByText('Listed by Wikidata as a member or part of this entity')
    ).toBeVisible();
    expect(screen.getByText('Listed by Wikidata as a founder of this entity')).toBeVisible();
  });

  it('renders member rows as links to the entity page', () => {
    hookMock.mockReturnValue(state({ groups: [group()] }));
    renderPanel();

    expect(screen.getByRole('link', { name: /Placeholder Person A/ })).toHaveAttribute(
      'href',
      `/entities/${MEMBER_A}`
    );
    expect(screen.getByRole('link', { name: /Placeholder Person B/ })).toHaveAttribute(
      'href',
      `/entities/${MEMBER_B}`
    );
  });

  it('shows "showing N of M" when the group is truncated', () => {
    hookMock.mockReturnValue(state({ groups: [group({ member_count: 7 })] }));
    renderPanel();
    expect(screen.getByText('Showing 2 of 7')).toBeInTheDocument();
  });

  it('omits the truncation note when all members are shown', () => {
    hookMock.mockReturnValue(state({ groups: [group()] }));
    renderPanel();
    expect(screen.queryByText(/Showing \d+ of \d+/)).not.toBeInTheDocument();
  });

  it('shows a loading state', () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    renderPanel();
    expect(screen.getByTestId('referenced-by-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('referenced-by-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('referenced-by-empty')).not.toBeInTheDocument();
  });

  it('shows a recoverable error state, distinct from empty', () => {
    hookMock.mockReturnValue(state({ isError: true }));
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent(/Couldn't load/);
    expect(screen.queryByTestId('referenced-by-empty')).not.toBeInTheDocument();
  });

  it('shows an empty state when nothing references the entity', () => {
    hookMock.mockReturnValue(state());
    renderPanel();
    expect(screen.getByTestId('referenced-by-empty')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
