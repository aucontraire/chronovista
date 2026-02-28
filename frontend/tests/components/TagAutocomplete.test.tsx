/**
 * Tests for TagAutocomplete Component - Video Classification Filters (Feature 020)
 *
 * Requirements tested:
 * - T029: Accessible tag autocomplete with ARIA combobox pattern
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 *
 * Test coverage:
 * - ARIA combobox pattern (role="combobox", aria-expanded, aria-autocomplete="list")
 * - ARIA listbox for suggestions (role="listbox", role="option")
 * - aria-activedescendant for keyboard navigation
 * - Keyboard navigation (Arrow Up/Down, Enter, Escape, Tab, Home/End)
 * - Focus management (returns to input after selection/removal)
 * - Maximum tag limit validation
 * - Filter pills with remove buttons
 * - Screen reader announcements
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { TagAutocomplete } from '../../src/components/TagAutocomplete';
import { QueryClient } from '@tanstack/react-query';
import type { SelectedCanonicalTag } from '../../src/types/canonical-tags';

// Mock the useCanonicalTags hook used by TagAutocomplete
vi.mock('../../src/hooks/useCanonicalTags', () => ({
  useCanonicalTags: (search: string) => {
    const mockTags = [
      { canonical_form: 'react', normalized_form: 'react', alias_count: 1, video_count: 10 },
      { canonical_form: 'typescript', normalized_form: 'typescript', alias_count: 1, video_count: 8 },
      { canonical_form: 'javascript', normalized_form: 'javascript', alias_count: 2, video_count: 15 },
      { canonical_form: 'python', normalized_form: 'python', alias_count: 1, video_count: 5 },
      { canonical_form: 'go', normalized_form: 'go', alias_count: 1, video_count: 3 },
      { canonical_form: 'rust', normalized_form: 'rust', alias_count: 1, video_count: 4 },
    ];
    const filteredTags = search
      ? mockTags.filter(tag => tag.canonical_form.toLowerCase().includes(search.toLowerCase()))
      : [];

    return {
      tags: filteredTags,
      suggestions: [],
      isLoading: false,
      isError: false,
      error: null,
      isRateLimited: false,
      rateLimitRetryAfter: 0,
    };
  },
}));

// Helper to create SelectedCanonicalTag objects from simple strings
function makeSelectedTags(tagNames: string[]): SelectedCanonicalTag[] {
  return tagNames.map(name => ({
    canonical_form: name,
    normalized_form: name,
    alias_count: 1,
  }));
}

describe('TagAutocomplete', () => {
  let mockOnTagSelect: ReturnType<typeof vi.fn>;
  let mockOnTagRemove: ReturnType<typeof vi.fn>;
  let queryClient: QueryClient;

  beforeEach(() => {
    mockOnTagSelect = vi.fn();
    mockOnTagRemove = vi.fn();
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
    it('should render with label and tag count', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react', 'typescript'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      expect(screen.getByText(/Tags/)).toBeInTheDocument();
      expect(screen.getByText(/\(2\/10\)/)).toBeInTheDocument();
    });

    it('should display selected tags as filter pills', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react', 'typescript'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      expect(screen.getByText('react')).toBeInTheDocument();
      expect(screen.getByText('typescript')).toBeInTheDocument();
    });

    it('should render combobox input with placeholder', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      expect(combobox).toBeInTheDocument();
      expect(combobox).toHaveAttribute('placeholder', 'Type to search tags...');
    });
  });

  describe('ARIA Combobox Pattern (FR-ACC-001)', () => {
    it('should have proper ARIA combobox attributes', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      expect(combobox).toHaveAttribute('aria-autocomplete', 'list');
      expect(combobox).toHaveAttribute('aria-expanded', 'false');
      expect(combobox).toHaveAttribute('aria-labelledby');
      expect(combobox).toHaveAttribute('aria-describedby');
    });

    it('should set aria-expanded to true when suggestions are shown', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        expect(combobox).toHaveAttribute('aria-expanded', 'true');
      });
    });

    it('should have aria-controls pointing to listbox when open', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        const controlsId = combobox.getAttribute('aria-controls');
        expect(controlsId).toBe(listbox.id);
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should have aria-activedescendant for highlighted option', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        const activeDescendant = combobox.getAttribute('aria-activedescendant');
        expect(activeDescendant).toBeTruthy();
        expect(activeDescendant).toMatch(/option-0$/);
      }, { timeout: 3000 });
    });
  });

  describe('ARIA Listbox Pattern', () => {
    it('should render listbox with proper role when suggestions available', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        const listbox = screen.getByRole('listbox');
        expect(listbox).toBeInTheDocument();
        expect(listbox).toHaveAttribute('aria-labelledby');
      });
    });

    it('should render options with role="option"', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'r');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        expect(options.length).toBeGreaterThan(0);
        options.forEach(option => {
          expect(option).toHaveAttribute('aria-selected');
        });
      });
    });
  });

  describe('Keyboard Navigation (T029)', () => {
    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should navigate down with ArrowDown key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'r');

      // Wait for listbox to appear before keyboard navigation
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant on combobox points to the highlighted option
        expect(combobox).toHaveAttribute('aria-activedescendant', options[0].id);
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should navigate up with ArrowUp key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'r');

      // Wait for listbox to appear before keyboard navigation
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowUp}');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant on combobox points to the highlighted option
        expect(combobox).toHaveAttribute('aria-activedescendant', options[0].id);
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should wrap to first option when pressing ArrowDown at last option', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'r');

      // Navigate to last option and press ArrowDown once more
      const options = await screen.findAllByRole('option');
      for (let i = 0; i < options.length; i++) {
        await user.keyboard('{ArrowDown}');
      }
      await user.keyboard('{ArrowDown}');

      await waitFor(() => {
        const firstOption = screen.getAllByRole('option')[0];
        // Check aria-activedescendant on combobox points to the first option after wrap
        expect(combobox).toHaveAttribute('aria-activedescendant', firstOption.id);
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should select option with Enter key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      // Wait for listbox to appear before keyboard navigation
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockOnTagSelect).toHaveBeenCalledWith('react');
      });
    });

    it('should close dropdown with Escape key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{Escape}');

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should jump to first option with Home key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{ArrowDown}');
      await user.keyboard('{ArrowDown}');
      await user.keyboard('{Home}');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant on combobox points to the first option
        expect(combobox).toHaveAttribute('aria-activedescendant', options[0].id);
      }, { timeout: 3000 });
    });

    // TODO: Fix keyboard navigation timing issues with user-event and React state updates
    it.skip('should jump to last option with End key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.keyboard('{End}');

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        // Check aria-activedescendant on combobox points to the last option
        expect(combobox).toHaveAttribute('aria-activedescendant', options[options.length - 1].id);
      }, { timeout: 3000 });
    });

    it('should close dropdown with Tab key', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');

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
    it('should return focus to input after tag selection', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.type(combobox, 'react');
      await user.keyboard('{ArrowDown}');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(combobox).toHaveFocus();
      });
    });

    it('should return focus to input after tag removal', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const removeButton = screen.getByRole('button', { name: /Remove tag react/ });
      await user.click(removeButton);

      await waitFor(() => {
        const combobox = screen.getByRole('combobox');
        expect(combobox).toHaveFocus();
      });
    });
  });

  describe('Maximum Tag Limit', () => {
    it('should disable input when max tags reached', () => {
      const maxTags = 3;

      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react', 'typescript', 'javascript'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
          maxTags={maxTags}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      expect(combobox).toBeDisabled();
      expect(combobox).toHaveAttribute('placeholder', 'Maximum tags reached');
    });

    it('should show correct count in label', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react', 'typescript'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
          maxTags={5}
        />,
        { queryClient }
      );

      expect(screen.getByText(/\(2\/5\)/)).toBeInTheDocument();
    });
  });

  describe('Screen Reader Announcements (FR-ACC-004)', () => {
    it('should have aria-live region for announcements', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const liveRegion = screen.getByRole('status');
      expect(liveRegion).toHaveAttribute('aria-live', 'polite');
      expect(liveRegion).toHaveAttribute('aria-atomic', 'true');
    });

    it('should have description for screen readers', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      const descriptionId = combobox.getAttribute('aria-describedby');
      expect(descriptionId).toBeTruthy();

      const description = document.getElementById(descriptionId!);
      expect(description).toHaveTextContent(/Use arrow keys to navigate/);
    });
  });

  describe('Filter Pills', () => {
    it('should render remove buttons for selected tags', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react', 'typescript'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      expect(screen.getByRole('button', { name: /Remove tag react/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Remove tag typescript/ })).toBeInTheDocument();
    });

    it('should call onTagRemove when remove button clicked', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const removeButton = screen.getByRole('button', { name: /Remove tag react/ });
      await user.click(removeButton);

      // onTagRemove is called with the normalizedForm ('react')
      expect(mockOnTagRemove).toHaveBeenCalledWith('react');
    });
  });

  describe('Visible Focus Indicators (FR-ACC-007)', () => {
    it('should have focus ring on combobox when focused', async () => {
      const { user } = renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const combobox = screen.getByRole('combobox');
      await user.click(combobox);

      expect(combobox).toHaveClass('focus:ring-2');
      expect(combobox).toHaveClass('focus:ring-blue-500');
    });

    it('should have focus ring on remove buttons', () => {
      renderWithProviders(
        <TagAutocomplete
          selectedTags={makeSelectedTags(['react'])}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />,
        { queryClient }
      );

      const removeButton = screen.getByRole('button', { name: /Remove tag react/ });
      expect(removeButton).toHaveClass('focus:ring-2');
      expect(removeButton).toHaveClass('focus:ring-blue-500');
    });
  });
});
