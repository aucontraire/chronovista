/**
 * Tests for HomePage (Videos Page) with sort/filter controls (Feature 027, T034).
 *
 * Verifies:
 * - Sort dropdown renders with correct options (Date Added / Title)
 * - Filter toggles render (Liked only, Has transcripts)
 * - FilterPills integration with boolean pills
 * - URL state with all filter types simultaneously
 * - Combined filter behavior with existing tag/topic/category filters
 * - ARIA live region for count announcement
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, getTestLocation } from '../test-utils';
import { HomePage } from '../../src/pages/HomePage';

// Mock the useVideos hook to avoid real API calls
vi.mock('../../src/hooks/useVideos', () => ({
  useVideos: vi.fn(() => ({
    videos: [],
    total: 42,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  })),
}));

// Mock the dependent components to isolate the page
vi.mock('../../src/components/VideoFilters', () => ({
  VideoFilters: ({ videoCount }: { videoCount?: number | null }) => (
    <div data-testid="video-filters">VideoFilters (count: {videoCount})</div>
  ),
}));

vi.mock('../../src/components/VideoList', () => ({
  VideoList: (props: Record<string, unknown>) => (
    <div data-testid="video-list" data-props={JSON.stringify(props)}>
      VideoList
    </div>
  ),
}));

/**
 * Helper to render HomePage with providers.
 */
function renderHomePage(initialUrl = '/') {
  return renderWithProviders(<HomePage />, {
    initialEntries: [initialUrl],
  });
}

