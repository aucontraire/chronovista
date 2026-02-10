/**
 * Tests for CategoryDropdown Component - Video Classification Filters (Feature 020)
 *
 * Requirements tested:
 * - T030: Accessible category dropdown with ARIA listbox pattern
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 *
 * Test coverage:
 * - ARIA listbox pattern (role="listbox", aria-labelledby)
 * - role="option" with aria-selected for items
 * - Single selection behavior
 * - Keyboard navigation (Arrow Up/Down, Enter/Space, Escape, Home/End)
 * - Focus management (returns to button after selection)
 * - "All Categories" option to clear filter
 * - Screen reader announcements
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { CategoryDropdown } from '../../src/components/CategoryDropdown';
import { QueryClient } from '@tanstack/react-query';

// Mock the useCategories hook
vi.mock('../../src/hooks/useCategories', () => ({
  useCategories: () => ({
    categories: [
      { category_id: '10', name: 'Music', assignable: true },
      { category_id: '20', name: 'Gaming', assignable: true },
      { category_id: '22', name: 'People & Blogs', assignable: true },
      { category_id: '24', name: 'Entertainment', assignable: true },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

describe('CategoryDropdown', () => {
  let mockOnCategoryChange: ReturnType<typeof vi.fn>;
  let queryClient: QueryClient;

  beforeEach(() => {
    mockOnCategoryChange = vi.fn();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render with label', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      expect(screen.getByText('Category')).toBeInTheDocument();
    });

    it('should render button with "All Categories" when no selection', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      expect(screen.getByRole('button', { name: /Category/ })).toHaveTextContent('All Categories');
    });

    it('should render button with selected category name', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      expect(screen.getByRole('button', { name: /Category/ })).toHaveTextContent('Music');
    });

    it('should show category badge when category is selected', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      // Check for both the label and badge with "Category" text
      const categoryElements = screen.getAllByText('Category');
      expect(categoryElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('ARIA Button Attributes (FR-ACC-001)', () => {
    it('should have proper ARIA button attributes', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      expect(button).toHaveAttribute('aria-haspopup', 'listbox');
      expect(button).toHaveAttribute('aria-expanded', 'false');
      expect(button).toHaveAttribute('aria-labelledby');
      expect(button).toHaveAttribute('aria-describedby');
    });

    it('should set aria-expanded to true when dropdown is open', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(button).toHaveAttribute('aria-expanded', 'true');
      });
    });
  });

  describe('ARIA Listbox Pattern', () => {
    it('should render listbox when dropdown is open', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        expect(listbox).toBeInTheDocument();
        expect(listbox).toHaveAttribute('aria-labelledby');
      });
    });

    it('should render options with role="option" and aria-selected', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        expect(options.length).toBe(5); // 4 categories + "All Categories"

        options.forEach(option => {
          expect(option).toHaveAttribute('aria-selected');
        });
      });
    });

    it('should mark selected option with aria-selected="true"', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        const musicOption = screen.getByRole('option', { name: /Music/ });
        expect(musicOption).toHaveAttribute('aria-selected', 'true');
      });
    });

    it('should have aria-activedescendant when option is highlighted', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const activeDescendant = listbox.getAttribute('aria-activedescendant');
        expect(activeDescendant).toBeTruthy();
      });
    });
  });

  describe('Keyboard Navigation (T030)', () => {
    it('should open dropdown with ArrowDown key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      button.focus();
      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });
    });

    it('should open dropdown with ArrowUp key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      button.focus();
      await user.keyboard('{ArrowUp}');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });
    });

    it('should open dropdown with Enter key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      button.focus();
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });
    });

    it('should open dropdown with Space key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      button.focus();
      await user.keyboard(' ');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });
    });

    it('should navigate options with ArrowDown key when open', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const options = screen.getAllByRole('option');
        // Second option should be highlighted (first is "All Categories" at index 0)
        // Check aria-activedescendant points to the highlighted option
        expect(listbox).toHaveAttribute('aria-activedescendant', options[1].id);
      });
    });

    it('should navigate options with ArrowUp key when open', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowUp}');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant points to the highlighted option
        expect(listbox).toHaveAttribute('aria-activedescendant', options[1].id);
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should wrap to first option when pressing ArrowDown at last option', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      // Navigate to last option
      const options = screen.getAllByRole('option');
      for (let i = 0; i < options.length; i++) {
        await user.keyboard('{ArrowDown}');
      }

      // Press ArrowDown once more to wrap
      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const firstOption = screen.getAllByRole('option')[0];
        // Check aria-activedescendant points to the first option after wrap
        expect(listbox).toHaveAttribute('aria-activedescendant', firstOption.id);
      });
    });

    it('should select option with Enter key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}'); // Move to "Music"
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockOnCategoryChange).toHaveBeenCalledWith('10');
      });
    });

    it('should select option with Space key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}'); // Move to "Music"
      await user.keyboard(' ');

      await waitFor(() => {
        expect(mockOnCategoryChange).toHaveBeenCalledWith('10');
      });
    });

    it('should close dropdown with Escape key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{Escape}');

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });
    });

    it('should jump to first option with Home key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowDown}');
      await user.keyboard('{Home}');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        expect(options[0]).toHaveAttribute('aria-selected', 'true');
      });
    });

    it('should jump to last option with End key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{End}');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant points to the last option
        expect(listbox).toHaveAttribute('aria-activedescendant', options[options.length - 1].id);
      });
    });

    it('should close dropdown with Tab key', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{Tab}');

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });
    });
  });

  describe('Focus Management (FR-ACC-002)', () => {
    it('should return focus to button after selection', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(button).toHaveFocus();
      });
    });

    it('should return focus to button after pressing Escape', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{Escape}');

      await waitFor(() => {
        expect(button).toHaveFocus();
      });
    });
  });

  describe('Single Selection Behavior', () => {
    it('should show checkmark for selected category', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        const musicOption = screen.getByRole('option', { name: /Music/ });
        expect(musicOption).toHaveAttribute('aria-selected', 'true');
        // Check for checkmark icon (via aria-hidden svg)
        const svg = musicOption.querySelector('svg[aria-hidden="true"]');
        expect(svg).toBeInTheDocument();
      });
    });

    it('should allow selecting "All Categories" to clear filter', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory="10"
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const allCategoriesOption = screen.getByRole('option', { name: /All Categories/ });
      await user.click(allCategoriesOption);

      expect(mockOnCategoryChange).toHaveBeenCalledWith(null);
    });
  });

  describe('Screen Reader Announcements (FR-ACC-004)', () => {
    it('should have aria-live region for announcements', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const liveRegion = screen.getByRole('status');
      expect(liveRegion).toHaveAttribute('aria-live', 'polite');
      expect(liveRegion).toHaveAttribute('aria-atomic', 'true');
    });

    it('should have description for screen readers', () => {
      renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      const descriptionId = button.getAttribute('aria-describedby');
      expect(descriptionId).toBeTruthy();

      const description = document.getElementById(descriptionId!);
      expect(description).toHaveTextContent(/Use arrow keys to navigate/);
    });
  });

  describe('Visible Focus Indicators (FR-ACC-007)', () => {
    it('should have focus ring on button when focused', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      expect(button).toHaveClass('focus:ring-2');
      expect(button).toHaveClass('focus:ring-blue-500');
    });
  });

  describe('Mouse Interaction', () => {
    it('should toggle dropdown on button click', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.click(button);

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });
    });

    it('should select option on mouse click', async () => {
      const { user } = renderWithProviders(
        <CategoryDropdown
          selectedCategory={null}
          onCategoryChange={mockOnCategoryChange}
        />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /Category/ });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const musicOption = screen.getByRole('option', { name: /Music/ });
      await user.click(musicOption);

      expect(mockOnCategoryChange).toHaveBeenCalledWith('10');
    });
  });
});
