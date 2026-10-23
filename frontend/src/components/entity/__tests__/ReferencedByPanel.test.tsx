/**
 * ReferencedByPanel — grouping, attribution, links, and states (Feature 087).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
      { entity_id: MEMBER_A, entity_type: 'person', canonical_name: 'Placeholder Person A', instance_of: [] },
      { entity_id: MEMBER_B, entity_type: 'person', canonical_name: 'Placeholder Person B', instance_of: [] },
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

  describe('type filter', () => {
    const member = (id: string, name: string, instance_of: string[]) => ({
      entity_id: id,
      entity_type: 'organization',
      canonical_name: name,
      instance_of,
    });
    const typedGroups = () => [
      group({
        members: [
          member('a', 'Placeholder Alpha', ['band']),
          member('b', 'Placeholder Beta', ['company']),
          member('c', 'Placeholder Gamma', ['band', 'company']),
          member('d', 'Placeholder Delta', []),
        ],
        member_count: 4,
      }),
      group({
        key: 'founder',
        label: 'Founder',
        members: [member('e', 'Placeholder Epsilon', ['school'])],
        member_count: 1,
      }),
    ];
    const filterGroup = () => within(screen.getByTestId('referenced-by-type-filter'));

    it('offers exactly the distinct present types plus All', () => {
      hookMock.mockReturnValue(state({ groups: typedGroups() }));
      renderPanel();
      const names = filterGroup()
        .getAllByRole('button')
        .map((b) => b.textContent);
      expect(names).toEqual(['All', 'band', 'company', 'school']);
    });

    it('narrows to a type, hides emptied groups, and restores on clear', async () => {
      const user = userEvent.setup();
      hookMock.mockReturnValue(state({ groups: typedGroups() }));
      renderPanel();

      await user.click(filterGroup().getByRole('button', { name: 'school' }));
      expect(filterGroup().getByRole('button', { name: 'school' })).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByText('Placeholder Epsilon')).toBeInTheDocument();
      expect(screen.queryByText('Placeholder Alpha')).not.toBeInTheDocument();
      expect(screen.queryByTestId('referenced-by-group-membership')).not.toBeInTheDocument();

      await user.click(filterGroup().getByRole('button', { name: 'All' }));
      expect(screen.getByText('Placeholder Alpha')).toBeInTheDocument();
      expect(screen.getByText('Placeholder Epsilon')).toBeInTheDocument();
      expect(screen.getByTestId('referenced-by-group-membership')).toBeInTheDocument();
    });

    it('matches a multi-valued member when any of its types is selected', async () => {
      const user = userEvent.setup();
      hookMock.mockReturnValue(state({ groups: typedGroups() }));
      renderPanel();

      await user.click(filterGroup().getByRole('button', { name: 'band' }));
      expect(screen.getByText('Placeholder Alpha')).toBeInTheDocument();
      expect(screen.getByText('Placeholder Gamma')).toBeInTheDocument();
      expect(screen.queryByText('Placeholder Beta')).not.toBeInTheDocument();

      await user.click(filterGroup().getByRole('button', { name: 'company' }));
      expect(screen.getByText('Placeholder Beta')).toBeInTheDocument();
      expect(screen.getByText('Placeholder Gamma')).toBeInTheDocument();
      expect(screen.queryByText('Placeholder Alpha')).not.toBeInTheDocument();
    });

    it('shows an untyped member unfiltered and excludes it under a filter', async () => {
      const user = userEvent.setup();
      hookMock.mockReturnValue(state({ groups: typedGroups() }));
      renderPanel();

      expect(screen.getByText('Placeholder Delta')).toBeInTheDocument();
      await user.click(filterGroup().getByRole('button', { name: 'band' }));
      expect(screen.queryByText('Placeholder Delta')).not.toBeInTheDocument();
    });

    it('omits the control when fewer than two distinct types are present', () => {
      hookMock.mockReturnValue(
        state({
          groups: [
            group({
              members: [member('a', 'Placeholder Alpha', ['band']), member('b', 'Placeholder Beta', ['band'])],
            }),
          ],
        })
      );
      renderPanel();
      expect(screen.queryByTestId('referenced-by-type-filter')).not.toBeInTheDocument();
      expect(screen.getByText('Placeholder Alpha')).toBeInTheDocument();
    });

    it('omits the control when no member has a type', () => {
      hookMock.mockReturnValue(state({ groups: [group()] }));
      renderPanel();
      expect(screen.queryByTestId('referenced-by-type-filter')).not.toBeInTheDocument();
    });
  });

  describe('malformed hook state', () => {
    it.each([
      ['undefined', undefined],
      ['null', null],
      ['a non-array object', {}],
    ])('does not crash when groups is %s', (_label, groups) => {
      hookMock.mockReturnValue(state({ groups }));
      renderPanel();
      expect(screen.getByTestId('referenced-by-empty')).toBeInTheDocument();
      expect(screen.queryByTestId('referenced-by-type-filter')).not.toBeInTheDocument();
    });

    it('does not crash while loading with non-array groups', () => {
      hookMock.mockReturnValue(state({ isLoading: true, groups: undefined }));
      renderPanel();
      expect(screen.getByTestId('referenced-by-loading')).toBeInTheDocument();
      expect(screen.queryByTestId('referenced-by-type-filter')).not.toBeInTheDocument();
    });

    it('tolerates members without instance_of', () => {
      hookMock.mockReturnValue(
        state({
          groups: [
            group({
              members: [{ entity_id: MEMBER_A, entity_type: 'person', canonical_name: 'Placeholder Person A' }],
            }),
          ],
        })
      );
      renderPanel();
      expect(screen.getByText('Placeholder Person A')).toBeInTheDocument();
    });
  });
});
