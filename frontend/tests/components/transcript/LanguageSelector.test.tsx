/**
 * Tests for LanguageSelector component.
 *
 * Covers:
 * - Tab selection
 * - Keyboard navigation (Left/Right arrows, Home/End)
 * - ARIA attributes (tablist, tab, aria-selected, aria-controls)
 * - Quality indicators (checkmarks for manual transcripts)
 * - Language change callback
 * - Accessibility announcements
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { renderWithProviders } from '../../test-utils';
import { LanguageSelector } from '../../../src/components/transcript/LanguageSelector';
import type { TranscriptLanguage } from '../../../src/types/transcript';

describe('LanguageSelector', () => {
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
      transcript_type: 'auto_synced',
      is_translatable: true,
      downloaded_at: '2024-01-15T10:05:00Z',
    },
    {
      language_code: 'fr',
      language_name: 'French',
      transcript_type: 'auto_generated',
      is_translatable: false,
      downloaded_at: '2024-01-15T10:10:00Z',
    },
  ];

  const mockOnLanguageChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render tablist with proper ARIA attributes', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tablist = screen.getByRole('tablist', { name: 'Transcript languages' });
      expect(tablist).toBeInTheDocument();
    });

    it('should render all language tabs', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole('tab');
      expect(tabs).toHaveLength(3);
    });

    it('should render language labels as uppercase 2-letter codes', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(screen.getByRole('tab', { name: /english/i })).toHaveTextContent('EN');
      expect(screen.getByRole('tab', { name: /spanish/i })).toHaveTextContent('ES');
      expect(screen.getByRole('tab', { name: /french/i })).toHaveTextContent('FR');
    });

    it('should render nothing when languages array is empty', () => {
      const { container } = renderWithProviders(
        <LanguageSelector
          languages={[]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });

  describe('Tab Selection', () => {
    it('should mark selected tab with aria-selected="true"', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      expect(spanishTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should mark non-selected tabs with aria-selected="false"', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      const frenchTab = screen.getByRole('tab', { name: /french/i });
      expect(englishTab).toHaveAttribute('aria-selected', 'false');
      expect(frenchTab).toHaveAttribute('aria-selected', 'false');
    });

    it('should call onLanguageChange when tab is clicked', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      await user.click(spanishTab);

      await waitFor(() => {
        expect(mockOnLanguageChange).toHaveBeenCalledWith('es');
      });
    });

    it('should NOT call onLanguageChange when already selected tab is clicked', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      await user.click(englishTab);

      await waitFor(() => {
        expect(mockOnLanguageChange).not.toHaveBeenCalled();
      });
    });
  });

  describe('Quality Indicators', () => {
    it('should show checkmark for manual transcripts', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      expect(englishTab).toHaveTextContent('✓');
    });

    it('should show checkmark for auto_synced transcripts', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      expect(spanishTab).toHaveTextContent('✓');
    });

    it('should NOT show checkmark for auto_generated transcripts', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole('tab', { name: /french/i });
      expect(frenchTab).not.toHaveTextContent('✓');
    });

    it('should include quality indicator in screen reader text', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english.*high quality/i });
      expect(englishTab).toBeInTheDocument();
    });
  });

  describe('Keyboard Navigation (NFR-A03)', () => {
    it('should move focus to next tab with ArrowRight', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      englishTab.focus();

      await user.keyboard('{ArrowRight}');

      await waitFor(() => {
        const spanishTab = screen.getByRole('tab', { name: /spanish/i });
        expect(spanishTab).toHaveFocus();
      });
    });

    it('should move focus to previous tab with ArrowLeft', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      spanishTab.focus();

      await user.keyboard('{ArrowLeft}');

      await waitFor(() => {
        const englishTab = screen.getByRole('tab', { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it('should wrap to first tab when ArrowRight on last tab', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole('tab', { name: /french/i });
      frenchTab.focus();

      await user.keyboard('{ArrowRight}');

      await waitFor(() => {
        const englishTab = screen.getByRole('tab', { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it('should wrap to last tab when ArrowLeft on first tab', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      englishTab.focus();

      await user.keyboard('{ArrowLeft}');

      await waitFor(() => {
        const frenchTab = screen.getByRole('tab', { name: /french/i });
        expect(frenchTab).toHaveFocus();
      });
    });

    it('should move to first tab with Home key', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole('tab', { name: /french/i });
      frenchTab.focus();

      await user.keyboard('{Home}');

      await waitFor(() => {
        const englishTab = screen.getByRole('tab', { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it('should move to last tab with End key', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      englishTab.focus();

      await user.keyboard('{End}');

      await waitFor(() => {
        const frenchTab = screen.getByRole('tab', { name: /french/i });
        expect(frenchTab).toHaveFocus();
      });
    });

    it('should select tab when navigating with arrow keys', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      englishTab.focus();

      await user.keyboard('{ArrowRight}');

      await waitFor(() => {
        expect(mockOnLanguageChange).toHaveBeenCalledWith('es');
      });
    });
  });

  describe('ARIA Attributes', () => {
    it('should have proper aria-controls attribute', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          contentId="test-content"
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      expect(englishTab).toHaveAttribute('aria-controls', 'test-content');
    });

    it('should use default content ID when not provided', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      expect(englishTab).toHaveAttribute('aria-controls', 'transcript-content');
    });

    it('should have proper tabindex for roving tabindex pattern', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      const frenchTab = screen.getByRole('tab', { name: /french/i });

      // Selected tab should have tabindex="0"
      expect(spanishTab).toHaveAttribute('tabindex', '0');
      // Other tabs should have tabindex="-1"
      expect(englishTab).toHaveAttribute('tabindex', '-1');
      expect(frenchTab).toHaveAttribute('tabindex', '-1');
    });

    it('should have id attribute for each tab', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      expect(englishTab).toHaveAttribute('id', 'tab-en');
    });
  });

  describe('Accessibility Announcements (NFR-A04)', () => {
    it('should announce language change to screen readers', async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole('tab', { name: /spanish/i });
      await user.click(spanishTab);

      await waitFor(() => {
        const announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('Transcript language changed to Spanish');
      });
    });

    it('should clear announcement after it has been read', async () => {
      vi.useFakeTimers();

      try {
        renderWithProviders(
          <LanguageSelector
            languages={mockLanguages}
            selectedLanguage="en"
            onLanguageChange={mockOnLanguageChange}
          />
        );

        const spanishTab = screen.getByRole('tab', { name: /spanish/i });

        // Click in act()
        act(() => {
          spanishTab.click();
        });

        // Fast-forward past debounce and announcement clear
        await act(async () => {
          await vi.advanceTimersByTimeAsync(2000);
        });

        const announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('');
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe('Visual Styling', () => {
    it('should have different styling for selected tab', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole('tab', { name: /english/i });
      const spanishTab = screen.getByRole('tab', { name: /spanish/i });

      // Selected tab should have blue background
      expect(spanishTab).toHaveClass('bg-blue-600');
      // Non-selected tab should have gray background
      expect(englishTab).toHaveClass('bg-gray-100');
    });
  });
});
