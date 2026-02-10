/**
 * Tests for TagAutocomplete error handling features.
 *
 * Implements tests for:
 * - T081: Loading states
 * - T082: Error handling with retry button
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TagAutocomplete } from '../TagAutocomplete';
import * as useTagsModule from '../../hooks/useTags';

// Mock the useTags hook
vi.mock('../../hooks/useTags');

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

describe('TagAutocomplete - Error Handling', () => {
  const mockOnTagSelect = vi.fn();
  const mockOnTagRemove = vi.fn();

  describe('Loading States (T081)', () => {
    it('should show loading spinner when loading', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: [],
        suggestions: [],
        isLoading: true,
        isError: false,
        error: null,
        refetch: mockRefetch,
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
        // Loading spinner should be present
        const spinner = document.querySelector('.animate-spin');
        expect(spinner).toBeInTheDocument();
      });
    });

    it('should not show loading spinner when not loading', () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: ['tag1', 'tag2'],
        suggestions: [],
        isLoading: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
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

  describe('Error Handling with Retry (T082)', () => {
    it('should show error message when error occurs', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: [],
        suggestions: [],
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        refetch: mockRefetch,
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
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: [],
        suggestions: [],
        isLoading: false,
        isError: true,
        error: { type: 'timeout', message: 'Request timed out' },
        refetch: mockRefetch,
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

    it('should show retry button when error occurs', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: [],
        suggestions: [],
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        refetch: mockRefetch,
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
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('should call refetch when retry button clicked', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: [],
        suggestions: [],
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        refetch: mockRefetch,
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
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await userEvent.click(retryButton);

      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('Success State', () => {
    it('should show suggestions when loaded successfully', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useTagsModule, 'useTags').mockReturnValue({
        tags: ['react', 'typescript', 'testing'],
        suggestions: [],
        isLoading: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
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
