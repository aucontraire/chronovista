/**
 * Tests for ClassificationSection component.
 *
 * Validates:
 * - T038: Organized subsections for tags, category, and topics
 * - T039: Clickable tag links navigate to filtered video lists
 * - T040: URL encoding for special characters in tags
 * - T041: Hover styling indicates clickability
 * - T042: Browser back button support (handled by react-router-dom)
 * - T067: "Classification & Context" section header
 * - T068: Playlists subsection with clickable playlist links
 * - T069: Graceful empty state for all subsections (FR-006, FR-032)
 * - T070: Labeled subsections for Tags, Categories, Topics, Playlists
 * - FR-ACC-003: WCAG AA compliant color contrast (7.0:1+ ratio)
 * - Empty state handling for tags, category, topics, and playlists
 * - Accessibility: semantic HTML, ARIA labels, keyboard navigation
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { ClassificationSection } from '../../src/components/ClassificationSection';
import type { TopicSummary } from '../../src/types/video';
import type { VideoPlaylistMembership } from '../../src/types/playlist';

describe('ClassificationSection', () => {
  const mockTopics: TopicSummary[] = [
    {
      topic_id: '/m/04rlf',
      name: 'Music',
      parent_path: null,
    },
    {
      topic_id: '/m/064t9',
      name: 'Pop Music',
      parent_path: 'Arts > Music',
    },
  ];

  const mockPlaylists: VideoPlaylistMembership[] = [
    {
      playlist_id: 'PLtest123',
      title: 'My Favorite Videos',
      position: 5,
      is_linked: true,
      privacy_status: 'public',
    },
    {
      playlist_id: 'PLtest456',
      title: 'Watch Later',
      position: 10,
      is_linked: true,
      privacy_status: 'private',
    },
  ];

  describe('Section Structure (T038, T067, T070)', () => {
    it('should render section heading (T067)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      expect(screen.getByRole('heading', { name: 'Classification & Context' })).toBeInTheDocument();
    });

    it('should have aria-labelledby attribute linking to heading (T067)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const section = screen.getByRole('heading', { name: 'Classification & Context' }).closest('section');
      const heading = screen.getByRole('heading', { name: 'Classification & Context' });

      expect(section).toHaveAttribute('aria-labelledby', 'classification-heading');
      expect(heading).toHaveAttribute('id', 'classification-heading');
    });

    it('should render all four subsections (T070)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react', 'typescript']}
          categoryId='28'
          categoryName='Science & Technology'
          topics={mockTopics}
          playlists={mockPlaylists}
        />
      );

      expect(screen.getByText('Tags')).toBeInTheDocument();
      expect(screen.getByText('Category')).toBeInTheDocument();
      expect(screen.getByText('Topics')).toBeInTheDocument();
      expect(screen.getByText('Playlists')).toBeInTheDocument();
    });
  });

  describe('Tags Subsection (T039, T040, T041)', () => {
    it('should render tags as clickable links', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react', 'typescript']}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const reactLink = screen.getByRole('link', { name: 'Filter videos by tag: react' });
      const tsLink = screen.getByRole('link', { name: 'Filter videos by tag: typescript' });

      expect(reactLink).toBeInTheDocument();
      expect(tsLink).toBeInTheDocument();
      expect(reactLink).toHaveAttribute('href', '/videos?tag=react');
      expect(tsLink).toHaveAttribute('href', '/videos?tag=typescript');
    });

    it('should URL encode special characters in tags (T040)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['C++', 'music & arts', 'rock/metal']}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const cppLink = screen.getByRole('link', { name: 'Filter videos by tag: C++' });
      const musicLink = screen.getByRole('link', { name: 'Filter videos by tag: music & arts' });
      const rockLink = screen.getByRole('link', { name: 'Filter videos by tag: rock/metal' });

      expect(cppLink).toHaveAttribute('href', '/videos?tag=C%2B%2B');
      expect(musicLink).toHaveAttribute('href', '/videos?tag=music%20%26%20arts');
      expect(rockLink).toHaveAttribute('href', '/videos?tag=rock%2Fmetal');
    });

    it('should apply hover and focus styles to tags (T041)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react']}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const tagLink = screen.getByRole('link', { name: 'Filter videos by tag: react' });

      // Check for hover classes
      expect(tagLink).toHaveClass('hover:underline');
      expect(tagLink).toHaveClass('hover:brightness-95');

      // Check for focus styles
      expect(tagLink).toHaveClass('focus:outline-none');
      expect(tagLink).toHaveClass('focus:ring-2');
      expect(tagLink).toHaveClass('focus:ring-offset-2');
    });

    it('should show "None" when no tags exist', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      // Find the Tags subsection
      const tagsSubsection = screen.getByText('Tags').closest('div');
      expect(tagsSubsection).toBeInTheDocument();

      // Should show "None" with muted styling
      const noneText = tagsSubsection?.querySelector('.text-gray-400');
      expect(noneText).toBeInTheDocument();
      expect(noneText).toHaveTextContent('None');
    });

    it('should apply filter color tokens (FR-ACC-003)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react']}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const tagLink = screen.getByRole('link', { name: 'Filter videos by tag: react' });

      // Check for inline styles from filterColors.tag
      expect(tagLink).toHaveStyle({
        backgroundColor: '#DBEAFE',
        color: '#1E40AF',
        borderColor: '#BFDBFE',
      });
    });
  });

  describe('Category Subsection', () => {
    it('should render category as clickable link', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId='28'
          categoryName='Science & Technology'
          topics={[]}
        />
      );

      const categoryLink = screen.getByRole('link', {
        name: 'Filter videos by category: Science & Technology',
      });

      expect(categoryLink).toBeInTheDocument();
      expect(categoryLink).toHaveAttribute('href', '/videos?category=28');
      expect(categoryLink).toHaveTextContent('Science & Technology');
    });

    it('should URL encode category ID', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId='28&special'
          categoryName='Science & Technology'
          topics={[]}
        />
      );

      const categoryLink = screen.getByRole('link', {
        name: 'Filter videos by category: Science & Technology',
      });

      expect(categoryLink).toHaveAttribute('href', '/videos?category=28%26special');
    });

    it('should show "None" when no category exists', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const categorySubsection = screen.getByText('Category').closest('div');
      expect(categorySubsection).toBeInTheDocument();

      const noneText = categorySubsection?.querySelector('.text-gray-400');
      expect(noneText).toBeInTheDocument();
      expect(noneText).toHaveTextContent('None');
    });

    it('should apply filter color tokens (FR-ACC-003)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId='28'
          categoryName='Science & Technology'
          topics={[]}
        />
      );

      const categoryLink = screen.getByRole('link', {
        name: 'Filter videos by category: Science & Technology',
      });

      expect(categoryLink).toHaveStyle({
        backgroundColor: '#DCFCE7',
        color: '#166534',
        borderColor: '#BBF7D0',
      });
    });
  });

  describe('Topics Subsection', () => {
    it('should render topics as clickable links', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={mockTopics}
        />
      );

      const musicLink = screen.getByRole('link', { name: 'Filter videos by topic: Music' });
      const popLink = screen.getByRole('link', {
        name: 'Filter videos by topic: Pop Music (Arts > Music)',
      });

      expect(musicLink).toBeInTheDocument();
      expect(popLink).toBeInTheDocument();
      expect(musicLink).toHaveAttribute('href', '/videos?topic_id=%2Fm%2F04rlf');
      expect(popLink).toHaveAttribute('href', '/videos?topic_id=%2Fm%2F064t9');
    });

    it('should display topic with parent path hierarchy', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={mockTopics}
        />
      );

      const popLink = screen.getByRole('link', {
        name: 'Filter videos by topic: Pop Music (Arts > Music)',
      });

      expect(popLink).toHaveTextContent('Arts > Music > Pop Music');
    });

    it('should display topic without parent path for top-level topics', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={mockTopics}
        />
      );

      const musicLink = screen.getByRole('link', { name: 'Filter videos by topic: Music' });

      expect(musicLink).toHaveTextContent('Music');
    });

    it('should show "None" when no topics exist', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const topicsSubsection = screen.getByText('Topics').closest('div');
      expect(topicsSubsection).toBeInTheDocument();

      const noneText = topicsSubsection?.querySelector('.text-gray-400');
      expect(noneText).toBeInTheDocument();
      expect(noneText).toHaveTextContent('None');
    });

    it('should apply filter color tokens (FR-ACC-003)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={mockTopics}
        />
      );

      const musicLink = screen.getByRole('link', { name: 'Filter videos by topic: Music' });

      expect(musicLink).toHaveStyle({
        backgroundColor: '#F3E8FF',
        color: '#6B21A8',
        borderColor: '#E9D5FF',
      });
    });
  });

  describe('Playlists Subsection (T068, T069, T070)', () => {
    it('should render playlists as clickable links (T068)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={mockPlaylists}
        />
      );

      const favoritesLink = screen.getByRole('link', { name: 'View playlist: My Favorite Videos' });
      const watchLaterLink = screen.getByRole('link', { name: 'View playlist: Watch Later' });

      expect(favoritesLink).toBeInTheDocument();
      expect(watchLaterLink).toBeInTheDocument();
      expect(favoritesLink).toHaveAttribute('href', '/playlists/PLtest123');
      expect(watchLaterLink).toHaveAttribute('href', '/playlists/PLtest456');
    });

    it('should show "None" when no playlists exist (T069)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={[]}
        />
      );

      const playlistsSubsection = screen.getByText('Playlists').closest('div');
      expect(playlistsSubsection).toBeInTheDocument();

      const noneText = playlistsSubsection?.querySelector('.text-gray-400');
      expect(noneText).toBeInTheDocument();
      expect(noneText).toHaveTextContent('None');
    });

    it('should show "None" when playlists prop is undefined (T069)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const playlistsSubsection = screen.getByText('Playlists').closest('div');
      const noneText = playlistsSubsection?.querySelector('.text-gray-400');
      expect(noneText).toHaveTextContent('None');
    });

    it('should apply filter color tokens (FR-ACC-003)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={mockPlaylists}
        />
      );

      const favoritesLink = screen.getByRole('link', { name: 'View playlist: My Favorite Videos' });

      expect(favoritesLink).toHaveStyle({
        backgroundColor: '#FED7AA',
        color: '#9A3412',
        borderColor: '#FDBA74',
      });
    });

    it('should have Playlists subsection label (T070)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={mockPlaylists}
        />
      );

      const playlistsLabel = screen.getByText('Playlists');
      expect(playlistsLabel).toBeInTheDocument();
      expect(playlistsLabel.tagName).toBe('H4');
    });
  });

  describe('Accessibility', () => {
    it('should have semantic HTML structure', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react']}
          categoryId='28'
          categoryName='Science & Technology'
          topics={mockTopics}
        />
      );

      // Section element
      const section = screen.getByRole('heading', { name: 'Classification & Context' }).closest('section');
      expect(section).toBeInTheDocument();

      // Heading hierarchy
      expect(screen.getByRole('heading', { name: 'Classification & Context', level: 3 })).toBeInTheDocument();
    });

    it('should have descriptive ARIA labels on links', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react']}
          categoryId='28'
          categoryName='Science & Technology'
          topics={mockTopics}
        />
      );

      const tagLink = screen.getByRole('link', { name: 'Filter videos by tag: react' });
      const categoryLink = screen.getByRole('link', {
        name: 'Filter videos by category: Science & Technology',
      });
      const topicLink = screen.getByRole('link', { name: 'Filter videos by topic: Music' });

      expect(tagLink).toHaveAccessibleName('Filter videos by tag: react');
      expect(categoryLink).toHaveAccessibleName('Filter videos by category: Science & Technology');
      expect(topicLink).toHaveAccessibleName('Filter videos by topic: Music');
    });

    it('should be keyboard navigable', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react']}
          categoryId='28'
          categoryName='Science & Technology'
          topics={mockTopics}
        />
      );

      const tagLink = screen.getByRole('link', { name: 'Filter videos by tag: react' });

      // Link elements are inherently keyboard focusable
      expect(tagLink.tagName).toBe('A');
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty arrays gracefully (T069)', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={[]}
        />
      );

      // Should render section with "None" for all subsections
      expect(screen.getByRole('heading', { name: 'Classification & Context' })).toBeInTheDocument();
      expect(screen.getByText('Tags')).toBeInTheDocument();
      expect(screen.getByText('Category')).toBeInTheDocument();
      expect(screen.getByText('Topics')).toBeInTheDocument();
      expect(screen.getByText('Playlists')).toBeInTheDocument();

      // All subsections should show "None"
      const noneElements = screen.getAllByText('None');
      expect(noneElements).toHaveLength(4);
    });

    it('should handle category with null ID but existing name', () => {
      renderWithProviders(
        <ClassificationSection
          tags={[]}
          categoryId={null}
          categoryName='Science & Technology'
          topics={[]}
        />
      );

      // Should treat as no category (since ID is null)
      const categorySubsection = screen.getByText('Category').closest('div');
      const noneText = categorySubsection?.querySelector('.text-gray-400');
      expect(noneText).toHaveTextContent('None');
    });

    it('should handle long tag names', () => {
      const longTag = 'This is a very long tag name that might wrap to multiple lines';
      renderWithProviders(
        <ClassificationSection
          tags={[longTag]}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      const tagLink = screen.getByRole('link', { name: `Filter videos by tag: ${longTag}` });
      expect(tagLink).toHaveTextContent(longTag);
    });

    it('should handle multiple tags with same name', () => {
      renderWithProviders(
        <ClassificationSection
          tags={['react', 'react', 'typescript']}
          categoryId={null}
          categoryName={null}
          topics={[]}
        />
      );

      // React keys should prevent duplicate rendering
      const reactLinks = screen.getAllByText('react');
      expect(reactLinks.length).toBeGreaterThanOrEqual(1);
    });
  });
});
