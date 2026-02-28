/**
 * Tests for TagAutocomplete error handling features.
 *
 * Implements tests for:
 * - T081: Loading states
 * - T082: Error handling display
 *
 * Updated for canonical tags refactor (Feature 030/032):
 * - Component now uses useCanonicalTags instead of useTags
 * - selectedTags is SelectedCanonicalTag[] instead of string[]
 * - Error state shows an alert (no retry button — canonical hook handles retry internally)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TagAutocomplete } from '../TagAutocomplete';
import * as useCanonicalTagsModule from '../../hooks/useCanonicalTags';

// Mock the useCanonicalTags hook
vi.mock('../../hooks/useCanonicalTags');

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  );
}

function mockCanonicalTags(overrides: Partial<ReturnType<typeof useCanonicalTagsModule.useCanonicalTags>> = {}) {
  vi.spyOn(useCanonicalTagsModule, 'useCanonicalTags').mockReturnValue({
    tags: [],
    suggestions: [],
    isLoading: false,
    isError: false,
    error: null,
    isRateLimited: false,
    rateLimitRetryAfter: 0,
    ...overrides,
  });
}

describe('TagAutocomplete - Error Handling', () => {
  const mockOnTagSelect = vi.fn();
  const mockOnTagRemove = vi.fn();

  describe('Loading States (T081)', () => {
    it('should show loading spinner when loading', async () => {
      mockCanonicalTags({ tags: [], isLoading: true });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const input = screen.getByRole('combobox', { name: /tags/i });
      await userEvent.type(input, 'test');

      await waitFor(() => {
        // Loading spinner should be present
        const spinner = document.querySelector('.animate-spin');
        expect(spinner).toBeInTheDocument();
      });
    });

    it('should not show loading spinner when not loading', () => {
      mockCanonicalTags({
        tags: [
          { canonical_form: 'tag1', normalized_form: 'tag1', alias_count: 1, video_count: 5 },
          { canonical_form: 'tag2', normalized_form: 'tag2', alias_count: 1, video_count: 3 },
        ],
        isLoading: false,
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const spinner = document.querySelector('.animate-spin');
      expect(spinner).not.toBeInTheDocument();
    });
  });

  describe('Error Handling (T082)', () => {
    it('should show error message when error occurs', async () => {
      mockCanonicalTags({
        tags: [],
        isError: true,
        error: new Error('Network error'),
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const input = screen.getByRole('combobox', { name: /tags/i });
      await userEvent.type(input, 'test');

      await waitFor(() => {
        expect(screen.getByText(/Error loading tags/i)).toBeInTheDocument();
      });
    });

    it('should show timeout-specific error message for timeout errors', async () => {
      mockCanonicalTags({
        tags: [],
        isError: true,
        error: { type: 'timeout', message: 'Request timed out' } as unknown as Error,
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const input = screen.getByRole('combobox', { name: /tags/i });
      await userEvent.type(input, 'test');

      await waitFor(() => {
        expect(screen.getByText(/Request timed out/i)).toBeInTheDocument();
      });
    });

    it('should show error alert (role=alert) when error occurs', async () => {
      mockCanonicalTags({
        tags: [],
        isError: true,
        error: new Error('Network error'),
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const input = screen.getByRole('combobox', { name: /tags/i });
      await userEvent.type(input, 'test');

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });

    it('should not show error when input is empty', async () => {
      mockCanonicalTags({
        tags: [],
        isError: true,
        error: new Error('Network error'),
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      // No input typed — error should be hidden
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('Success State', () => {
    it('should show suggestions when loaded successfully', async () => {
      mockCanonicalTags({
        tags: [
          { canonical_form: 'react', normalized_form: 'react', alias_count: 1, video_count: 100 },
          { canonical_form: 'typescript', normalized_form: 'typescript', alias_count: 2, video_count: 50 },
          { canonical_form: 'testing', normalized_form: 'testing', alias_count: 1, video_count: 25 },
        ],
      });

      renderWithProviders(
        <TagAutocomplete
          selectedTags={[]}
          onTagSelect={mockOnTagSelect}
          onTagRemove={mockOnTagRemove}
        />
      );

      const input = screen.getByRole('combobox', { name: /tags/i });
      await userEvent.type(input, 'test');

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
        expect(screen.getByRole('option', { name: /react/i })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: /typescript/i })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: /testing/i })).toBeInTheDocument();
      });
    });
  });
});
