/**
 * CategoryMembersPanel — states and behaviour (Feature 090).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { CategoryMembersPanel } from '../CategoryMembersPanel';

const categoriesMock = vi.fn();
const membersMock = vi.fn();

vi.mock('../../../hooks/useAllCategories', () => ({
  useAllCategories: (...args: unknown[]) => categoriesMock(...args),
}));
vi.mock('../../../hooks/useCategoryEntities', () => ({
  useCategoryEntities: (...args: unknown[]) => membersMock(...args),
}));

const SUBJECT = '11111111-1111-4111-8111-111111111111';
const MEMBER_A = '22222222-2222-4222-8222-222222222222';
const MEMBER_B = '33333333-3333-4333-8333-333333333333';

function categoriesState(overrides: Record<string, unknown> = {}) {
  return {
    categories: [
      { id: 'cat-1', name: 'Sample Category A', member_count: 3 },
      { id: 'cat-2', name: 'Sample Category B', member_count: 9 },
    ],
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function membersState(overrides: Record<string, unknown> = {}) {
  return {
    entities: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    retry: vi.fn(),
    loadMoreRef: { current: null },
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <CategoryMembersPanel entityId={SUBJECT} />
    </MemoryRouter>
  );
}

describe('CategoryMembersPanel (Feature 090)', () => {
  beforeEach(() => {
    categoriesMock.mockReset();
    membersMock.mockReset();
    categoriesMock.mockReturnValue(categoriesState());
    membersMock.mockReturnValue(membersState());
  });

  it('requests the 200-category ceiling for the selector', () => {
    renderPanel();
    expect(categoriesMock).toHaveBeenCalledWith(SUBJECT, 200);
  });

  it('hides the empty state while more member pages are loadable', () => {
    membersMock.mockReturnValue(membersState({ hasNextPage: true }));
    renderPanel();
    expect(
      screen.queryByTestId('category-members-empty')
    ).not.toBeInTheDocument();
  });

  it('lists the entity categories, defaulting to the first', () => {
    renderPanel();
    const select = screen.getByTestId('category-members-select');
    expect(select).toHaveValue('cat-1');
    expect(screen.getByLabelText('Category')).toBe(select);
    expect(
      screen.getByRole('option', { name: 'Sample Category A (3)' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: 'Sample Category B (9)' })
    ).toBeInTheDocument();
    expect(membersMock).toHaveBeenLastCalledWith('cat-1');
  });

  it('drives the member list with the chosen category and links members', async () => {
    const user = userEvent.setup();
    membersMock.mockImplementation((id: string) =>
      id === 'cat-2'
        ? membersState({
            entities: [
              { entity_id: MEMBER_A, entity_type: 'person', canonical_name: 'Member One' },
              { entity_id: MEMBER_B, entity_type: 'organization', canonical_name: 'Member Two' },
            ],
          })
        : membersState()
    );
    renderPanel();
    expect(screen.getByTestId('category-members-empty')).toBeInTheDocument();

    await user.selectOptions(screen.getByTestId('category-members-select'), 'cat-2');

    expect(membersMock).toHaveBeenLastCalledWith('cat-2');
    expect(screen.getByRole('link', { name: /Member One/ })).toHaveAttribute(
      'href',
      `/entities/${MEMBER_A}`
    );
    expect(screen.getByRole('link', { name: /Member Two/ })).toHaveAttribute(
      'href',
      `/entities/${MEMBER_B}`
    );
  });

  it('shows an empty state without a selector when there are no categories', () => {
    categoriesMock.mockReturnValue(categoriesState({ categories: [] }));
    renderPanel();
    expect(screen.getByTestId('category-members-no-categories')).toBeInTheDocument();
    expect(screen.queryByTestId('category-members-select')).not.toBeInTheDocument();
  });

  it('shows a loading state while categories load', () => {
    categoriesMock.mockReturnValue(
      categoriesState({ categories: [], isLoading: true })
    );
    renderPanel();
    expect(screen.getByRole('status')).toHaveTextContent('Loading categories');
    expect(screen.queryByTestId('category-members-select')).not.toBeInTheDocument();
  });

  it('shows a loading state while members load', () => {
    membersMock.mockReturnValue(membersState({ isLoading: true }));
    renderPanel();
    expect(screen.getByTestId('category-members-loading')).toBeInTheDocument();
  });

  it('shows a recoverable error for categories', () => {
    categoriesMock.mockReturnValue(
      categoriesState({ categories: [], isError: true })
    );
    renderPanel();
    expect(
      screen.getByTestId('category-members-categories-error')
    ).toHaveAttribute('role', 'alert');
  });

  it('shows a recoverable error for members with a working retry', async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    membersMock.mockReturnValue(membersState({ isError: true, retry }));
    renderPanel();
    expect(screen.getByTestId('category-members-error')).toHaveAttribute(
      'role',
      'alert'
    );
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('category-members-select')).toBeInTheDocument();
  });

  it('omits the subject entity from its own category member list', () => {
    membersMock.mockReturnValue(
      membersState({
        entities: [
          { entity_id: SUBJECT, entity_type: 'person', canonical_name: 'Subject Entity' },
          { entity_id: MEMBER_A, entity_type: 'person', canonical_name: 'Member One' },
        ],
      })
    );
    renderPanel();
    expect(screen.queryByRole('link', { name: /Subject Entity/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Member One/ })).toBeInTheDocument();
  });
});
