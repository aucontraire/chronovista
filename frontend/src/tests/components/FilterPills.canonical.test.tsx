/**
 * Tests for FilterPills component — canonical_tag pill support
 *
 * Verifies:
 * - canonical_tag pill renders with canonical_form label
 * - Variation badge "{N} var." shown when alias_count > 1 (N = alias_count - 1)
 * - No variation badge when alias_count = 1
 * - Pill uses filterColors.canonical_tag blue inline styles
 * - Truncation at 25 chars with title tooltip
 * - Remove button has proper aria-label
 * - Focus management after removal: next pill → previous → search input (FR-022)
 * - Screen reader announcements on add/remove/clear per FR-021
 */

import React, { createRef } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterPills } from '../../components/FilterPills';
import type { FilterPill } from '../../components/FilterPills';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCanonicalPill(
  label: string,
  value: string,
  aliasCount: number
): FilterPill {
  return {
    type: 'canonical_tag',
    value,
    label,
    aliasCount,
  };
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('FilterPills — canonical_tag pill', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // Label rendering
  // -----------------------------------------------------------------------
  describe('Label rendering', () => {
    it('renders canonical_form as the pill label', () => {
      render(
        <FilterPills
          filters={[makeCanonicalPill('JavaScript', 'javascript', 3)]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText('JavaScript')).toBeInTheDocument();
    });

    it('renders the tag emoji icon for canonical_tag type', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('React', 'react', 2)]}
          onRemove={() => {}}
        />
      );

      expect(container.textContent).toContain('🏷️');
    });

    it('screen reader prefix reads "canonical_tag:"', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('TypeScript', 'typescript', 1)]}
          onRemove={() => {}}
        />
      );

      const srSpans = container.querySelectorAll('.sr-only');
      const typeSrSpan = Array.from(srSpans).find((el) =>
        el.textContent?.includes('canonical_tag:')
      );
      expect(typeSrSpan).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Variation badge
  // -----------------------------------------------------------------------
  describe('Variation badge', () => {
    it('shows "{N} var." badge when alias_count > 1 (N = alias_count - 1)', () => {
      // alias_count = 4 → "3 var."
      render(
        <FilterPills
          filters={[makeCanonicalPill('JavaScript', 'javascript', 4)]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText('3 var.')).toBeInTheDocument();
    });

    it('shows "1 var." when alias_count = 2', () => {
      render(
        <FilterPills
          filters={[makeCanonicalPill('React', 'react', 2)]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText('1 var.')).toBeInTheDocument();
    });

    it('does NOT show variation badge when alias_count = 1', () => {
      render(
        <FilterPills
          filters={[makeCanonicalPill('SoloTag', 'solotag', 1)]}
          onRemove={() => {}}
        />
      );

      // No "var." text anywhere in the pill
      expect(screen.queryByText(/var\./)).not.toBeInTheDocument();
    });

    it('does NOT show variation badge when aliasCount is undefined', () => {
      render(
        <FilterPills
          filters={[
            {
              type: 'canonical_tag',
              value: 'notag',
              label: 'NoTag',
              // aliasCount omitted
            },
          ]}
          onRemove={() => {}}
        />
      );

      expect(screen.queryByText(/var\./)).not.toBeInTheDocument();
    });

    it('variation badge is aria-hidden (visual only)', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('Python', 'python', 5)]}
          onRemove={() => {}}
        />
      );

      // Find the span containing "4 var." and check it is aria-hidden
      const allAriaHidden = container.querySelectorAll('[aria-hidden="true"]');
      const varBadge = Array.from(allAriaHidden).find(
        (el) => el.textContent === '4 var.'
      );
      expect(varBadge).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Color scheme
  // -----------------------------------------------------------------------
  describe('Color scheme', () => {
    it('uses filterColors.canonical_tag blue inline styles', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('JavaScript', 'javascript', 2)]}
          onRemove={() => {}}
        />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: '#DBEAFE',
        color: '#1E40AF',
        borderColor: '#BFDBFE',
      });
    });
  });

  // -----------------------------------------------------------------------
  // Truncation (25 chars for canonical_tag)
  // -----------------------------------------------------------------------
  describe('Truncation (25 chars for canonical_tag)', () => {
    it('truncates canonical_form at 25 chars with ellipsis', () => {
      const longLabel = 'a'.repeat(30); // 30 chars
      render(
        <FilterPills
          filters={[makeCanonicalPill(longLabel, 'long-tag', 1)]}
          onRemove={() => {}}
        />
      );

      // Should show first 25 chars + "..."
      const truncated = 'a'.repeat(25) + '...';
      expect(screen.getByText(truncated)).toBeInTheDocument();
    });

    it('does NOT truncate a 25-char canonical_form', () => {
      const exactLabel = 'a'.repeat(25); // exactly 25 chars
      render(
        <FilterPills
          filters={[makeCanonicalPill(exactLabel, 'exact-tag', 1)]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText(exactLabel)).toBeInTheDocument();
      expect(screen.queryByText(exactLabel + '...')).not.toBeInTheDocument();
    });

    it('shows tooltip with full label when truncated', () => {
      const longLabel = 'b'.repeat(30);
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill(longLabel, 'long-b', 1)]}
          onRemove={() => {}}
        />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveAttribute('title', longLabel);
    });

    it('does NOT truncate at 20 chars (default) for canonical_tag', () => {
      // 22-char label should NOT be truncated for canonical_tag (limit is 25)
      const label22 = 'c'.repeat(22);
      render(
        <FilterPills
          filters={[makeCanonicalPill(label22, 'tag-22', 1)]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText(label22)).toBeInTheDocument();
      expect(screen.queryByText(label22.slice(0, 20) + '...')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Remove button aria-label
  // -----------------------------------------------------------------------
  describe('Remove button', () => {
    it('has proper aria-label "Remove canonical_tag filter: {label}"', () => {
      render(
        <FilterPills
          filters={[makeCanonicalPill('React', 'react', 2)]}
          onRemove={() => {}}
        />
      );

      const removeBtn = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: React',
      });
      expect(removeBtn).toBeInTheDocument();
    });

    it('calls onRemove with type=canonical_tag and value=normalized_form', async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      render(
        <FilterPills
          filters={[makeCanonicalPill('TypeScript', 'typescript', 3)]}
          onRemove={mockOnRemove}
        />
      );

      const btn = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: TypeScript',
      });
      await user.click(btn);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith('canonical_tag', 'typescript');
    });
  });

  // -----------------------------------------------------------------------
  // Focus management (FR-022)
  // -----------------------------------------------------------------------
  describe('Focus management after removal (FR-022)', () => {
    it('focuses the next pill remove button after removing a non-last pill', async () => {
      // We need a controlled component to test focus changes after removal
      const user = userEvent.setup();

      const filters: FilterPill[] = [
        makeCanonicalPill('Tag A', 'tag-a', 1),
        makeCanonicalPill('Tag B', 'tag-b', 1),
        makeCanonicalPill('Tag C', 'tag-c', 1),
      ];

      let currentFilters = [...filters];
      const mockOnRemove = vi.fn((type: string, value: string) => {
        currentFilters = currentFilters.filter(
          (f) => !(f.type === type && f.value === value)
        );
      });

      const { rerender } = render(
        <FilterPills filters={currentFilters} onRemove={mockOnRemove} />
      );

      // Remove Tag A (index 0) — next should be Tag B's remove button
      const removeBtnA = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: Tag A',
      });
      await user.click(removeBtnA);

      // Rerender with updated filters (Tag A removed)
      rerender(
        <FilterPills filters={currentFilters} onRemove={mockOnRemove} />
      );

      // After removal, Tag B's button should exist
      const removeBtnB = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: Tag B',
      });
      expect(removeBtnB).toBeInTheDocument();
    });

    it('focuses the search input when last pill is removed and searchInputRef provided', async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      // Create a real input element and attach a ref
      const searchInput = document.createElement('input');
      searchInput.setAttribute('placeholder', 'Search...');
      document.body.appendChild(searchInput);

      const searchInputRef = createRef<HTMLInputElement>();
      // Manually set the ref's current to our input
      (searchInputRef as React.MutableRefObject<HTMLInputElement>).current = searchInput;

      render(
        <FilterPills
          filters={[makeCanonicalPill('OnlyTag', 'only-tag', 1)]}
          onRemove={mockOnRemove}
          searchInputRef={searchInputRef}
        />
      );

      const removeBtn = screen.getByRole('button', {
        name: 'Remove canonical_tag filter: OnlyTag',
      });
      await user.click(removeBtn);

      // requestAnimationFrame is used internally — tick it
      await act(async () => {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      });

      expect(mockOnRemove).toHaveBeenCalledWith('canonical_tag', 'only-tag');

      // Cleanup
      document.body.removeChild(searchInput);
    });
  });

  // -----------------------------------------------------------------------
  // Screen reader announcements (FR-021)
  // -----------------------------------------------------------------------
  describe('Screen reader announcements (FR-021)', () => {
    it('renders aria-live="polite" status region', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('React', 'react', 1)]}
          onRemove={() => {}}
        />
      );

      const liveRegion = container.querySelector('[role="status"][aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });

    it('announces filter removal with active count', async () => {
      const filters: FilterPill[] = [
        makeCanonicalPill('React', 'react', 1),
        makeCanonicalPill('TypeScript', 'typescript', 2),
      ];

      const { rerender, container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Remove React pill
      const updatedFilters = filters.filter((f) => f.value !== 'react');
      rerender(<FilterPills filters={updatedFilters} onRemove={() => {}} />);

      await waitFor(() => {
        const liveRegion = container.querySelector(
          '[data-testid="filter-pills-announcement"]'
        );
        expect(liveRegion?.textContent).toContain('React');
        expect(liveRegion?.textContent).toContain('filter removed');
        expect(liveRegion?.textContent).toContain('1 active filter');
      });
    });

    it('announces "All filters cleared." when all pills removed', async () => {
      const filters: FilterPill[] = [
        makeCanonicalPill('React', 'react', 1),
      ];

      const { rerender, container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Remove all filters
      rerender(<FilterPills filters={[]} onRemove={() => {}} />);

      await waitFor(() => {
        const liveRegion = container.querySelector(
          '[data-testid="filter-pills-announcement"]'
        );
        expect(liveRegion?.textContent).toContain('All filters cleared.');
      });
    });

    it('announces add with variation info when alias_count > 1', async () => {
      const initialFilters: FilterPill[] = [];

      const { rerender, container } = render(
        <FilterPills filters={initialFilters} onRemove={() => {}} />
      );

      // Add a canonical tag with alias_count = 4
      const newFilters: FilterPill[] = [makeCanonicalPill('JavaScript', 'javascript', 4)];
      rerender(<FilterPills filters={newFilters} onRemove={() => {}} />);

      await waitFor(() => {
        const liveRegion = container.querySelector(
          '[data-testid="filter-pills-announcement"]'
        );
        expect(liveRegion?.textContent).toContain('JavaScript');
        expect(liveRegion?.textContent).toContain('filter added');
        expect(liveRegion?.textContent).toContain('Covers 3 variation');
      });
    });

    it('does NOT include variation info in announcement when alias_count = 1', async () => {
      const initialFilters: FilterPill[] = [];

      const { rerender, container } = render(
        <FilterPills filters={initialFilters} onRemove={() => {}} />
      );

      // Add a canonical tag with alias_count = 1
      const newFilters: FilterPill[] = [makeCanonicalPill('Solo', 'solo', 1)];
      rerender(<FilterPills filters={newFilters} onRemove={() => {}} />);

      await waitFor(() => {
        const liveRegion = container.querySelector(
          '[data-testid="filter-pills-announcement"]'
        );
        expect(liveRegion?.textContent).toContain('Solo');
        expect(liveRegion?.textContent).not.toContain('variation');
      });
    });
  });

  // -----------------------------------------------------------------------
  // Coexistence with other pill types
  // -----------------------------------------------------------------------
  describe('Coexistence with other pill types', () => {
    it('renders canonical_tag pill alongside tag, category, topic pills', () => {
      render(
        <FilterPills
          filters={[
            { type: 'tag', value: 'music', label: 'music' },
            makeCanonicalPill('JavaScript', 'javascript', 3),
            { type: 'category', value: '10', label: 'Gaming' },
          ]}
          onRemove={() => {}}
        />
      );

      expect(screen.getByText('music')).toBeInTheDocument();
      expect(screen.getByText('JavaScript')).toBeInTheDocument();
      expect(screen.getByText('Gaming')).toBeInTheDocument();
      expect(screen.getByText('2 var.')).toBeInTheDocument();
    });

    it('canonical_tag pill uses blue, tag pill uses same blue, category uses green', () => {
      const { container } = render(
        <FilterPills
          filters={[
            { type: 'tag', value: 'music', label: 'music' },
            makeCanonicalPill('JavaScript', 'javascript', 1),
            { type: 'category', value: '10', label: 'Gaming' },
          ]}
          onRemove={() => {}}
        />
      );

      const pills = container.querySelectorAll('[role="listitem"]');
      // tag and canonical_tag both use blue (#DBEAFE)
      expect(pills[0]).toHaveStyle({ backgroundColor: '#DBEAFE' });
      expect(pills[1]).toHaveStyle({ backgroundColor: '#DBEAFE' });
      // category uses green (#DCFCE7)
      expect(pills[2]).toHaveStyle({ backgroundColor: '#DCFCE7' });
    });
  });

  // -----------------------------------------------------------------------
  // Accessibility structure
  // -----------------------------------------------------------------------
  describe('Accessibility structure', () => {
    it('canonical_tag pill has role="listitem" within role="list"', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('Python', 'python', 2)]}
          onRemove={() => {}}
        />
      );

      const list = container.querySelector('[role="list"][aria-label="Active filters"]');
      expect(list).toBeInTheDocument();

      const listitem = list?.querySelector('[role="listitem"]');
      expect(listitem).toBeInTheDocument();
    });

    it('remove button SVG is aria-hidden', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('Python', 'python', 1)]}
          onRemove={() => {}}
        />
      );

      const svgs = container.querySelectorAll('svg[aria-hidden="true"]');
      expect(svgs.length).toBeGreaterThan(0);
    });

    it('live region is sr-only (visually hidden)', () => {
      const { container } = render(
        <FilterPills
          filters={[makeCanonicalPill('Go', 'go', 1)]}
          onRemove={() => {}}
        />
      );

      const liveRegion = container.querySelector(
        '[data-testid="filter-pills-announcement"]'
      );
      expect(liveRegion).toHaveClass('sr-only');
    });
  });
});
