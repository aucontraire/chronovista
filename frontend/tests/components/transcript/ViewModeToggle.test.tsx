/**
 * Tests for ViewModeToggle component.
 *
 * Covers:
 * - Segments/Full Text toggle rendering
 * - Mode change callback
 * - ARIA pressed states
 * - Keyboard accessibility
 * - Accessibility announcements
 * - Visual styling for active/inactive states
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { renderWithProviders } from '../../test-utils';
import { ViewModeToggle } from '../../../src/components/transcript/ViewModeToggle';
import type { ViewMode } from '../../../src/components/transcript/ViewModeToggle';

describe('ViewModeToggle', () => {
  const mockOnModeChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render toggle button group with proper role', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      expect(screen.getByRole('group', { name: 'Transcript view mode' })).toBeInTheDocument();
    });

    it('should render both Segments and Full Text buttons', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      expect(screen.getByRole('button', { name: 'Segments' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Full Text' })).toBeInTheDocument();
    });
  });

  describe('Mode Change Callback', () => {
    it('should call onModeChange when Segments button is clicked', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      await user.click(segmentsButton);

      await waitFor(() => {
        expect(mockOnModeChange).toHaveBeenCalledWith('segments');
      });
    });

    it('should call onModeChange when Full Text button is clicked', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      await user.click(fullTextButton);

      await waitFor(() => {
        expect(mockOnModeChange).toHaveBeenCalledWith('fulltext');
      });
    });

    it('should NOT call onModeChange when already active button is clicked', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      await user.click(segmentsButton);

      await waitFor(() => {
        expect(mockOnModeChange).not.toHaveBeenCalled();
      });
    });
  });

  describe('ARIA Pressed States', () => {
    it('should set aria-pressed="true" for active Segments mode', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      expect(segmentsButton).toHaveAttribute('aria-pressed', 'true');
    });

    it('should set aria-pressed="false" for inactive Segments mode', () => {
      renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      expect(segmentsButton).toHaveAttribute('aria-pressed', 'false');
    });

    it('should set aria-pressed="true" for active Full Text mode', () => {
      renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      expect(fullTextButton).toHaveAttribute('aria-pressed', 'true');
    });

    it('should set aria-pressed="false" for inactive Full Text mode', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      expect(fullTextButton).toHaveAttribute('aria-pressed', 'false');
    });
  });

  describe('Keyboard Accessibility (NFR-A06)', () => {
    it('should be keyboard accessible via Tab navigation', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });

      segmentsButton.focus();
      expect(segmentsButton).toHaveFocus();

      fullTextButton.focus();
      expect(fullTextButton).toHaveFocus();
    });

    it('should activate button via Enter key', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      fullTextButton.focus();

      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockOnModeChange).toHaveBeenCalledWith('fulltext');
      });
    });

    it('should activate button via Space key', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      fullTextButton.focus();

      await user.keyboard(' ');

      await waitFor(() => {
        expect(mockOnModeChange).toHaveBeenCalledWith('fulltext');
      });
    });
  });

  describe('Accessibility Announcements (NFR-A04)', () => {
    it('should announce view change when switching to Segments', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      await user.click(segmentsButton);

      await waitFor(() => {
        const announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('View changed to Segments');
      });
    });

    it('should announce view change when switching to Full Text', async () => {
      const { user } = renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      await user.click(fullTextButton);

      await waitFor(() => {
        const announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('View changed to Full Text');
      });
    });

    it('should clear announcement after it has been read', async () => {
      vi.useFakeTimers();

      try {
        renderWithProviders(
          <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
        );

        const fullTextButton = screen.getByRole('button', { name: 'Full Text' });

        // Click and advance timers in act()
        act(() => {
          fullTextButton.click();
        });

        let announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('View changed to Full Text');

        // Fast-forward past announcement clear
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1500);
        });

        announcement = screen.getByRole('status');
        expect(announcement).toHaveTextContent('');
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe('Visual Styling', () => {
    it('should have active styling for Segments mode when selected', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      expect(segmentsButton).toHaveClass('bg-blue-600');
      expect(segmentsButton).toHaveClass('text-white');
    });

    it('should have inactive styling for Segments mode when not selected', () => {
      renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      expect(segmentsButton).toHaveClass('bg-gray-100');
      expect(segmentsButton).toHaveClass('text-gray-700');
    });

    it('should have active styling for Full Text mode when selected', () => {
      renderWithProviders(
        <ViewModeToggle mode="fulltext" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      expect(fullTextButton).toHaveClass('bg-blue-600');
      expect(fullTextButton).toHaveClass('text-white');
    });

    it('should have inactive styling for Full Text mode when not selected', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });
      expect(fullTextButton).toHaveClass('bg-gray-100');
      expect(fullTextButton).toHaveClass('text-gray-700');
    });
  });

  describe('Focus Management', () => {
    it('should have visible focus indicator on buttons', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      expect(segmentsButton).toHaveClass('focus-visible:ring-2');
      expect(segmentsButton).toHaveClass('focus-visible:ring-blue-500');
    });
  });

  describe('Button Type', () => {
    it('should have type="button" to prevent form submission', () => {
      renderWithProviders(
        <ViewModeToggle mode="segments" onModeChange={mockOnModeChange} />
      );

      const segmentsButton = screen.getByRole('button', { name: 'Segments' });
      const fullTextButton = screen.getByRole('button', { name: 'Full Text' });

      expect(segmentsButton).toHaveAttribute('type', 'button');
      expect(fullTextButton).toHaveAttribute('type', 'button');
    });
  });
});
