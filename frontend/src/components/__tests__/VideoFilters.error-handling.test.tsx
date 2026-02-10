/**
 * Tests for VideoFilters error handling features.
 *
 * Implements tests for:
 * - T084: Offline indicator
 * - T088: Partial results warning banner
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VideoFilters } from '../VideoFilters';
import * as useOnlineStatusModule from '../../hooks/useOnlineStatus';

// Mock the hooks
vi.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({
    categories: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('../../hooks/useTopics', () => ({
  useTopics: () => ({
    topics: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('../../hooks/useOnlineStatus');

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
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe('VideoFilters - Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Offline Indicator (T084)', () => {
    it('should show offline banner when offline', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(false);

      renderWithProviders(<VideoFilters videoCount={0} />);

      expect(screen.getByText(/You are currently offline/i)).toBeInTheDocument();
    });

    it('should not show offline banner when online', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(true);

      renderWithProviders(<VideoFilters videoCount={0} />);

      expect(screen.queryByText(/You are currently offline/i)).not.toBeInTheDocument();
    });

    it('should use assertive aria-live for offline banner', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(false);

      renderWithProviders(<VideoFilters videoCount={0} />);

      const banner = screen.getByText(/You are currently offline/i).closest('div');
      expect(banner).toHaveAttribute('role', 'alert');
      expect(banner).toHaveAttribute('aria-live', 'assertive');
    });
  });

  describe('Partial Results Warning (T088)', () => {
    it('should show warning banner when warnings provided', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(true);

      const warnings = [
        { filter: 'tags', message: 'Tag filter failed to apply' },
        { filter: 'category', message: 'Category not found' },
      ];

      renderWithProviders(<VideoFilters videoCount={0} warnings={warnings} />);

      expect(screen.getByText(/Some filters could not be applied/i)).toBeInTheDocument();
      expect(screen.getByText(/Tag filter failed to apply/i)).toBeInTheDocument();
      expect(screen.getByText(/Category not found/i)).toBeInTheDocument();
    });

    it('should not show warning banner when no warnings', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(true);

      renderWithProviders(<VideoFilters videoCount={0} warnings={[]} />);

      expect(screen.queryByText(/Some filters could not be applied/i)).not.toBeInTheDocument();
    });

    it('should use polite aria-live for warning banner', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(true);

      const warnings = [
        { filter: 'tags', message: 'Tag filter failed' },
      ];

      renderWithProviders(<VideoFilters videoCount={0} warnings={warnings} />);

      const banner = screen.getByText(/Some filters could not be applied/i).closest('div');
      expect(banner).toHaveAttribute('role', 'alert');
      expect(banner).toHaveAttribute('aria-live', 'polite');
    });

    it('should handle multiple warnings', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(true);

      const warnings = [
        { filter: 'tag1', message: 'First tag error' },
        { filter: 'tag2', message: 'Second tag error' },
        { filter: 'topic', message: 'Topic error' },
      ];

      renderWithProviders(<VideoFilters videoCount={0} warnings={warnings} />);

      expect(screen.getByText(/First tag error/i)).toBeInTheDocument();
      expect(screen.getByText(/Second tag error/i)).toBeInTheDocument();
      expect(screen.getByText(/Topic error/i)).toBeInTheDocument();
    });
  });

  describe('Combined Banners', () => {
    it('should show both offline and warning banners when both conditions met', () => {
      vi.spyOn(useOnlineStatusModule, 'useOnlineStatus').mockReturnValue(false);

      const warnings = [
        { filter: 'tags', message: 'Tag filter failed' },
      ];

      renderWithProviders(<VideoFilters videoCount={0} warnings={warnings} />);

      expect(screen.getByText(/You are currently offline/i)).toBeInTheDocument();
      expect(screen.getByText(/Some filters could not be applied/i)).toBeInTheDocument();
    });
  });
});
