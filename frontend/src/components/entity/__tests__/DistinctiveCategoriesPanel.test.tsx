/**
 * DistinctiveCategoriesPanel — states and behaviour (Feature 089).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { DistinctiveCategoriesPanel } from '../DistinctiveCategoriesPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useDistinctiveCategories', async () => {
  const actual = await vi.importActual<
    typeof import('../../../hooks/useDistinctiveCategories')
  >('../../../hooks/useDistinctiveCategories');
  return {
    ...actual,
    useDistinctiveCategories: (...args: unknown[]) => hookMock(...args),
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
      <DistinctiveCategoriesPanel entityId={SUBJECT} />
    </MemoryRouter>
  );
}

describe('DistinctiveCategoriesPanel (Feature 089)', () => {
  beforeEach(() => {
    hookMock.mockReset();
  });

  it('renders categories as chips linking to the category page', () => {
    hookMock.mockReturnValue(
      state({
        categories: [
          { id: 'cat-1', name: 'Sample Category A' },
          { id: 'cat-2', name: 'Sample Category B' },
        ],
      })
    );
    renderPanel();

    expect(
      screen.getByRole('heading', { name: 'Distinctive — only this entity' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Sample Category A' })
    ).toHaveAttribute('href', '/wikipedia-categories/cat-1');
    expect(
      screen.getByRole('link', { name: 'Sample Category B' })
    ).toHaveAttribute('href', '/wikipedia-categories/cat-2');
  });

  it('renders nothing when there are no distinctive categories', () => {
    hookMock.mockReturnValue(state());
    const { container } = renderPanel();

    expect(container).toBeEmptyDOMElement();
    expect(
      screen.queryByTestId('distinctive-categories-panel')
    ).not.toBeInTheDocument();
  });

  it('renders nothing while loading (no flash)', () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    const { container } = renderPanel();

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('pops in once data arrives after loading', () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    const { container, rerender } = renderPanel();
    expect(container).toBeEmptyDOMElement();

    hookMock.mockReturnValue(
      state({ categories: [{ id: 'cat-1', name: 'Sample Category A' }] })
    );
    rerender(
      <MemoryRouter>
        <DistinctiveCategoriesPanel entityId={SUBJECT} />
      </MemoryRouter>
    );

    expect(screen.getByTestId('distinctive-categories-panel')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Sample Category A' })
    ).toBeInTheDocument();
  });

  it('shows a recoverable error alert and keeps the heading', () => {
    hookMock.mockReturnValue(state({ isError: true, error: new Error('boom') }));
    renderPanel();

    expect(screen.getByRole('alert')).toHaveTextContent(
      /rest of this page is unaffected/i
    );
    expect(screen.getByText('Distinctive — only this entity')).toBeInTheDocument();
  });

  describe('show more', () => {
    it('is hidden when the list is short of the page size', () => {
      hookMock.mockReturnValue(
        state({ categories: [{ id: 'cat-1', name: 'Sample Category A' }] })
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
