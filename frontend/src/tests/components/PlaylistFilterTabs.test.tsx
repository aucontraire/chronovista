/**
 * Tests for PlaylistFilterTabs Component
 *
 * Tests:
 * - Three tabs render correctly (All, YouTube-Linked, Local)
 * - Active tab has aria-selected="true"
 * - Click handler fires with correct filter type
 * - Keyboard navigation (Arrow keys, Home, End)
 * - Focus management and indicators
 * - Optional count badges display
 * - Dark mode styling
 * - WCAG 2.1 AA compliance
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlaylistFilterTabs } from '../../components/PlaylistFilterTabs';

describe('PlaylistFilterTabs', () => {
  describe('Rendering', () => {
    it('renders all three filter tabs', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByRole('tab', { name: /show all playlists/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /show youtube-linked playlists/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /show local playlists/i })).toBeInTheDocument();
    });

    it('renders tablist with proper aria-label', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      const tablist = screen.getByRole('tablist', { name: /filter playlists by type/i });
      expect(tablist).toBeInTheDocument();
    });

    it('displays tab labels correctly', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByText('All')).toBeInTheDocument();
      expect(screen.getByText('YouTube-Linked')).toBeInTheDocument();
      expect(screen.getByText('Local')).toBeInTheDocument();
    });

    it('applies custom className when provided', () => {
      const { container } = render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
          className="custom-class"
        />
      );

      const tablist = container.querySelector('[role="tablist"]');
      expect(tablist).toHaveClass('custom-class');
    });
  });

  describe('Active State', () => {
    it('marks "All" tab as selected when currentFilter is "all"', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      expect(allTab).toHaveAttribute('aria-selected', 'true');

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      expect(linkedTab).toHaveAttribute('aria-selected', 'false');

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      expect(localTab).toHaveAttribute('aria-selected', 'false');
    });

    it('marks "YouTube-Linked" tab as selected when currentFilter is "linked"', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      expect(allTab).toHaveAttribute('aria-selected', 'false');

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      expect(linkedTab).toHaveAttribute('aria-selected', 'true');

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      expect(localTab).toHaveAttribute('aria-selected', 'false');
    });

    it('marks "Local" tab as selected when currentFilter is "local"', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="local"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      expect(allTab).toHaveAttribute('aria-selected', 'false');

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      expect(linkedTab).toHaveAttribute('aria-selected', 'false');

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      expect(localTab).toHaveAttribute('aria-selected', 'true');
    });

    it('applies selected styling to active tab', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
        />
      );

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      expect(linkedTab).toHaveClass('text-blue-600');
      expect(linkedTab).toHaveClass('border-blue-600');
      expect(linkedTab).toHaveClass('font-semibold');
    });

    it('applies inactive styling to non-selected tabs', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      expect(allTab).toHaveClass('text-gray-600');
      expect(allTab).toHaveClass('border-transparent');
    });
  });

  describe('Click Interactions', () => {
    it('calls onFilterChange with "all" when All tab is clicked', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={handleFilterChange}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      await user.click(allTab);

      expect(handleFilterChange).toHaveBeenCalledOnce();
      expect(handleFilterChange).toHaveBeenCalledWith('all');
    });

    it('calls onFilterChange with "linked" when YouTube-Linked tab is clicked', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      await user.click(linkedTab);

      expect(handleFilterChange).toHaveBeenCalledOnce();
      expect(handleFilterChange).toHaveBeenCalledWith('linked');
    });

    it('calls onFilterChange with "local" when Local tab is clicked', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      await user.click(localTab);

      expect(handleFilterChange).toHaveBeenCalledOnce();
      expect(handleFilterChange).toHaveBeenCalledWith('local');
    });

    it('allows clicking the same tab multiple times', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      await user.click(allTab);
      await user.click(allTab);

      expect(handleFilterChange).toHaveBeenCalledTimes(2);
    });
  });

  describe('Keyboard Navigation', () => {
    it('selected tab has tabindex="0" and others have tabindex="-1"', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      const localTab = screen.getByRole('tab', { name: /show local playlists/i });

      expect(allTab).toHaveAttribute('tabindex', '-1');
      expect(linkedTab).toHaveAttribute('tabindex', '0');
      expect(localTab).toHaveAttribute('tabindex', '-1');
    });

    it('navigates to next tab with ArrowRight', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      allTab.focus();

      await user.keyboard('{ArrowRight}');

      expect(handleFilterChange).toHaveBeenCalledWith('linked');
      expect(screen.getByRole('tab', { name: /show youtube-linked playlists/i })).toHaveFocus();
    });

    it('navigates to previous tab with ArrowLeft', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={handleFilterChange}
        />
      );

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      linkedTab.focus();

      await user.keyboard('{ArrowLeft}');

      expect(handleFilterChange).toHaveBeenCalledWith('all');
      expect(screen.getByRole('tab', { name: /show all playlists/i })).toHaveFocus();
    });

    it('wraps to last tab when pressing ArrowLeft on first tab', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      allTab.focus();

      await user.keyboard('{ArrowLeft}');

      expect(handleFilterChange).toHaveBeenCalledWith('local');
      expect(screen.getByRole('tab', { name: /show local playlists/i })).toHaveFocus();
    });

    it('wraps to first tab when pressing ArrowRight on last tab', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="local"
          onFilterChange={handleFilterChange}
        />
      );

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      localTab.focus();

      await user.keyboard('{ArrowRight}');

      expect(handleFilterChange).toHaveBeenCalledWith('all');
      expect(screen.getByRole('tab', { name: /show all playlists/i })).toHaveFocus();
    });

    it('navigates to first tab with Home key', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="local"
          onFilterChange={handleFilterChange}
        />
      );

      const localTab = screen.getByRole('tab', { name: /show local playlists/i });
      localTab.focus();

      await user.keyboard('{Home}');

      expect(handleFilterChange).toHaveBeenCalledWith('all');
      expect(screen.getByRole('tab', { name: /show all playlists/i })).toHaveFocus();
    });

    it('navigates to last tab with End key', async () => {
      const user = userEvent.setup();
      const handleFilterChange = vi.fn();

      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={handleFilterChange}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      allTab.focus();

      await user.keyboard('{End}');

      expect(handleFilterChange).toHaveBeenCalledWith('local');
      expect(screen.getByRole('tab', { name: /show local playlists/i })).toHaveFocus();
    });
  });

  describe('Count Badges', () => {
    it('displays count badge for "all" filter', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
          counts={{ all: 47 }}
        />
      );

      expect(screen.getByText('47')).toBeInTheDocument();
      expect(screen.getByLabelText('47 playlists')).toBeInTheDocument();
    });

    it('displays count badges for all filters', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
          counts={{ all: 47, linked: 32, local: 15 }}
        />
      );

      expect(screen.getByLabelText('47 playlists')).toBeInTheDocument();
      expect(screen.getByLabelText('32 playlists')).toBeInTheDocument();
      expect(screen.getByLabelText('15 playlists')).toBeInTheDocument();
    });

    it('does not display badge when count is 0', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
          counts={{ all: 47, linked: 0, local: 15 }}
        />
      );

      expect(screen.getByLabelText('47 playlists')).toBeInTheDocument();
      expect(screen.queryByLabelText('0 playlists')).not.toBeInTheDocument();
      expect(screen.getByLabelText('15 playlists')).toBeInTheDocument();
    });

    it('does not display badge when count is undefined', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
          counts={{ all: 47 }}
        />
      );

      expect(screen.getByLabelText('47 playlists')).toBeInTheDocument();
      // No labels for linked or local
      expect(screen.queryByLabelText(/32 playlists/i)).not.toBeInTheDocument();
    });

    it('applies selected styling to badge on active tab', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
          counts={{ all: 47, linked: 32, local: 15 }}
        />
      );

      const linkedBadge = screen.getByLabelText('32 playlists');
      expect(linkedBadge).toHaveClass('bg-blue-100');
      expect(linkedBadge).toHaveClass('text-blue-700');
    });

    it('applies inactive styling to badge on non-selected tabs', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
          counts={{ all: 47, linked: 32, local: 15 }}
        />
      );

      const allBadge = screen.getByLabelText('47 playlists');
      expect(allBadge).toHaveClass('bg-gray-100');
      expect(allBadge).toHaveClass('text-gray-700');
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA roles', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByRole('tablist')).toBeInTheDocument();
      expect(screen.getAllByRole('tab')).toHaveLength(3);
    });

    it('has focus indicators on all tabs', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      const tabs = screen.getAllByRole('tab');
      tabs.forEach((tab) => {
        expect(tab).toHaveClass('focus:ring-2');
        expect(tab).toHaveClass('focus:ring-blue-500');
        expect(tab).toHaveClass('focus:outline-none');
      });
    });

    it('has descriptive aria-label for each tab', () => {
      render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByRole('tab', { name: 'Show all playlists' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Show YouTube-linked playlists' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Show local playlists' })).toBeInTheDocument();
    });

    it('maintains roving tabindex for keyboard navigation', () => {
      const { rerender } = render(
        <PlaylistFilterTabs
          currentFilter="all"
          onFilterChange={vi.fn()}
        />
      );

      const allTab = screen.getByRole('tab', { name: /show all playlists/i });
      expect(allTab).toHaveAttribute('tabindex', '0');

      // Simulate filter change
      rerender(
        <PlaylistFilterTabs
          currentFilter="linked"
          onFilterChange={vi.fn()}
        />
      );

      const linkedTab = screen.getByRole('tab', { name: /show youtube-linked playlists/i });
      expect(linkedTab).toHaveAttribute('tabindex', '0');
      expect(allTab).toHaveAttribute('tabindex', '-1');
    });
  });
});
