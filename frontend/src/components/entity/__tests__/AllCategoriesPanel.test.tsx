/**
 * AllCategoriesPanel — states and behaviour (Feature 090).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { AllCategoriesPanel } from '../AllCategoriesPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useAllCategories', async () => {
  const actual = await vi.importActual<
    typeof import('../../../hooks/useAllCategories')
  >('../../../hooks/useAllCategories');
  return {
    ...actual,
    useAllCategories: (...args: unknown[]) => hookMock(...args),
  };
});

const SUBJECT = '11111111-1111-4111-8111-111111111111';

function state(overrides: Record<string, unknown> = {}) {
  return {
    categories: [],
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <AllCategoriesPanel entityId={SUBJECT} />
    </MemoryRouter>
  );
}

describe('AllCategoriesPanel (Feature 090)', () => {
  beforeEach(() => {
    hookMock.mockReset();
  });

  it('renders categories in server order with member counts and links', () => {
    hookMock.mockReturnValue(
      state({
        categories: [
          { id: 'cat-1', name: 'Sample Category A', member_count: 1 },
          { id: 'cat-2', name: 'Sample Category B', member_count: 7 },
          { id: 'cat-3', name: 'Sample Category C', member_count: 3 },
        ],
      })
    );
    renderPanel();

    expect(
      screen.getByRole('heading', { name: 'All categories' })
    ).toBeInTheDocument();

    const links = screen.getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/wikipedia-categories/cat-1',
      '/wikipedia-categories/cat-2',
      '/wikipedia-categories/cat-3',
    ]);
    expect(links[0]).toHaveTextContent('Sample Category A');
    expect(links[1]).toHaveTextContent('Sample Category B');
  });

  it('pluralizes the member count', () => {
    hookMock.mockReturnValue(
      state({
        categories: [
          { id: 'cat-1', name: 'Sample Category A', member_count: 1 },
          { id: 'cat-2', name: 'Sample Category B', member_count: 2 },
        ],
      })
    );
    renderPanel();

    const [first, second] = screen.getAllByRole('link');
    expect(within(first as HTMLElement).getByText('1 member')).toBeInTheDocument();
    expect(
      within(second as HTMLElement).getByText('2 members')
    ).toBeInTheDocument();
  });

  it('shows an honest empty message when there are no categories', () => {
    hookMock.mockReturnValue(state());
    renderPanel();

    expect(screen.getByTestId('all-categories-empty')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows a loading status while the first page loads', () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    renderPanel();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByTestId('all-categories-empty')).not.toBeInTheDocument();
  });

  it('shows a recoverable error alert and keeps the heading', () => {
    hookMock.mockReturnValue(state({ isError: true, error: new Error('boom') }));
    renderPanel();

    expect(screen.getByRole('alert')).toHaveTextContent(
      /rest of this page is unaffected/i
    );
    expect(screen.getByText('All categories')).toBeInTheDocument();
  });

  describe('show more', () => {
    it('is hidden when the list is short of the page size', () => {
      hookMock.mockReturnValue(
        state({
          categories: [{ id: 'cat-1', name: 'Sample Category A', member_count: 2 }],
        })
      );
      renderPanel();

      expect(
        screen.queryByRole('button', { name: 'Show more' })
      ).not.toBeInTheDocument();
    });

    it('requests a further tranche, then hides at the ceiling', async () => {
      const user = userEvent.setup();
      hookMock.mockImplementation((_id: string, limit: number) =>
        state({
          categories: Array.from({ length: limit }, (_, i) => ({
            id: `cat-${i}`,
            name: `Category ${i}`,
            member_count: i + 1,
          })),
        })
      );
      renderPanel();

      // 50 -> 100 -> 150 -> 200
      for (let i = 0; i < 3; i++) {
        await user.click(screen.getByRole('button', { name: 'Show more' }));
      }

      await waitFor(() => {
        expect(hookMock.mock.calls.map((c) => c[1])).toContain(200);
      });
      expect(
        screen.queryByRole('button', { name: 'Show more' })
      ).not.toBeInTheDocument();
    });

    it('passes the subject id and page size to the hook', () => {
      hookMock.mockReturnValue(state());
      renderPanel();

      expect(hookMock).toHaveBeenCalledWith(SUBJECT, 50);
    });
  });
});
