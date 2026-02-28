/**
 * Tests for FilterPills boolean filter pill support (Feature 027, T033).
 *
 * Verifies:
 * - Boolean pills render alongside tag/topic/category pills
 * - Removable boolean pills call onRemove with correct type and value
 * - "Liked" and "Has transcripts" pills display when filters active
 * - Boolean pills have correct color scheme (slate)
 * - Boolean pills have proper ARIA labels
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterPills } from '../../src/components/FilterPills';

describe('FilterPills - Boolean Filter Pills (T033)', () => {
  describe('Boolean pill rendering', () => {
    it('should render boolean pills alongside tag pills', () => {
      const filters = [
        { type: 'tag' as const, value: 'music', label: 'music' },
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText('music')).toBeInTheDocument();
      expect(screen.getByText('Liked')).toBeInTheDocument();
    });

    it('should render boolean pills alongside category pills', () => {
      const filters = [
        { type: 'category' as const, value: '10', label: 'Gaming' },
        {
          type: 'boolean' as const,
          value: 'has_transcript',
          label: 'Has transcripts',
        },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText('Gaming')).toBeInTheDocument();
      expect(screen.getByText('Has transcripts')).toBeInTheDocument();
    });

    it('should render boolean pills alongside topic pills', () => {
      const filters = [
        { type: 'topic' as const, value: '/m/04rlf', label: 'Music' },
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      const musicItems = screen.getAllByText('Music');
      expect(musicItems.length).toBeGreaterThan(0);
      expect(screen.getByText('Liked')).toBeInTheDocument();
    });

    it('should render all filter types together', () => {
      const filters = [
        { type: 'tag' as const, value: 'music', label: 'music' },
        { type: 'category' as const, value: '10', label: 'Gaming' },
        { type: 'topic' as const, value: '/m/04rlf', label: 'Music Topic' },
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
        {
          type: 'boolean' as const,
          value: 'has_transcript',
          label: 'Has transcripts',
        },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText('music')).toBeInTheDocument();
      expect(screen.getByText('Gaming')).toBeInTheDocument();
      expect(screen.getByText('Music Topic')).toBeInTheDocument();
      expect(screen.getByText('Liked')).toBeInTheDocument();
      expect(screen.getByText('Has transcripts')).toBeInTheDocument();
    });

    it('should render Liked pill when liked_only filter is active', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText('Liked')).toBeInTheDocument();
    });

    it('should render Has transcripts pill when has_transcript filter is active', () => {
      const filters = [
        {
          type: 'boolean' as const,
          value: 'has_transcript',
          label: 'Has transcripts',
        },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText('Has transcripts')).toBeInTheDocument();
    });
  });

  describe('Boolean pill removal', () => {
    it('should call onRemove with boolean type and liked_only value', async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      render(<FilterPills filters={filters} onRemove={mockOnRemove} />);

      const removeButton = screen.getByRole('button', {
        name: 'Remove boolean filter: Liked',
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith('boolean', 'liked_only');
    });

    it('should call onRemove with boolean type and has_transcript value', async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      const filters = [
        {
          type: 'boolean' as const,
          value: 'has_transcript',
          label: 'Has transcripts',
        },
      ];

      render(<FilterPills filters={filters} onRemove={mockOnRemove} />);

      const removeButton = screen.getByRole('button', {
        name: 'Remove boolean filter: Has transcripts',
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith(
        'boolean',
        'has_transcript'
      );
    });

    it('should handle removing boolean pill alongside tag pill', async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      const filters = [
        { type: 'tag' as const, value: 'music', label: 'music' },
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      render(<FilterPills filters={filters} onRemove={mockOnRemove} />);

      // Remove the boolean pill
      const booleanRemove = screen.getByRole('button', {
        name: 'Remove boolean filter: Liked',
      });
      await user.click(booleanRemove);

      expect(mockOnRemove).toHaveBeenCalledWith('boolean', 'liked_only');

      // Remove the tag pill
      const tagRemove = screen.getByRole('button', {
        name: 'Remove tag filter: music',
      });
      await user.click(tagRemove);

      expect(mockOnRemove).toHaveBeenCalledWith('tag', 'music');
    });
  });

  describe('Boolean pill color scheme', () => {
    it('should apply boolean color scheme (slate)', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      const { container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: '#F1F5F9', // Light slate
        color: '#334155', // Dark slate
      });
    });
  });

  describe('Boolean pill accessibility', () => {
    it('should have ARIA list structure for boolean pills', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      const { container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const list = container.querySelector('[role="list"]');
      expect(list).toBeInTheDocument();
      expect(list).toHaveAttribute('aria-label', 'Active filters');

      const items = container.querySelectorAll('[role="listitem"]');
      expect(items).toHaveLength(1);
    });

    it('should have accessible remove button labels for boolean pills', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
        {
          type: 'boolean' as const,
          value: 'has_transcript',
          label: 'Has transcripts',
        },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(
        screen.getByRole('button', {
          name: 'Remove boolean filter: Liked',
        })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', {
          name: 'Remove boolean filter: Has transcripts',
        })
      ).toBeInTheDocument();
    });

    it('should have screen reader text for boolean filter type', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      const { container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // querySelector returns the first .sr-only which is the announcement region;
      // use querySelectorAll to find the span inside the pill label
      const srOnlyElements = container.querySelectorAll('.sr-only');
      const pillTypeSrOnly = Array.from(srOnlyElements).find(
        (el) => el.textContent?.includes('boolean:')
      );
      expect(pillTypeSrOnly).toBeTruthy();
      expect(pillTypeSrOnly).toHaveTextContent('boolean:');
    });

    it('should have 44px minimum hit area on boolean pill remove buttons', () => {
      const filters = [
        { type: 'boolean' as const, value: 'liked_only', label: 'Liked' },
      ];

      const { container } = render(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toBeInTheDocument();
      if (pill) {
        expect(pill.className).toMatch(/min-h-\[44px\]/);
      }
    });
  });
});
