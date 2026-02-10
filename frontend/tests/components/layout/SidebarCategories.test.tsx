/**
 * Tests for SidebarCategories Component - Categories Sidebar Navigation (Feature 020)
 *
 * Tasks tested:
 * - T076: List of category names with video counts
 * - T077: Integrated with existing Sidebar
 * - T078: Clickable navigation to filtered video list
 * - T079: Zero-video category handling (hidden by default with toggle)
 * - T079b: Toggle state persisted in localStorage
 * - T080: Video count displayed next to category name
 *
 * Requirements tested:
 * - FR-032: Display category names with video counts
 * - FR-033: Hide categories with 0 videos by default with toggle
 * - FR-034: Clickable navigation to filtered video lists
 *
 * Accessibility:
 * - Semantic HTML (ul/li for lists)
 * - Keyboard navigation (Tab/Enter for links)
 * - Screen reader friendly structure
 * - Focus management
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, getTestLocation } from '../../test-utils';
import { SidebarCategories } from '../../../src/components/layout/SidebarCategories';
import type { SidebarCategory } from '../../../src/hooks/useSidebarCategories';

// Mock data
const mockCategories: SidebarCategory[] = [
  {
    category_id: '10',
    name: 'Music',
    video_count: 47,
    href: '/videos?category=10',
  },
  {
    category_id: '20',
    name: 'Gaming',
    video_count: 123,
    href: '/videos?category=20',
  },
  {
    category_id: '22',
    name: 'People & Blogs',
    video_count: 0,
    href: '/videos?category=22',
  },
  {
    category_id: '24',
    name: 'Entertainment',
    video_count: 89,
    href: '/videos?category=24',
  },
  {
    category_id: '28',
    name: 'Science & Technology',
    video_count: 0,
    href: '/videos?category=28',
  },
];

describe('SidebarCategories', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
    // Mock console methods to avoid noise in test output
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  describe('Basic Rendering (T076, T080)', () => {
    it('should render section header', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      expect(screen.getByText('Categories')).toBeInTheDocument();
    });

    it('should render category list with semantic ul/li structure', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const list = screen.getByRole('list');
      expect(list).toBeInTheDocument();
      expect(list.tagName).toBe('UL');
    });

    it('should render category names', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Should only show categories with video_count > 0 by default (FR-033)
      expect(screen.getByText('Music')).toBeInTheDocument();
      expect(screen.getByText('Gaming')).toBeInTheDocument();
      expect(screen.getByText('Entertainment')).toBeInTheDocument();
    });

    it('should display video count next to each category name (T080)', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      expect(screen.getByText('47')).toBeInTheDocument();
      expect(screen.getByText('123')).toBeInTheDocument();
      expect(screen.getByText('89')).toBeInTheDocument();
    });

    it('should render loading state', () => {
      renderWithProviders(
        <SidebarCategories categories={[]} isLoading={true} />
      );

      expect(screen.getByText('Categories')).toBeInTheDocument();
      // Check for loading skeleton (using class)
      const container = screen.getByText('Categories').parentElement;
      expect(container?.querySelector('.animate-pulse')).toBeInTheDocument();
    });

    it('should render empty state when no categories', () => {
      renderWithProviders(
        <SidebarCategories categories={[]} isLoading={false} />
      );

      expect(screen.getByText('No categories available')).toBeInTheDocument();
    });
  });

  describe('Clickable Navigation (T078, FR-034)', () => {
    it('should render categories as links', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const musicLink = screen.getByRole('link', { name: /Music/ });
      expect(musicLink).toBeInTheDocument();
      expect(musicLink).toHaveAttribute('href', '/videos?category=10');
    });

    it('should navigate to filtered video list on click', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />,
        { initialEntries: ['/'] }
      );

      const gamingLink = screen.getByRole('link', { name: /Gaming/ });
      await user.click(gamingLink);

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.pathname).toBe('/videos');
        expect(location.search).toBe('?category=20');
      });
    });

    it('should have proper href for each category', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const musicLink = screen.getByRole('link', { name: /Music/ });
      const gamingLink = screen.getByRole('link', { name: /Gaming/ });
      const entertainmentLink = screen.getByRole('link', { name: /Entertainment/ });

      expect(musicLink).toHaveAttribute('href', '/videos?category=10');
      expect(gamingLink).toHaveAttribute('href', '/videos?category=20');
      expect(entertainmentLink).toHaveAttribute('href', '/videos?category=24');
    });
  });

  describe('Zero-Video Category Handling (T079, FR-033)', () => {
    it('should hide categories with 0 videos by default', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Categories with video_count > 0 should be visible
      expect(screen.getByText('Music')).toBeInTheDocument();
      expect(screen.getByText('Gaming')).toBeInTheDocument();
      expect(screen.getByText('Entertainment')).toBeInTheDocument();

      // Categories with video_count === 0 should be hidden
      expect(screen.queryByText('People & Blogs')).not.toBeInTheDocument();
      expect(screen.queryByText('Science & Technology')).not.toBeInTheDocument();
    });

    it('should show "Show all" toggle button when there are hidden categories', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      expect(toggleButton).toBeInTheDocument();
      expect(toggleButton).toHaveTextContent('Show all (2 empty)');
    });

    it('should not show toggle button when all categories have videos', () => {
      const categoriesWithVideos = mockCategories.filter(
        (c) => c.video_count > 0
      );

      renderWithProviders(
        <SidebarCategories categories={categoriesWithVideos} isLoading={false} />
      );

      expect(
        screen.queryByRole('button')
      ).not.toBeInTheDocument();
    });

    it('should show hidden categories when toggle is clicked', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Initially hidden
      expect(screen.queryByText('People & Blogs')).not.toBeInTheDocument();

      // Click toggle
      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      await user.click(toggleButton);

      // Now visible
      await waitFor(() => {
        expect(screen.getByText('People & Blogs')).toBeInTheDocument();
        expect(screen.getByText('Science & Technology')).toBeInTheDocument();
      });
    });

    it('should change toggle button text when showing all', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Hide empty categories/ })
        ).toBeInTheDocument();
      });
    });

    it('should hide empty categories again when toggle is clicked twice', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const showButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      await user.click(showButton);

      await waitFor(() => {
        expect(screen.getByText('People & Blogs')).toBeInTheDocument();
      });

      const hideButton = screen.getByRole('button', {
        name: /Hide empty categories/,
      });
      await user.click(hideButton);

      await waitFor(() => {
        expect(screen.queryByText('People & Blogs')).not.toBeInTheDocument();
      });
    });

    it('should have proper aria-expanded attribute on toggle button', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      expect(toggleButton).toHaveAttribute('aria-expanded', 'false');

      await user.click(toggleButton);

      await waitFor(() => {
        const expandedButton = screen.getByRole('button', {
          name: /Hide empty categories/,
        });
        expect(expandedButton).toHaveAttribute('aria-expanded', 'true');
      });
    });
  });

  describe('LocalStorage Persistence (T079b)', () => {
    it('should persist show state to localStorage', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(localStorage.getItem('chronovista.sidebar.showAllCategories')).toBe(
          'true'
        );
      });
    });

    it('should persist hide state to localStorage', async () => {
      // Start with showAll = true
      localStorage.setItem('chronovista.sidebar.showAllCategories', 'true');

      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', {
        name: /Hide empty categories/,
      });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(localStorage.getItem('chronovista.sidebar.showAllCategories')).toBe(
          'false'
        );
      });
    });

    it('should load initial state from localStorage', () => {
      localStorage.setItem('chronovista.sidebar.showAllCategories', 'true');

      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Should show all categories including empty ones
      expect(screen.getByText('People & Blogs')).toBeInTheDocument();
      expect(screen.getByText('Science & Technology')).toBeInTheDocument();
    });

    it('should default to false when localStorage is empty', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Should hide empty categories by default
      expect(screen.queryByText('People & Blogs')).not.toBeInTheDocument();
      expect(screen.queryByText('Science & Technology')).not.toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should use semantic list structure', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const list = screen.getByRole('list');
      expect(list.tagName).toBe('UL');

      const items = screen.getAllByRole('listitem');
      expect(items.length).toBeGreaterThan(0);
      items.forEach((item) => {
        expect(item.tagName).toBe('LI');
      });
    });

    it('should have keyboard navigable links', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const links = screen.getAllByRole('link');
      links.forEach((link) => {
        expect(link).toHaveAttribute('href');
      });
    });

    it('should have focus styles on links', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const musicLink = screen.getByRole('link', { name: /Music/ });
      expect(musicLink).toHaveClass('focus:outline-none');
      expect(musicLink).toHaveClass('focus:ring-2');
      expect(musicLink).toHaveClass('focus:ring-blue-500');
    });

    it('should have focus styles on toggle button', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      expect(toggleButton).toHaveClass('focus:outline-none');
      expect(toggleButton).toHaveClass('focus:ring-2');
      expect(toggleButton).toHaveClass('focus:ring-blue-500');
    });

    it('should have descriptive aria-label on toggle button', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      expect(toggleButton).toHaveAttribute(
        'aria-label',
        'Show 2 empty categories'
      );
    });

    it('should support keyboard navigation with Tab', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Tab through links
      await user.tab();
      const musicLink = screen.getByRole('link', { name: /Music/ });
      expect(musicLink).toHaveFocus();

      await user.tab();
      const gamingLink = screen.getByRole('link', { name: /Gaming/ });
      expect(gamingLink).toHaveFocus();
    });

    it('should support keyboard activation of links with Enter', async () => {
      const { user } = renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />,
        { initialEntries: ['/'] }
      );

      const musicLink = screen.getByRole('link', { name: /Music/ });
      musicLink.focus();
      await user.keyboard('{Enter}');

      await waitFor(() => {
        const location = getTestLocation();
        expect(location.pathname).toBe('/videos');
        expect(location.search).toBe('?category=10');
      });
    });
  });

  describe('Visual Styling', () => {
    it('should have muted styling for video counts (T080)', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      // Check that counts are in separate spans with muted classes
      const musicLink = screen.getByRole('link', { name: /Music/ });
      const countSpan = musicLink.querySelector('.text-gray-500');
      expect(countSpan).toBeInTheDocument();
      expect(countSpan).toHaveTextContent('47');
    });

    it('should have hover styles on links', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const musicLink = screen.getByRole('link', { name: /Music/ });
      expect(musicLink).toHaveClass('hover:bg-slate-800');
      expect(musicLink).toHaveClass('hover:text-white');
    });

    it('should have hover styles on toggle button', () => {
      renderWithProviders(
        <SidebarCategories categories={mockCategories} isLoading={false} />
      );

      const toggleButton = screen.getByRole('button', { name: /Show 2 empty categories/ });
      expect(toggleButton).toHaveClass('hover:text-blue-300');
      expect(toggleButton).toHaveClass('hover:underline');
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty categories array', () => {
      renderWithProviders(<SidebarCategories categories={[]} isLoading={false} />);

      expect(screen.getByText('No categories available')).toBeInTheDocument();
      expect(screen.queryByRole('list')).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: /Show all/ })
      ).not.toBeInTheDocument();
    });

    it('should handle all categories having zero videos', () => {
      const emptyCategories = mockCategories.map((c) => ({
        ...c,
        video_count: 0,
      }));

      renderWithProviders(
        <SidebarCategories categories={emptyCategories} isLoading={false} />
      );

      // Should show toggle button
      const toggleButton = screen.getByRole('button', { name: /Show 5 empty categories/ });
      expect(toggleButton).toBeInTheDocument();
      expect(toggleButton).toHaveTextContent('Show all (5 empty)');
    });

    it('should handle single category', () => {
      const singleCategory = [mockCategories[0]];

      renderWithProviders(
        <SidebarCategories categories={singleCategory} isLoading={false} />
      );

      expect(screen.getByText('Music')).toBeInTheDocument();
      expect(screen.getByText('47')).toBeInTheDocument();
    });

    it('should truncate long category names', () => {
      const longNameCategory: SidebarCategory = {
        category_id: '99',
        name: 'This Is A Very Long Category Name That Should Be Truncated',
        video_count: 5,
        href: '/videos?category=99',
      };

      renderWithProviders(
        <SidebarCategories categories={[longNameCategory]} isLoading={false} />
      );

      const link = screen.getByRole('link', {
        name: /This Is A Very Long Category Name/,
      });
      const nameSpan = link.querySelector('.truncate');
      expect(nameSpan).toBeInTheDocument();
    });
  });
});
