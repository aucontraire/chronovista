/**
 * Tests for TranscriptFullText component.
 *
 * Covers:
 * - Rendering continuous prose text
 * - Loading state with skeleton placeholder
 * - Error state with retry functionality
 * - Empty transcript handling
 * - Proper text formatting and accessibility
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test-utils';
import { TranscriptFullText } from '../../../src/components/transcript/TranscriptFullText';
import type { Transcript } from '../../../src/types/transcript';

// Mock hooks
vi.mock('../../../src/hooks/useTranscript');

import { useTranscript } from '../../../src/hooks/useTranscript';

const mockUseTranscript = vi.mocked(useTranscript);

describe('TranscriptFullText', () => {
  const mockTranscript: Transcript = {
    video_id: 'test-video',
    language_code: 'en',
    transcript_type: 'manual',
    full_text: 'Welcome to this video tutorial. Today we will learn about React testing. Let us start with the basics.',
    segment_count: 3,
    downloaded_at: '2024-01-15T10:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading State', () => {
    it('should render skeleton placeholder during load', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('status', { name: 'Loading transcript' })).toBeInTheDocument();
      expect(screen.getByText('Loading transcript content...')).toBeInTheDocument();
    });

    it('should render animated pulse skeleton', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      const { container } = renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const skeleton = container.querySelector('.animate-pulse');
      expect(skeleton).toBeInTheDocument();
    });
  });

  describe('Transcript Rendering (FR-019)', () => {
    beforeEach(() => {
      mockUseTranscript.mockReturnValue({
        data: mockTranscript,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);
    });

    it('should render full transcript text as continuous prose', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText(mockTranscript.full_text)).toBeInTheDocument();
    });

    it('should have region role with proper label', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('region', { name: 'Full transcript text' })).toBeInTheDocument();
    });

    it('should preserve whitespace with pre-wrap', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const textElement = screen.getByText(mockTranscript.full_text);
      expect(textElement).toHaveClass('whitespace-pre-wrap');
    });

    it('should have proper text contrast for accessibility (NFR-A18)', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const textElement = screen.getByText(mockTranscript.full_text);
      expect(textElement).toHaveClass('text-gray-900');
    });

    it('should have proper line height for readability', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const textElement = screen.getByText(mockTranscript.full_text);
      expect(textElement).toHaveClass('leading-7');
    });
  });

  describe('Error State', () => {
    it('should render error message when fetch fails', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Failed to load transcript')).toBeInTheDocument();
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    it('should render retry button in error state', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });

    it('should call refetch when retry button is clicked', async () => {
      const mockRefetch = vi.fn();
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      const { user } = renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const retryButton = screen.getByRole('button', { name: /try again/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1);
      });
    });

    it('should display default error message when error has no message', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('An unexpected error occurred')).toBeInTheDocument();
    });
  });

  describe('Empty States', () => {
    it('should show message when transcript data is null', () => {
      mockUseTranscript.mockReturnValue({
        data: null,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('No transcript available for this language.')).toBeInTheDocument();
    });

    it('should show message when full_text is empty string', () => {
      mockUseTranscript.mockReturnValue({
        data: { ...mockTranscript, full_text: '' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('Transcript is empty.')).toBeInTheDocument();
    });

    it('should show message when full_text is only whitespace', () => {
      mockUseTranscript.mockReturnValue({
        data: { ...mockTranscript, full_text: '   \n  \t  ' },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('Transcript is empty.')).toBeInTheDocument();
    });
  });

  describe('Text Formatting', () => {
    it('should preserve line breaks in transcript text', () => {
      const multilineTranscript: Transcript = {
        ...mockTranscript,
        full_text: 'Line one.\n\nLine two.\nLine three.',
      };

      mockUseTranscript.mockReturnValue({
        data: multilineTranscript,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      const { container } = renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      // Query for the paragraph element with whitespace-pre-wrap class
      const textElement = container.querySelector('.whitespace-pre-wrap');
      expect(textElement).toBeInTheDocument();
      // Check that the text content (with newlines collapsed) matches
      expect(textElement).toHaveTextContent(/Line one.*Line two.*Line three/);
      // The key assertion: whitespace-pre-wrap class preserves line breaks
      expect(textElement).toHaveClass('whitespace-pre-wrap');
    });

    it('should use prose styling for readability', () => {
      mockUseTranscript.mockReturnValue({
        data: mockTranscript,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      const { container } = renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const proseContainer = container.querySelector('.prose');
      expect(proseContainer).toBeInTheDocument();
      expect(proseContainer).toHaveClass('prose-sm');
      expect(proseContainer).toHaveClass('max-w-none');
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      mockUseTranscript.mockReturnValue({
        data: mockTranscript,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);
    });

    it('should have proper semantic HTML structure', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const region = screen.getByRole('region', { name: 'Full transcript text' });
      expect(region).toBeInTheDocument();
    });

    it('should have sufficient color contrast (NFR-A18)', () => {
      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const textElement = screen.getByText(mockTranscript.full_text);
      // text-gray-900 ensures WCAG AA compliance with high contrast ratio
      expect(textElement).toHaveClass('text-gray-900');
    });

    it('should have role="status" for loading state', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('should have role="alert" for error state', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  describe('Retry Functionality', () => {
    it('should have keyboard accessible retry button', async () => {
      const mockRefetch = vi.fn();
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: mockRefetch,
      } as any);

      const { user } = renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const retryButton = screen.getByRole('button', { name: /try again/i });
      retryButton.focus();
      expect(retryButton).toHaveFocus();

      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1);
      });
    });

    it('should have visible focus indicator on retry button', () => {
      mockUseTranscript.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        refetch: vi.fn(),
      } as any);

      renderWithProviders(
        <TranscriptFullText
          videoId="test-video"
          languageCode="en"
        />
      );

      const retryButton = screen.getByRole('button', { name: /try again/i });
      expect(retryButton).toHaveClass('focus-visible:ring-2');
      expect(retryButton).toHaveClass('focus-visible:ring-red-500');
    });
  });
});
