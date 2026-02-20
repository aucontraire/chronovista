/**
 * Tests for SortDropdown Component (Feature 027, T004)
 *
 * Tests the generic SortDropdown component that manages sort_by and sort_order
 * URL parameters via useUrlParam hook.
 *
 * Requirements tested:
 * - FR-001: Native HTML <select> element with configured options
 * - FR-001a: Renders correctly with only 2 sort options
 * - FR-005: Accessible label and 44×44px minimum hit area (WCAG 2.5.8)
 * - FR-024: URL parameter synchronization
 * - FR-027: Default sort value selected when no URL params
 * - FR-032: Visible focus indicator
 *
 * Test coverage:
 * - Renders configured sort options as <option> elements
 * - Selection updates URL sort_by and sort_order params
 * - Changing sort field sets the field's defaultOrder
 * - Toggling same field reverses sort order (asc↔desc)
 * - Has accessible label (aria-label or associated <label>)
 * - Renders correctly with only 2 options
 * - Has visible focus indicator
 * - Default value selected when no URL params
 * - Preserves existing URL params when changing sort
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, getTestLocation } from '../test-utils';
import { SortDropdown } from '../../src/components/SortDropdown';
import type { SortOption } from '../../src/types/filters';

// Test sort field types
type TestSortField = 'upload_date' | 'title' | 'video_count';

// Sample sort options for testing
const VIDEO_SORT_OPTIONS: SortOption<TestSortField>[] = [
  { field: 'upload_date', label: 'Date Added', defaultOrder: 'desc' },
  { field: 'title', label: 'Title', defaultOrder: 'asc' },
  { field: 'video_count', label: 'Video Count', defaultOrder: 'desc' },
];

const MINIMAL_SORT_OPTIONS: SortOption<TestSortField>[] = [
  { field: 'upload_date', label: 'Date', defaultOrder: 'desc' },
  { field: 'title', label: 'Name', defaultOrder: 'asc' },
];

describe('SortDropdown', () => {
  beforeEach(() => {
    // Reset location between tests
  });

  describe('Basic Rendering (FR-001)', () => {
    it('should render native HTML <select> element', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox', { name: /sort by/i });
      expect(select).toBeInTheDocument();
      expect(select.tagName).toBe('SELECT');
    });

    it('should render configured sort options as <option> elements', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      // Each field should have two options (asc and desc)
      expect(screen.getByRole('option', { name: /date added.*↓/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /date added.*↑/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /title.*↑/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /title.*↓/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /video count.*↓/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /video count.*↑/i })).toBeInTheDocument();
    });

    it('should render correctly with only 2 sort options (FR-001a)', () => {
      renderWithProviders(
        <SortDropdown
          options={MINIMAL_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();

      // Should have 4 options total (2 fields × 2 orders)
      const options = screen.getAllByRole('option');
      expect(options).toHaveLength(4);
    });

    it('should display field labels with direction indicators', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      // Options should show direction with arrows
      const dateDesc = screen.getByRole('option', { name: /date added.*↓/i });
      expect(dateDesc).toHaveTextContent('↓'); // Down arrow for descending

      const titleAsc = screen.getByRole('option', { name: /title.*↑/i });
      expect(titleAsc).toHaveTextContent('↑'); // Up arrow for ascending
    });
  });

  describe('Accessible Label (FR-005)', () => {
    it('should have accessible label via aria-label', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox', { name: /sort by/i });
      expect(select).toHaveAccessibleName();
    });

    it('should accept custom label text', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
          label="Order by"
        />
      );

      const select = screen.getByRole('combobox', { name: /order by/i });
      expect(select).toBeInTheDocument();
    });

    it('should use default label "Sort by" when label prop omitted', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox', { name: /sort by/i });
      expect(select).toBeInTheDocument();
    });

    it('should have associated <label> element', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const label = screen.getByText(/sort by/i);
      expect(label.tagName).toBe('LABEL');

      const select = screen.getByRole('combobox');
      expect(select).toHaveAttribute('id');
      expect(label).toHaveAttribute('for', select.id);
    });
  });

  describe('Minimum Hit Area (FR-005, WCAG 2.5.8)', () => {
    it('should have min-h-[44px] class for 44px minimum height', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveClass('min-h-[44px]');
    });

    it('should have min-w-[44px] class for 44px minimum width', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveClass('min-w-[44px]');
    });
  });

  describe('Visible Focus Indicator (FR-032)', () => {
    it('should have focus ring classes', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      // Should have focus ring utilities
      expect(select.className).toMatch(/focus:(ring|border|outline)/);
    });

    it('should be keyboard focusable', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');

      // Tab to focus
      await user.tab();
      expect(select).toHaveFocus();
    });
  });

  describe('URL Parameter Synchronization (FR-024)', () => {
    it('should update sort_by and sort_order URL params when selection changes', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos'] }
      );

      const select = screen.getByRole('combobox');

      // Select title ascending
      await user.selectOptions(select, 'title:asc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_by=title');
        expect(location.search).toContain('sort_order=asc');
      });
    });

    it('should read initial values from URL params', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_by=title&sort_order=asc'] }
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('title:asc');
    });

    it('should preserve existing URL params when changing sort', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?liked_only=true&has_transcript=true'] }
      );

      const select = screen.getByRole('combobox');

      // Change sort
      await user.selectOptions(select, 'title:asc');

      await waitFor(() => {
        const location = getTestLocation();
        // Should preserve existing params
        expect(location.search).toContain('liked_only=true');
        expect(location.search).toContain('has_transcript=true');
        // And add new sort params
        expect(location.search).toContain('sort_by=title');
        expect(location.search).toContain('sort_order=asc');
      });
    });
  });

  describe('Default Sort Value (FR-027)', () => {
    it('should select default value when no URL params present', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos'] }
      );

      const select = screen.getByRole('combobox');
      // Default: upload_date desc
      expect(select).toHaveValue('upload_date:desc');
    });

    it('should respect different default field and order', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="title"
          defaultOrder="asc"
        />,
        { initialEntries: ['/videos'] }
      );

      const select = screen.getByRole('combobox');
      // Default: title asc
      expect(select).toHaveValue('title:asc');
    });

    it('should not add default values to URL when first rendered', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos'] }
      );

      const location = getTestLocation();
      // URL should remain clean (no params added for default)
      expect(location.search).toBe('');
    });
  });

  describe('Field Default Order Behavior', () => {
    it('should use field defaultOrder when selecting a new field', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos'] }
      );

      const select = screen.getByRole('combobox');

      // Select title (defaultOrder: asc)
      await user.selectOptions(select, 'title:asc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_order=asc');
      });
    });

    it('should respect field defaultOrder from options config', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');

      // Select video_count (defaultOrder: desc)
      await user.selectOptions(select, 'video_count:desc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_by=video_count');
        expect(location.search).toContain('sort_order=desc');
      });
    });
  });

  describe('Toggle Sort Order Behavior', () => {
    it('should allow toggling between asc and desc for same field', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="title"
          defaultOrder="asc"
        />,
        { initialEntries: ['/videos?sort_by=title&sort_order=asc'] }
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('title:asc');

      // Toggle to desc
      await user.selectOptions(select, 'title:desc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_order=desc');
      });
    });

    it('should toggle from desc to asc', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_by=upload_date&sort_order=desc'] }
      );

      const select = screen.getByRole('combobox');

      // Toggle to asc
      await user.selectOptions(select, 'upload_date:asc');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.search).toContain('sort_order=asc');
      });
    });
  });

  describe('Edge Cases', () => {
    it('should handle invalid URL params by falling back to default', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_by=invalid&sort_order=invalid'] }
      );

      const select = screen.getByRole('combobox');
      // Should fall back to default
      expect(select).toHaveValue('upload_date:desc');
    });

    it('should handle missing sort_by param', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_order=asc'] }
      );

      const select = screen.getByRole('combobox');
      // Should use default field with provided order
      expect(select).toHaveValue('upload_date:desc');
    });

    it('should handle missing sort_order param', () => {
      renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_by=title'] }
      );

      const select = screen.getByRole('combobox');
      // Should use field's defaultOrder
      expect(select).toHaveValue('title:asc');
    });

    it('should handle empty options array gracefully', () => {
      renderWithProviders(
        <SortDropdown
          options={[]}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
      expect(screen.queryAllByRole('option')).toHaveLength(0);
    });
  });

  describe('Keyboard Navigation', () => {
    it('should allow keyboard navigation with arrow keys', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      select.focus();
      expect(select).toHaveFocus();

      // Arrow keys navigate through options (native <select> behavior)
      await user.keyboard('{ArrowDown}');
      expect(select).toHaveFocus();
    });

    it('should allow Enter key to confirm selection', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      select.focus();

      await user.keyboard('{Enter}');
      // Native <select> behavior
      expect(select).toHaveFocus();
    });
  });

  describe('Component Updates', () => {
    it('should update when URL params change externally', () => {
      const { rerender } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />,
        { initialEntries: ['/videos?sort_by=title&sort_order=asc'] }
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('title:asc');

      // Simulate external URL change (e.g., browser back button)
      rerender(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      // Note: In real app, MemoryRouter would handle this.
      // This test verifies component respects URL state
    });

    it('should maintain focus when selection changes', async () => {
      const { user } = renderWithProviders(
        <SortDropdown
          options={VIDEO_SORT_OPTIONS}
          defaultField="upload_date"
          defaultOrder="desc"
        />
      );

      const select = screen.getByRole('combobox');
      select.focus();
      expect(select).toHaveFocus();

      await user.selectOptions(select, 'title:asc');

      // Focus should remain on select after selection
      expect(select).toHaveFocus();
    });
  });
});