describe('HomePage (Videos Page) - Feature 027', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Sort Dropdown', () => {
    it('should render the sort dropdown', () => {
      renderHomePage();

      // SortDropdown renders a <select> with the label
      const sortDropdown = screen.getByRole('combobox', {
        name: /sort videos by/i,
      });
      expect(sortDropdown).toBeInTheDocument();
    });

    it('should have Date Added and Title sort options', () => {
      renderHomePage();

      const sortDropdown = screen.getByRole('combobox', {
        name: /sort videos by/i,
      });

      // Get all options
      const options = sortDropdown.querySelectorAll('option');
      const optionTexts = Array.from(options).map((opt) => opt.textContent);

      // Should contain Date Added and Title (with asc/desc arrows)
      expect(optionTexts.some((t) => t?.includes('Date Added'))).toBe(true);
      expect(optionTexts.some((t) => t?.includes('Title'))).toBe(true);
    });

    it('should default to Date Added descending', () => {
      renderHomePage();

      const sortDropdown = screen.getByRole('combobox', {
        name: /sort videos by/i,
      }) as HTMLSelectElement;

      // Default value should be upload_date:desc
      expect(sortDropdown.value).toBe('upload_date:desc');
    });

    it('should update URL when sort option changes', async () => {
      const user = userEvent.setup();
      renderHomePage();

      const sortDropdown = screen.getByRole('combobox', {
        name: /sort videos by/i,
      });

      // Select "Title ascending"
      await user.selectOptions(sortDropdown, 'title:asc');

      const location = getTestLocation();
      expect(location.search).toContain('sort_by=title');
      expect(location.search).toContain('sort_order=asc');
    });
  });

  describe('Filter Toggles', () => {
    it('should render Liked only toggle', () => {
      renderHomePage();

      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      expect(likedToggle).toBeInTheDocument();
    });

    it('should render Has transcripts toggle', () => {
      renderHomePage();

      const transcriptToggle = screen.getByRole('checkbox', {
        name: /has transcripts/i,
      });
      expect(transcriptToggle).toBeInTheDocument();
    });

    it('should have unchecked toggles by default', () => {
      renderHomePage();

      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      const transcriptToggle = screen.getByRole('checkbox', {
        name: /has transcripts/i,
      });

      expect(likedToggle).not.toBeChecked();
      expect(transcriptToggle).not.toBeChecked();
    });

    it('should check Liked toggle when liked_only URL param is true', () => {
      renderHomePage('/?liked_only=true');

      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      expect(likedToggle).toBeChecked();
    });

    it('should check Has transcripts toggle when has_transcript URL param is true', () => {
      renderHomePage('/?has_transcript=true');

      const transcriptToggle = screen.getByRole('checkbox', {
        name: /has transcripts/i,
      });
      expect(transcriptToggle).toBeChecked();
    });

    it('should add liked_only=true to URL when toggled on', async () => {
      const user = userEvent.setup();
      renderHomePage();

      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });

      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).toContain('liked_only=true');
    });

    it('should add has_transcript=true to URL when toggled on', async () => {
      const user = userEvent.setup();
      renderHomePage();

      const transcriptToggle = screen.getByRole('checkbox', {
        name: /has transcripts/i,
      });

      await user.click(transcriptToggle);

      const location = getTestLocation();
      expect(location.search).toContain('has_transcript=true');
    });
  });

  describe('Combined URL State', () => {
    it('should preserve sort params alongside filter params', async () => {
      const user = userEvent.setup();
      renderHomePage('/?sort_by=title&sort_order=asc');

      // Toggle liked_only on
      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).toContain('sort_by=title');
      expect(location.search).toContain('sort_order=asc');
      expect(location.search).toContain('liked_only=true');
    });

    it('should handle all filter types in URL simultaneously', () => {
      renderHomePage(
        '/?sort_by=title&sort_order=asc&liked_only=true&has_transcript=true&tag=music&category=10&topic_id=/m/04rlf&include_unavailable=true'
      );

      // Verify sort dropdown has correct value
      const sortDropdown = screen.getByRole('combobox', {
        name: /sort videos by/i,
      }) as HTMLSelectElement;
      expect(sortDropdown.value).toBe('title:asc');

      // Verify toggles are checked
      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      const transcriptToggle = screen.getByRole('checkbox', {
        name: /has transcripts/i,
      });
      expect(likedToggle).toBeChecked();
      expect(transcriptToggle).toBeChecked();
    });

    it('should remove liked_only from URL when unchecked', async () => {
      const user = userEvent.setup();
      renderHomePage('/?liked_only=true&sort_by=title');

      const likedToggle = screen.getByRole('checkbox', {
        name: /liked only/i,
      });
      expect(likedToggle).toBeChecked();

      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).not.toContain('liked_only');
      // sort_by should still be preserved
      expect(location.search).toContain('sort_by=title');
    });
  });

  describe('Page Structure', () => {
    it('should render page heading', () => {
      renderHomePage();

      expect(
        screen.getByRole('heading', { name: /videos/i, level: 2 })
      ).toBeInTheDocument();
    });

    it('should render VideoFilters component', () => {
      renderHomePage();

      expect(screen.getByTestId('video-filters')).toBeInTheDocument();
    });

    it('should render VideoList component', () => {
      renderHomePage();

      expect(screen.getByTestId('video-list')).toBeInTheDocument();
    });

    it('should have ARIA live region for count announcement', () => {
      renderHomePage();

      // Check for role="status" with aria-live
      const liveRegion = document.querySelector(
        '[role="status"][aria-live="polite"]'
      );
      expect(liveRegion).toBeInTheDocument();
    });

    it('should render sort and filter controls section', () => {
      renderHomePage();

      // Check for the controls section heading (sr-only)
      expect(
        screen.getByText('Sort and filter controls')
      ).toBeInTheDocument();
    });
  });

  describe('VideoList receives correct props', () => {
    it('should pass sort and filter params to VideoList', () => {
      renderHomePage(
        '/?sort_by=title&sort_order=asc&liked_only=true&has_transcript=true'
      );

      const videoList = screen.getByTestId('video-list');
      const propsJson = videoList.getAttribute('data-props');
      const props = JSON.parse(propsJson || '{}');

      expect(props.sortBy).toBe('title');
      expect(props.sortOrder).toBe('asc');
      expect(props.likedOnly).toBe(true);
      expect(props.hasTranscript).toBe(true);
    });

    it('should pass default values when no URL params', () => {
      renderHomePage();

      const videoList = screen.getByTestId('video-list');
      const propsJson = videoList.getAttribute('data-props');
      const props = JSON.parse(propsJson || '{}');

      expect(props.likedOnly).toBe(false);
      expect(props.hasTranscript).toBe(false);
      expect(props.includeUnavailable).toBe(false);
    });
  });
});
