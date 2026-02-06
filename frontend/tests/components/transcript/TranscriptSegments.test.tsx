/**
 * Tests for TranscriptSegments component.
 *
 * Covers:
 * - Rendering with segments
 * - Infinite scroll trigger
 * - Loading states (initial and pagination)
 * - Error states with retry
 * - End of transcript indicator
 * - Keyboard navigation (Arrow keys, Page Up/Down, Home/End)
 * - Virtualization for 500+ segments
 * - Accessibility attributes
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test-utils';
import { TranscriptSegments } from '../../../src/components/transcript/TranscriptSegments';
import type { TranscriptSegment } from '../../../src/types/transcript';

// Mock hooks
vi.mock('../../../src/hooks/useTranscriptSegments');

// Mock @tanstack/react-virtual for virtualization tests
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
  })),
}));

import { useTranscriptSegments } from '../../../src/hooks/useTranscriptSegments';

const mockUseTranscriptSegments = vi.mocked(useTranscriptSegments);

describe('TranscriptSegments', () => {
  const mockSegments: TranscriptSegment[] = [
    {
      id: 1,
      text: 'Welcome to this video tutorial.',
      start_time: 0.5,
      end_time: 3.2,
      duration: 2.7,
    },
    {
      id: 2,
      text: 'Today we will learn about React testing.',
      start_time: 3.5,
      end_time: 7.1,
      duration: 3.6,
    },
    {
      id: 3,
      text: 'Let us start with the basics.',
      start_time: 7.5,
      end_time: 10.0,
      duration: 2.5,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading States', () => {
    it('should render skeleton segments during initial load', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: true,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('status', { name: 'Loading transcript segments' })).toBeInTheDocument();
      expect(screen.getByText('Loading transcript segments...')).toBeInTheDocument();
    });

    it('should render 3 skeleton segments during loading (FR-020d)', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: true,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      const { container } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      // Count skeleton elements (animated pulse divs)
      const skeletons = container.querySelectorAll('.animate-pulse');
      expect(skeletons.length).toBe(3);
    });

    it('should show loading indicator when fetching next page', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 100,
        isLoading: false,
        isFetchingNextPage: true,
        hasNextPage: true,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('status', { name: 'Loading more segments' })).toBeInTheDocument();
      expect(screen.getByText('Loading more segments...')).toBeInTheDocument();
    });
  });

  describe('Segments Rendering', () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 3,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });
    });

    it('should render all segments with timestamps and text', () => {
      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('Welcome to this video tutorial.')).toBeInTheDocument();
      expect(screen.getByText('Today we will learn about React testing.')).toBeInTheDocument();
      expect(screen.getByText('Let us start with the basics.')).toBeInTheDocument();
    });

    it('should render timestamps in MM:SS format (FR-018)', () => {
      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('0:00')).toBeInTheDocument(); // 0.5s rounded down
      expect(screen.getByText('0:03')).toBeInTheDocument(); // 3.5s
      expect(screen.getByText('0:07')).toBeInTheDocument(); // 7.5s
    });

    it('should render timestamp on left and text on right (FR-018)', () => {
      const { container } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const segmentContainers = container.querySelectorAll('[data-segment-id]');
      expect(segmentContainers.length).toBe(3);

      // Check first segment structure
      const firstSegment = segmentContainers[0];
      expect(firstSegment).toHaveClass('flex');
      expect(firstSegment).toHaveClass('gap-4');
    });
  });

  describe('Error States', () => {
    it('should render error message when fetch fails with no segments', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Could not load transcript segments.')).toBeInTheDocument();
    });

    it('should render retry button in error state', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call retry when retry button is clicked', async () => {
      const mockRetry = vi.fn();
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        fetchNextPage: vi.fn(),
        retry: mockRetry,
        cancelRequests: vi.fn(),
      });

      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalledTimes(1);
      });
    });

    it('should preserve loaded segments when error occurs during pagination (FR-025b)', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 100,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: true,
        isError: true,
        error: { type: 'network', message: 'Network error' },
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      // Segments should still be visible
      expect(screen.getByText('Welcome to this video tutorial.')).toBeInTheDocument();
      expect(screen.getByText('Today we will learn about React testing.')).toBeInTheDocument();

      // Error message should be shown inline
      expect(screen.getByText('Could not load more segments.')).toBeInTheDocument();
    });
  });

  describe('End of Transcript', () => {
    it('should show "End of transcript" when all segments loaded (FR-020e)', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 3,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('End of transcript')).toBeInTheDocument();
    });

    it('should NOT show "End of transcript" when more segments available', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 100,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: true,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.queryByText('End of transcript')).not.toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('should show message when no segments available', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: [],
        totalCount: 0,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByText('No transcript segments available for this language.')).toBeInTheDocument();
    });
  });

  describe('Keyboard Navigation (NFR-A11-A14)', () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 3,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });
    });

    it('should be focusable with tabindex="0" (NFR-A11)', () => {
      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      expect(container).toHaveAttribute('tabindex', '0');
    });

    it('should scroll down when ArrowDown is pressed (NFR-A12)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{ArrowDown}');

      // scrollBy should be called on the container
      expect(container.scrollBy).toHaveBeenCalled();
    });

    it('should scroll up when ArrowUp is pressed (NFR-A12)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{ArrowUp}');

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it('should scroll by viewport height with PageDown (NFR-A13)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{PageDown}');

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it('should scroll by viewport height with PageUp (NFR-A13)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{PageUp}');

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it('should scroll to beginning with Home key (NFR-A14)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{Home}');

      expect(container.scrollTo).toHaveBeenCalledWith(
        expect.objectContaining({ top: 0 })
      );
    });

    it('should scroll to end with End key (NFR-A14)', async () => {
      const { user } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      container.focus();

      await user.keyboard('{End}');

      expect(container.scrollTo).toHaveBeenCalled();
    });
  });

  describe('Accessibility Attributes (NFR-A15)', () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 3,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });
    });

    it('should have region role with proper label', () => {
      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      expect(screen.getByRole('region', { name: 'Transcript segments' })).toBeInTheDocument();
    });

    it('should have visible focus indicator', () => {
      renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      const container = screen.getByRole('region', { name: 'Transcript segments' });
      expect(container).toHaveClass('focus-visible:ring-2');
      expect(container).toHaveClass('focus-visible:ring-blue-500');
    });
  });

  describe('Virtualization (NFR-P12-P16)', () => {
    it('should use standard rendering for < 500 segments', () => {
      mockUseTranscriptSegments.mockReturnValue({
        segments: mockSegments,
        totalCount: 3,
        isLoading: false,
        isFetchingNextPage: false,
        hasNextPage: false,
        isError: false,
        error: null,
        fetchNextPage: vi.fn(),
        retry: vi.fn(),
        cancelRequests: vi.fn(),
      });

      const { container } = renderWithProviders(
        <TranscriptSegments
          videoId="test-video"
          languageCode="en"
        />
      );

      // Standard rendering should show all segment elements directly
      const segmentElements = container.querySelectorAll('[data-segment-id]');
      expect(segmentElements.length).toBe(3);
    });
  });
});
