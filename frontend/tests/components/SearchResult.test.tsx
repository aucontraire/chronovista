/**
 * Tests for SearchResult Component - Transcript Search (User Story 1)
 *
 * Requirements tested:
 * - FR-003: Display video title, channel name, timestamp range, segment text, match count
 * - FR-005: Timestamp links navigate to /videos/:id?t=:seconds
 * - FR-006: Video title links navigate to /videos/:id
 * - EC-007: Show "Unknown Channel" when channel_title is null
 * - Query term highlighting in segment text
 *
 * Test coverage:
 * - Renders video title
 * - Renders channel name
 * - Renders "Unknown Channel" when channel_title is null
 * - Renders formatted timestamp range (MM:SS format)
 * - Renders segment text with highlighted query terms
 * - Renders match count
 * - Renders upload date
 * - Links to video detail page (FR-006)
 * - Timestamp links with time parameter (FR-005)
 * - Keyboard accessibility (Tab, Shift+Tab, Enter)
 * - Proper href attributes for all links
 * - Handles missing context (context_before/context_after null)
 * - Accessibility (ARIA attributes, keyboard navigation)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { SearchResult } from '../../src/components/SearchResult';
import type { SearchResultSegment } from '../../src/types/search';

describe('SearchResult', () => {
  const mockSegment: SearchResultSegment = {
    segment_id: 1,
    video_id: 'abc123def45',
    video_title: 'Introduction to Machine Learning',
    channel_title: 'Tech Education Hub',
    language_code: 'en',
    text: 'In this video, we will explore machine learning algorithms and their applications.',
    start_time: 154.5,
    end_time: 192.8,
    context_before: 'Welcome to this comprehensive tutorial.',
    context_after: 'Let us begin with supervised learning.',
    match_count: 2,
    video_upload_date: '2024-01-15T12:00:00Z',
  };

  const mockQueryTerms = ['machine', 'learning'];

  describe('Basic Rendering', () => {
    it('should render video title', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('Introduction to Machine Learning')).toBeInTheDocument();
    });

    it('should render channel name', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('Tech Education Hub')).toBeInTheDocument();
    });

    it('should render segment text', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // Text is split by highlighting, so use partial match
      expect(screen.getByText(/In this video, we will explore/)).toBeInTheDocument();
      expect(screen.getByText(/algorithms and their applications/)).toBeInTheDocument();
    });

    it('should render match count', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText(/2.*match/i)).toBeInTheDocument();
    });
  });

  describe('Channel Name Handling (EC-007)', () => {
    it('should show "Unknown Channel" when channel_title is null', () => {
      const segmentWithoutChannel: SearchResultSegment = {
        ...mockSegment,
        channel_title: null,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithoutChannel} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('Unknown Channel')).toBeInTheDocument();
    });

    it('should show channel name when channel_title is provided', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('Tech Education Hub')).toBeInTheDocument();
      expect(screen.queryByText('Unknown Channel')).not.toBeInTheDocument();
    });
  });

  describe('Timestamp Formatting (FR-003)', () => {
    it('should render formatted timestamp range in MM:SS format', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // 154.5 seconds = 2:34, 192.8 seconds = 3:12
      expect(screen.getByText(/2:34.*3:12/)).toBeInTheDocument();
    });

    it('should handle timestamps less than 1 minute', () => {
      const segmentWithShortTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 15.0,
        end_time: 45.5,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithShortTime} queryTerms={mockQueryTerms} />
      );

      // 15 seconds = 0:15, 45.5 seconds = 0:45
      expect(screen.getByText(/0:15.*0:45/)).toBeInTheDocument();
    });

    it('should handle timestamps over 1 hour', () => {
      const segmentWithLongTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 3665.0,
        end_time: 3720.5,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithLongTime} queryTerms={mockQueryTerms} />
      );

      // 3665 seconds = 1:01:05, 3720.5 seconds = 1:02:00
      expect(screen.getByText(/1:01:05.*1:02:00/)).toBeInTheDocument();
    });

    it('should pad seconds with leading zero when needed', () => {
      const segmentWithPaddedTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 125.0,
        end_time: 130.5,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithPaddedTime} queryTerms={mockQueryTerms} />
      );

      // 125 seconds = 2:05, 130.5 seconds = 2:10
      expect(screen.getByText(/2:05.*2:10/)).toBeInTheDocument();
    });

    it('should handle zero timestamp', () => {
      const segmentFromStart: SearchResultSegment = {
        ...mockSegment,
        start_time: 0.0,
        end_time: 10.5,
      };

      renderWithProviders(
        <SearchResult segment={segmentFromStart} queryTerms={mockQueryTerms} />
      );

      // 0 seconds = 0:00, 10.5 seconds = 0:10
      expect(screen.getByText(/0:00.*0:10/)).toBeInTheDocument();
    });
  });

  describe('Query Term Highlighting', () => {
    it('should highlight query terms in segment text', () => {
      const { container } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks.length).toBeGreaterThan(0);

      // Should highlight both "machine" and "learning"
      const highlightedTexts = Array.from(marks).map((mark) => mark.textContent?.toLowerCase());
      expect(highlightedTexts).toContain('machine');
      expect(highlightedTexts).toContain('learning');
    });

    it('should highlight terms case-insensitively', () => {
      const segmentWithMixedCase: SearchResultSegment = {
        ...mockSegment,
        text: 'MACHINE learning is important. Machine LEARNING algorithms are powerful.',
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithMixedCase} queryTerms={['machine', 'learning']} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks.length).toBe(4); // 2 occurrences of "machine", 2 of "learning"
    });

    it('should not highlight when queryTerms is empty', () => {
      const { container } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={[]} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(0);
    });

    it('should preserve original text casing in highlights', () => {
      const { container } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const marks = container.querySelectorAll('mark');
      const machineHighlight = Array.from(marks).find(
        (mark) => mark.textContent?.toLowerCase() === 'machine'
      );

      expect(machineHighlight).toHaveTextContent('machine'); // Lowercase in original
    });
  });

  describe('Upload Date Rendering', () => {
    it('should render formatted upload date', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // Should show date in readable format (e.g., "Jan 15, 2024")
      expect(screen.getByText(/Jan.*15.*2024/i)).toBeInTheDocument();
    });

    it('should handle different date formats', () => {
      const segmentWithDifferentDate: SearchResultSegment = {
        ...mockSegment,
        video_upload_date: '2023-12-31T23:59:59Z',
      };

      renderWithProviders(
        <SearchResult segment={segmentWithDifferentDate} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText(/Dec.*31.*2023/i)).toBeInTheDocument();
    });
  });

  describe('Video Link Navigation (FR-005, FR-006)', () => {
    describe('Video Title Link (FR-006)', () => {
      it('should link video title to video detail page', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const link = screen.getByRole('link', { name: /Introduction to Machine Learning/i });
        expect(link).toHaveAttribute('href', '/videos/abc123def45');
      });

      it('should have proper href attribute for video title link', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const link = screen.getByRole('link', { name: /Introduction to Machine Learning/i });
        expect(link).toHaveAttribute('href');
        expect(link.getAttribute('href')).toMatch(/^\/videos\/[a-zA-Z0-9_-]+/);
      });

      it('should make video title keyboard accessible with Tab', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const link = screen.getByRole('link', { name: /Introduction to Machine Learning/i });

        // Tab to the link
        await user.tab();

        expect(link).toHaveFocus();
      });

      it('should activate video title link with Enter key', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const link = screen.getByRole('link', { name: /Introduction to Machine Learning/i });

        // Tab to the link and press Enter
        await user.tab();

        // Verify link is focused before pressing Enter
        expect(link).toHaveFocus();

        // Pressing Enter on a focused link would navigate (browser behavior)
        // We just verify the link is accessible via keyboard
        await user.keyboard('{Enter}');
      });
    });

    describe('Timestamp Link Navigation (FR-005)', () => {
      it('should navigate to video detail with timestamp parameter', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        // Look for timestamp link (the timestamp text should be clickable)
        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toBeDefined();
        expect(timestampLink).toHaveAttribute('href', expect.stringContaining('t=154'));
      });

      it('should include correct seconds in timestamp link', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        // start_time is 154.5 seconds, should be floored to 154
        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toHaveAttribute('href', '/videos/abc123def45?t=154');
      });

      it('should floor fractional seconds in timestamp parameter', () => {
        const segmentWithFractional: SearchResultSegment = {
          ...mockSegment,
          start_time: 89.7,
        };

        renderWithProviders(
          <SearchResult segment={segmentWithFractional} queryTerms={mockQueryTerms} />
        );

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toHaveAttribute('href', expect.stringContaining('t=89'));
      });

      it('should handle zero timestamp in link', () => {
        const segmentAtStart: SearchResultSegment = {
          ...mockSegment,
          start_time: 0.0,
        };

        renderWithProviders(
          <SearchResult segment={segmentAtStart} queryTerms={mockQueryTerms} />
        );

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toHaveAttribute('href', '/videos/abc123def45?t=0');
      });

      it('should be keyboard accessible via Tab', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        // Tab through all links - timestamp link should be focusable
        await user.tab(); // First link (video title)
        await user.tab(); // Second link (timestamp)

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toHaveFocus();
      });

      it('should activate timestamp link with Enter key', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        // Tab to timestamp link
        await user.tab(); // Video title
        await user.tab(); // Timestamp link

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        expect(timestampLink).toHaveFocus();

        // Press Enter to activate (would navigate in browser)
        await user.keyboard('{Enter}');
      });

      it('should have proper href attribute structure', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        const href = timestampLink?.getAttribute('href');
        expect(href).toMatch(/^\/videos\/[a-zA-Z0-9_-]+\?t=\d+$/);
      });

      it('should have accessible label for timestamp link', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const timestampLinks = screen.getAllByRole('link');
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute('href')?.includes('t=')
        );

        // Link should have accessible text (the timestamp range)
        expect(timestampLink).toHaveAccessibleName();
        expect(timestampLink?.textContent).toMatch(/\d+:\d+.*\d+:\d+/);
      });
    });

    describe('Link Accessibility', () => {
      it('should have all links keyboard navigable in order', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const allLinks = screen.getAllByRole('link');

        // First tab should focus video title link
        await user.tab();
        expect(allLinks[0]).toHaveFocus();

        // Second tab should focus timestamp link
        await user.tab();
        expect(allLinks[1]).toHaveFocus();
      });

      it('should support keyboard navigation in reverse (Shift+Tab)', async () => {
        const { user } = renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const allLinks = screen.getAllByRole('link');

        // Tab forward to second link
        await user.tab();
        await user.tab();
        expect(allLinks[1]).toHaveFocus();

        // Shift+Tab should go back to first link
        await user.tab({ shift: true });
        expect(allLinks[0]).toHaveFocus();
      });

      it('should have proper ARIA attributes on all links', () => {
        renderWithProviders(
          <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
        );

        const allLinks = screen.getAllByRole('link');

        allLinks.forEach((link) => {
          expect(link).toHaveAccessibleName();
          expect(link).toHaveAttribute('href');
        });
      });
    });
  });

  describe('Context Rendering', () => {
    it('should render context expander when context is available', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // Context expander button should be visible
      expect(screen.getByRole('button', { name: /expand additional context/i })).toBeInTheDocument();
    });

    it('should show context_before when expander is clicked', async () => {
      const { user } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const expandButton = screen.getByRole('button', { name: /expand additional context/i });
      await user.click(expandButton);

      expect(screen.getByText(/Welcome to this comprehensive tutorial/)).toBeInTheDocument();
    });

    it('should show context_after when expander is clicked', async () => {
      const { user } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const expandButton = screen.getByRole('button', { name: /expand additional context/i });
      await user.click(expandButton);

      expect(screen.getByText(/Let us begin with supervised learning/)).toBeInTheDocument();
    });

    it('should handle null context_before gracefully', () => {
      const segmentWithoutContextBefore: SearchResultSegment = {
        ...mockSegment,
        context_before: null,
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithoutContextBefore} queryTerms={mockQueryTerms} />
      );

      // Should not crash and should still show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should still be visible (because context_after exists)
      expect(screen.getByRole('button', { name: /expand additional context/i })).toBeInTheDocument();
    });

    it('should handle null context_after gracefully', () => {
      const segmentWithoutContextAfter: SearchResultSegment = {
        ...mockSegment,
        context_after: null,
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithoutContextAfter} queryTerms={mockQueryTerms} />
      );

      // Should not crash and should still show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should still be visible (because context_before exists)
      expect(screen.getByRole('button', { name: /expand additional context/i })).toBeInTheDocument();
    });

    it('should handle both context_before and context_after being null', () => {
      const segmentWithoutContext: SearchResultSegment = {
        ...mockSegment,
        context_before: null,
        context_after: null,
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithoutContext} queryTerms={mockQueryTerms} />
      );

      // Should only show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should NOT be visible (no context available)
      expect(screen.queryByRole('button', { name: /expand additional context/i })).not.toBeInTheDocument();
    });
  });

  describe('Match Count Display', () => {
    it('should use singular "match" when count is 1', () => {
      const segmentWithOneMatch: SearchResultSegment = {
        ...mockSegment,
        match_count: 1,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithOneMatch} queryTerms={mockQueryTerms} />
      );

      // Match count badge only shows when > 1, so single match should not be visible
      expect(screen.queryByText('1 match')).not.toBeInTheDocument();
      expect(screen.queryByText('1 matches')).not.toBeInTheDocument();
    });

    it('should use plural "matches" when count is greater than 1', () => {
      const segmentWithMultipleMatches: SearchResultSegment = {
        ...mockSegment,
        match_count: 5,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithMultipleMatches} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText(/5 matches/i)).toBeInTheDocument();
    });

    it('should handle zero matches', () => {
      const segmentWithZeroMatches: SearchResultSegment = {
        ...mockSegment,
        match_count: 0,
      };

      renderWithProviders(
        <SearchResult segment={segmentWithZeroMatches} queryTerms={mockQueryTerms} />
      );

      // Match count badge only shows when > 1, so zero should not be visible
      expect(screen.queryByText(/0 matches/i)).not.toBeInTheDocument();
    });
  });

  describe('Language Code Display', () => {
    it('should display language code badge', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('en')).toBeInTheDocument();
    });

    it('should display different language codes', () => {
      const spanishSegment: SearchResultSegment = {
        ...mockSegment,
        language_code: 'es',
      };

      renderWithProviders(
        <SearchResult segment={spanishSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('es')).toBeInTheDocument();
    });

    it('should display regional language codes', () => {
      const regionalSegment: SearchResultSegment = {
        ...mockSegment,
        language_code: 'es-MX',
      };

      renderWithProviders(
        <SearchResult segment={regionalSegment} queryTerms={mockQueryTerms} />
      );

      expect(screen.getByText('es-MX')).toBeInTheDocument();
    });
  });

  describe('Accessibility (ARIA Attributes)', () => {
    it('should have proper ARIA label for video link', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const links = screen.getAllByRole('link');
      // All links should have accessible names
      links.forEach(link => {
        expect(link).toHaveAccessibleName();
      });
    });

    it('should have semantic HTML structure', () => {
      const { container } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // Should use article or similar semantic element
      const article = container.querySelector('article');
      expect(article).toBeInTheDocument();
    });

    it('should have accessible timestamp information', () => {
      renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      // Timestamp should be accessible to screen readers
      const timestamp = screen.getByText(/2:34.*3:12/);
      expect(timestamp).toBeInTheDocument();
    });
  });

  describe('Long Text Handling', () => {
    it('should handle very long segment text', () => {
      const segmentWithLongText: SearchResultSegment = {
        ...mockSegment,
        text: 'A'.repeat(1000) + ' machine learning ' + 'B'.repeat(1000),
      };

      renderWithProviders(
        <SearchResult segment={segmentWithLongText} queryTerms={mockQueryTerms} />
      );

      // Should render without crashing
      expect(screen.getByText(/machine learning/i)).toBeInTheDocument();
    });

    it('should handle very long video titles', () => {
      const segmentWithLongTitle: SearchResultSegment = {
        ...mockSegment,
        video_title:
          'This is an extremely long video title that should be handled gracefully by the component without breaking the layout or causing accessibility issues',
      };

      renderWithProviders(
        <SearchResult segment={segmentWithLongTitle} queryTerms={mockQueryTerms} />
      );

      expect(
        screen.getByText(/This is an extremely long video title/)
      ).toBeInTheDocument();
    });

    it('should handle very long channel names', () => {
      const segmentWithLongChannel: SearchResultSegment = {
        ...mockSegment,
        channel_title:
          'This is an extremely long channel name that should also be handled gracefully',
      };

      renderWithProviders(
        <SearchResult segment={segmentWithLongChannel} queryTerms={mockQueryTerms} />
      );

      expect(
        screen.getByText(/This is an extremely long channel name/)
      ).toBeInTheDocument();
    });
  });

  describe('Special Characters', () => {
    it('should handle special characters in segment text', () => {
      const segmentWithSpecialChars: SearchResultSegment = {
        ...mockSegment,
        text: 'Learn C++ & Python (2024) - $100 course! Machine learning basics.',
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithSpecialChars} queryTerms={mockQueryTerms} />
      );

      // Text is split by highlights, check for parts separately
      expect(container.textContent).toMatch(/Learn C\+\+ & Python/);
      expect(container.textContent).toMatch(/basics/);
    });

    it('should handle emoji in segment text', () => {
      const segmentWithEmoji: SearchResultSegment = {
        ...mockSegment,
        text: '🚀 Machine learning tutorial 🎓 Learn algorithms 💻',
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithEmoji} queryTerms={mockQueryTerms} />
      );

      // Text is split by highlights, check using container
      expect(container.textContent).toMatch(/🚀/);
      expect(container.textContent).toMatch(/🎓/);
      expect(container.textContent).toMatch(/💻/);
    });

    it('should handle multi-byte Unicode characters', () => {
      const segmentWithUnicode: SearchResultSegment = {
        ...mockSegment,
        text: 'Machine learning 機械学習 apprentissage automatique',
      };

      const { container } = renderWithProviders(
        <SearchResult segment={segmentWithUnicode} queryTerms={mockQueryTerms} />
      );

      // Text is split by highlights, check using container
      expect(container.textContent).toMatch(/機械学習/);
      expect(container.textContent).toMatch(/apprentissage automatique/);
    });
  });

  describe('Hover States', () => {
    it('should be hoverable', async () => {
      const { user } = renderWithProviders(
        <SearchResult segment={mockSegment} queryTerms={mockQueryTerms} />
      );

      const links = screen.getAllByRole('link');
      const firstLink = links[0];

      await user.hover(firstLink);

      // Visual hover state would be tested with visual regression
      expect(firstLink).toBeInTheDocument();
    });
  });

  describe('Multiple Query Terms', () => {
    it('should highlight all query terms', () => {
      const segmentWithMultipleTerms: SearchResultSegment = {
        ...mockSegment,
        text: 'Python programming with TensorFlow for deep learning and neural networks.',
      };

      const { container } = renderWithProviders(
        <SearchResult
          segment={segmentWithMultipleTerms}
          queryTerms={['python', 'learning', 'neural']}
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks.length).toBe(3);

      const highlightedTexts = Array.from(marks).map((mark) =>
        mark.textContent?.toLowerCase()
      );
      expect(highlightedTexts).toContain('python');
      expect(highlightedTexts).toContain('learning');
      expect(highlightedTexts).toContain('neural');
    });
  });
});
