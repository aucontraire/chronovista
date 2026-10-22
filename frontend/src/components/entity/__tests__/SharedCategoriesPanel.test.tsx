/**
 * SharedCategoriesPanel — states and behaviour (Feature 085).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SharedCategoriesPanel } from '../SharedCategoriesPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useSharedCategoryNeighbours', async () => {
  const actual = await vi.importActual<
    typeof import('../../../hooks/useSharedCategoryNeighbours')
  >('../../../hooks/useSharedCategoryNeighbours');
  return {
    ...actual,
    useSharedCategoryNeighbours: (...args: unknown[]) => hookMock(...args),
  };
});

const SUBJECT = '11111111-1111-4111-8111-111111111111';
const NEIGHBOUR = '22222222-2222-4222-8222-222222222222';

function neighbour(overrides: Record<string, unknown> = {}) {
  return {
    entity_id: NEIGHBOUR,
    entity_type: 'organization',
    canonical_name: 'Analytical Engine',
    shared_categories: [
      { id: 'cat-1', name: 'Sample Category A' },
      { id: 'cat-2', name: 'Sample Category B' },
    ],
    shared_category_count: 2,
    ...overrides,
  };
}

function state(overrides: Record<string, unknown> = {}) {
  return {
    neighbours: [],
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SharedCategoriesPanel entityId={SUBJECT} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('SharedCategoriesPanel (Feature 085)', () => {
  beforeEach(() => {
    hookMock.mockReset();
  });

  describe('states', () => {
    it('shows a loading status', () => {
      hookMock.mockReturnValue(state({ isLoading: true }));
      renderPanel();

      expect(screen.getByTestId('shared-categories-loading')).toHaveAttribute(
        'role',
        'status'
      );
      expect(screen.queryByTestId('shared-categories-empty')).not.toBeInTheDocument();
      expect(screen.queryByTestId('shared-categories-error')).not.toBeInTheDocument();
    });

    it('shows a panel-level error alert and keeps the heading', () => {
      hookMock.mockReturnValue(state({ isError: true, error: new Error('boom') }));
      renderPanel();

      expect(screen.getByRole('alert')).toHaveTextContent(
        /rest of this page is unaffected/i
      );
      expect(screen.getByText('Shares categories with')).toBeInTheDocument();
    });

    it('shows a clean empty status, not an error', () => {
      hookMock.mockReturnValue(state());
      renderPanel();

      expect(screen.getByTestId('shared-categories-empty')).toHaveAttribute(
        'role',
        'status'
      );
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('renders the list', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      renderPanel();

      expect(screen.getByRole('list')).toBeInTheDocument();
      expect(screen.getByText('Analytical Engine')).toBeInTheDocument();
    });
  });

  describe('rows', () => {
    it('links each neighbour to its entity page', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      renderPanel();

      expect(
        screen.getByRole('link', { name: /Analytical Engine/ })
      ).toHaveAttribute('href', `/entities/${NEIGHBOUR}`);
    });

    it('links each category chip to its category page', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      renderPanel();

      expect(
        screen.getByRole('link', { name: 'Sample Category A' })
      ).toHaveAttribute('href', '/wikipedia-categories/cat-1');
      expect(
        screen.getByRole('link', { name: 'Sample Category B' })
      ).toHaveAttribute('href', '/wikipedia-categories/cat-2');
    });

    it('shows the shared category names and count', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      renderPanel();

      expect(screen.getByText('Sample Category A')).toBeInTheDocument();
      expect(screen.getByText('Sample Category B')).toBeInTheDocument();
      expect(screen.getByText('2 categories')).toBeInTheDocument();
    });

    it('singularises a count of one', () => {
      hookMock.mockReturnValue(
        state({
          neighbours: [
            neighbour({ shared_categories: [{ id: 'cat-1', name: 'Sample Category A' }], shared_category_count: 1 }),
          ],
        })
      );
      renderPanel();

      expect(screen.getByText('1 category')).toBeInTheDocument();
    });

    it('renders neighbours in the order the hook returns them', () => {
      hookMock.mockReturnValue(
        state({
          neighbours: [
            neighbour({ entity_id: 'z', canonical_name: 'Zeta', shared_category_count: 1 }),
            neighbour({ entity_id: 'a', canonical_name: 'Alpha', shared_category_count: 5 }),
            neighbour({ entity_id: 'm', canonical_name: 'Mu', shared_category_count: 3 }),
          ],
        })
      );
      renderPanel();

      const links = within(screen.getByRole('list'))
        .getAllByRole('link')
        .filter((l) => l.getAttribute('href')?.startsWith('/entities/'));
      expect(links.map((l) => l.getAttribute('href'))).toEqual([
        '/entities/z',
        '/entities/a',
        '/entities/m',
      ]);
    });
  });

  describe('framing', () => {
    it('is topical and never calls the grouping a relationship', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      const { container } = renderPanel();

      expect(
        screen.getByRole('heading', { name: 'Shares categories with' })
      ).toBeInTheDocument();
      const text = container.textContent ?? '';
      expect(text).not.toMatch(/relationship/i);
      expect(text).not.toMatch(/related to/i);
    });
  });

  describe('show more', () => {
    it('is hidden when the list is short of the page size', () => {
      hookMock.mockReturnValue(state({ neighbours: [neighbour()] }));
      renderPanel();

      expect(
        screen.queryByRole('button', { name: 'Show more' })
      ).not.toBeInTheDocument();
    });

    it('requests a further tranche when the list fills the page', async () => {
      const user = userEvent.setup();
      const full = Array.from({ length: 12 }, (_, i) =>
        neighbour({ entity_id: `n${i}`, canonical_name: `Neighbour ${i}` })
      );
      hookMock.mockReturnValue(state({ neighbours: full }));
      renderPanel();

      await user.click(screen.getByRole('button', { name: 'Show more' }));

      await waitFor(() => {
        expect(hookMock.mock.calls.map((c) => c[1])).toContain(24);
      });
    });

    it('is hidden once the ceiling is reached', async () => {
      const user = userEvent.setup();
      hookMock.mockImplementation((_id: string, limit: number) =>
        state({
          neighbours: Array.from({ length: limit }, (_, i) =>
            neighbour({ entity_id: `n${i}`, canonical_name: `Neighbour ${i}` })
          ),
        })
      );
      renderPanel();

      // 12 -> 24 -> 36 -> 48 -> 50
      for (let i = 0; i < 4; i++) {
        await user.click(screen.getByRole('button', { name: 'Show more' }));
      }

      expect(
        screen.queryByRole('button', { name: 'Show more' })
      ).not.toBeInTheDocument();
      expect(hookMock.mock.calls.map((c) => c[1])).toContain(50);
    });

    it('passes the subject id and page size to the hook', () => {
      hookMock.mockReturnValue(state());
      renderPanel();

      expect(hookMock).toHaveBeenCalledWith(SUBJECT, 12);
    });
  });
});
