/**
 * Tests for TranscriptPanel component.
 *
 * Covers:
 * - Collapsed state (default)
 * - Expanded state
 * - No transcripts message
 * - Expand/collapse button semantics (NFR-A06-A10)
 * - Loading and error states
 * - Language badges display
 * - Focus management
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test-utils';
import { TranscriptPanel } from '../../../src/components/transcript/TranscriptPanel';
import type { TranscriptLanguage } from '../../../src/types/transcript';

// Mock hooks
vi.mock('../../../src/hooks/useTranscriptLanguages');
vi.mock('../../../src/hooks/usePrefersReducedMotion');

// Mock child components
vi.mock('../../../src/components/transcript/LanguageSelector', () => ({
  LanguageSelector: ({ selectedLanguage, onLanguageChange }: any) => (
    <div data-testid="language-selector">
      <button onClick={() => onLanguageChange('en')}>EN</button>
      <button onClick={() => onLanguageChange('es')}>ES</button>
      <div>Selected: {selectedLanguage}</div>
    </div>
  ),
}));

vi.mock('../../../src/components/transcript/ViewModeToggle', () => ({
  ViewModeToggle: ({ mode, onModeChange }: any) => (
    <div data-testid="view-mode-toggle">
      <button onClick={() => onModeChange('segments')}>Segments</button>
      <button onClick={() => onModeChange('fulltext')}>Full Text</button>
      <div>Mode: {mode}</div>
    </div>
  ),
}));

vi.mock('../../../src/components/transcript/TranscriptSegments', () => ({
  TranscriptSegments: ({ videoId, languageCode }: any) => (
    <div data-testid="transcript-segments">
      Segments: {videoId} - {languageCode}
    </div>
  ),
}));

vi.mock('../../../src/components/transcript/TranscriptFullText', () => ({
  TranscriptFullText: ({ videoId, languageCode }: any) => (
    <div data-testid="transcript-fulltext">
      FullText: {videoId} - {languageCode}
    </div>
  ),
}));

import { useTranscriptLanguages } from '../../../src/hooks/useTranscriptLanguages';
import { usePrefersReducedMotion } from '../../../src/hooks/usePrefersReducedMotion';

const mockUseTranscriptLanguages = vi.mocked(useTranscriptLanguages);
const mockUsePrefersReducedMotion = vi.mocked(usePrefersReducedMotion);

describe('TranscriptPanel', () => {
  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: 'en',
      language_name: 'English',
      transcript_type: 'manual',
      is_translatable: true,
      downloaded_at: '2024-01-15T10:00:00Z',
    },
    {
      language_code: 'es',
      language_name: 'Spanish',
      transcript_type: 'auto_generated',
      is_translatable: true,
      downloaded_at: '2024-01-15T10:05:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePrefersReducedMotion.mockReturnValue(false);
  });

  describe('Loading State', () => {
    it('should render loading skeleton', () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
      } as any);

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole('status', { name: 'Loading transcript information' })).toBeInTheDocument();
      expect(screen.getByText('Loading transcript information...')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('should render error message', () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Failed to fetch' },
      } as any);

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Could not load transcript information.')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch')).toBeInTheDocument();
    });
  });

  describe('No Transcripts Available', () => {
    it('should render no transcript message when languages array is empty', () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: [],
        isLoading: false,
        isError: false,
        error: null,
      } as any);

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText('No transcript available for this video')).toBeInTheDocument();
    });
  });

  describe('Collapsed State (Default)', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should render in collapsed state by default', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
    });

    it('should show "Transcript Available" text when collapsed', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText('Transcript Available')).toBeInTheDocument();
    });

    it('should show language badges when collapsed', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      // Query within the language badge list to avoid confusion with mocked LanguageSelector buttons
      const badgeList = screen.getByRole('list', { name: 'Available languages' });
      const badges = badgeList.querySelectorAll('[role="listitem"]');

      // Should show language badges for en and es
      expect(badges).toHaveLength(2);
      expect(badges[0]).toHaveTextContent('EN');
      expect(badges[1]).toHaveTextContent('ES');
    });

    it('should show high quality checkmark for manual transcripts', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const badges = screen.getAllByRole('listitem');
      // First badge (EN) should have checkmark for manual transcript
      expect(badges[0]).toHaveTextContent('EN✓');
      // Second badge (ES) should not have checkmark (auto-generated)
      expect(badges[1]).toHaveTextContent('ES');
      expect(badges[1]).not.toHaveTextContent('✓');
    });

    it('should have expandable content hidden when collapsed', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      const contentId = toggleButton.getAttribute('aria-controls');
      const expandableContent = document.getElementById(contentId!);

      expect(expandableContent).toHaveAttribute('aria-hidden', 'true');
    });
  });

  describe('Expanded State', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should expand when toggle button is clicked', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
        const contentId = toggleButton.getAttribute('aria-controls');
        const expandableContent = document.getElementById(contentId!);
        expect(expandableContent).toHaveAttribute('aria-hidden', 'false');
      });
    });

    it('should show "Hide transcript" text when expanded', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByText('Hide transcript')).toBeInTheDocument();
      });
    });

    it('should show language selector when expanded', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('language-selector')).toBeInTheDocument();
      });
    });

    it('should show view mode toggle when expanded', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('view-mode-toggle')).toBeInTheDocument();
      });
    });

    it('should show transcript segments by default', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('transcript-segments')).toBeInTheDocument();
      });
    });

    it('should NOT show language badges when expanded', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });

      // Verify badges are visible when collapsed
      expect(screen.getByRole('list', { name: 'Available languages' })).toBeInTheDocument();

      await user.click(toggleButton);

      await waitFor(() => {
        // After expansion, the badges should be hidden (not rendered in collapsed state)
        // The implementation renders badges conditionally with !isExpanded
        expect(screen.queryByRole('list', { name: 'Available languages' })).not.toBeInTheDocument();
      });
    });
  });

  describe('Expand/Collapse Button Semantics (NFR-A06-A10)', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should have proper aria-expanded attribute', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
    });

    it('should have proper aria-controls attribute', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute('aria-controls', 'transcript-content');
    });

    it('should be keyboard accessible', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      toggleButton.focus();

      expect(toggleButton).toHaveFocus();

      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
      });
    });

    it('should announce state changes to screen readers', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        const announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('Transcript panel expanded');
      });
    });
  });

  describe('View Mode Switching', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should show segments view by default', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('transcript-segments')).toBeInTheDocument();
        expect(screen.queryByTestId('transcript-fulltext')).not.toBeInTheDocument();
      });
    });

    it('should switch to full text view when view mode toggle is clicked', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      // Expand panel first
      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('view-mode-toggle')).toBeInTheDocument();
      });

      // Click Full Text button in view mode toggle
      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      await user.click(fullTextButton);

      await waitFor(() => {
        expect(screen.getByTestId('transcript-fulltext')).toBeInTheDocument();
        expect(screen.queryByTestId('transcript-segments')).not.toBeInTheDocument();
      });
    });
  });

  describe('Language Selection', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should initialize with first language selected', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByText('Selected: en')).toBeInTheDocument();
      });
    });

    it('should pass selected language to transcript components', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('transcript-segments')).toHaveTextContent('Segments: test-video - en');
      });
    });

    it('should update transcript when language is changed', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId('language-selector')).toBeInTheDocument();
      });

      const spanishButton = screen.getByRole('button', { name: 'ES' });
      await user.click(spanishButton);

      await waitFor(() => {
        expect(screen.getByTestId('transcript-segments')).toHaveTextContent('Segments: test-video - es');
      });
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      } as any);
    });

    it('should have proper region role and label', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole('region', { name: 'Transcript information' })).toBeInTheDocument();
    });

    it('should provide screen reader summary when collapsed', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText(/2 transcripts available in English, Spanish/i)).toBeInTheDocument();
    });

    it('should have tabpanel role for expanded content', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole('button', { name: /show transcript/i });
      const contentId = toggleButton.getAttribute('aria-controls');

      await user.click(toggleButton);

      await waitFor(() => {
        const expandableContent = document.getElementById(contentId!);
        expect(expandableContent).toHaveAttribute('role', 'tabpanel');
      });
    });
  });
});
