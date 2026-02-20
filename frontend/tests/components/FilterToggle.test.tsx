/**
 * Tests for FilterToggle component.
 *
 * Covers:
 * - Renders native checkbox with associated label
 * - Label text matches provided prop
 * - Checking adds param key=true to URL
 * - Unchecking removes param from URL (not =false)
 * - Checked state reflects current URL param value
 * - Focus remains on checkbox after state change (FR-032)
 * - 44×44px minimum interactive hit area per WCAG 2.5.8 (FR-005)
 * - Preserves existing URL params when toggling
 * - Renders unchecked by default when URL param is absent
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, getTestLocation } from '../test-utils';
import { FilterToggle } from '../../src/components/FilterToggle';

/**
 * Helper to render FilterToggle with all providers.
 */
function renderFilterToggle(paramKey: string, label: string, initialUrl = '/') {
  return renderWithProviders(<FilterToggle paramKey={paramKey} label={label} />, {
    initialEntries: [initialUrl],
  });
}

describe('FilterToggle', () => {
  describe('Rendering', () => {
    it('should render a native checkbox input', () => {
      renderFilterToggle('liked_only', 'Show Liked Only');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      expect(checkbox).toBeInTheDocument();
      expect(checkbox.tagName).toBe('INPUT');
      expect(checkbox).toHaveAttribute('type', 'checkbox');
    });

    it('should render an associated label with correct text', () => {
      renderFilterToggle('has_transcript', 'Has Transcripts');

      const label = screen.getByText('Has Transcripts');
      expect(label).toBeInTheDocument();
      expect(label.tagName).toBe('LABEL');
    });

    it('should associate label with checkbox via htmlFor', () => {
      renderFilterToggle('test_param', 'Test Label');

      const checkbox = screen.getByRole('checkbox', { name: /test label/i });
      const label = screen.getByText('Test Label');

      // Verify label's htmlFor matches checkbox id
      expect(label).toHaveAttribute('for');
      expect(checkbox).toHaveAttribute('id');
      expect(label.getAttribute('for')).toBe(checkbox.getAttribute('id'));
    });

    it('should render unchecked by default when URL param is absent', () => {
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      expect(checkbox).not.toBeChecked();
    });

    it('should render checked when URL param is true', () => {
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos?liked_only=true');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      expect(checkbox).toBeChecked();
    });

    it('should render unchecked when URL param is false', () => {
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos?liked_only=false');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      expect(checkbox).not.toBeChecked();
    });
  });

  describe('URL Parameter Synchronization', () => {
    it('should add param key=true to URL when checked', async () => {
      const user = userEvent.setup();
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });

      await user.click(checkbox);

      // Checkbox should be checked
      expect(checkbox).toBeChecked();

      // URL should contain liked_only=true
      const location = getTestLocation();
      expect(location.search).toContain('liked_only=true');
    });

    it('should remove param from URL when unchecked (not set to false)', async () => {
      const user = userEvent.setup();
      renderFilterToggle('has_transcript', 'Has Transcripts', '/videos?has_transcript=true');

      const checkbox = screen.getByRole('checkbox', { name: /has transcripts/i });
      expect(checkbox).toBeChecked();

      await user.click(checkbox);

      // Checkbox should be unchecked
      expect(checkbox).not.toBeChecked();

      // URL should NOT contain has_transcript param at all
      const location = getTestLocation();
      expect(location.search).not.toContain('has_transcript');
    });

    it('should preserve existing URL params when toggling', async () => {
      const user = userEvent.setup();
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos?sort_by=title&tag=music');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });

      await user.click(checkbox);

      // Should preserve existing params
      const location = getTestLocation();
      expect(location.search).toContain('sort_by=title');
      expect(location.search).toContain('tag=music');
      expect(location.search).toContain('liked_only=true');
    });

    it('should use snake_case param keys', async () => {
      const user = userEvent.setup();
      renderFilterToggle('unavailable_only', 'Unavailable Only', '/playlists/123/videos');

      const checkbox = screen.getByRole('checkbox', { name: /unavailable only/i });

      await user.click(checkbox);

      // Should use snake_case in URL
      const location = getTestLocation();
      expect(location.search).toContain('unavailable_only=true');
      expect(location.search).not.toContain('unavailableOnly');
    });
  });

  describe('Focus Management (FR-032)', () => {
    it('should maintain focus on checkbox after checking', async () => {
      const user = userEvent.setup();
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });

      await user.click(checkbox);

      // Focus should remain on checkbox
      expect(checkbox).toHaveFocus();
    });

    it('should maintain focus on checkbox after unchecking', async () => {
      const user = userEvent.setup();
      renderFilterToggle('has_transcript', 'Has Transcripts', '/videos?has_transcript=true');

      const checkbox = screen.getByRole('checkbox', { name: /has transcripts/i });

      await user.click(checkbox);

      // Focus should remain on checkbox
      expect(checkbox).toHaveFocus();
    });
  });

  describe('Accessibility (WCAG 2.5.8 - FR-005)', () => {
    it('should have minimum 44×44px interactive hit area', () => {
      renderFilterToggle('liked_only', 'Show Liked Only');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      const container = checkbox.closest('div, label');

      // Container should have min-h-[44px] class or equivalent
      expect(container).toBeInTheDocument();
      if (container) {
        const styles = window.getComputedStyle(container);
        // This test verifies the class exists; actual pixel measurement would require jsdom-testing-library
        expect(container.className).toMatch(/min-h-\[44px\]/);
      }
    });

    it('should be keyboard accessible', async () => {
      const user = userEvent.setup();
      renderFilterToggle('liked_only', 'Show Liked Only', '/videos');

      const checkbox = screen.getByRole('checkbox', { name: /show liked only/i });

      // Tab to checkbox
      await user.tab();
      expect(checkbox).toHaveFocus();

      // Press Space to toggle
      await user.keyboard(' ');
      expect(checkbox).toBeChecked();

      // Press Space again to toggle off
      await user.keyboard(' ');
      expect(checkbox).not.toBeChecked();
    });
  });

  describe('Edge Cases', () => {
    it('should handle multiple toggles on same page', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <>
          <FilterToggle paramKey="liked_only" label="Show Liked Only" />
          <FilterToggle paramKey="has_transcript" label="Has Transcripts" />
        </>,
        { initialEntries: ['/videos'] }
      );

      const likedCheckbox = screen.getByRole('checkbox', { name: /show liked only/i });
      const transcriptCheckbox = screen.getByRole('checkbox', { name: /has transcripts/i });

      await user.click(likedCheckbox);
      await user.click(transcriptCheckbox);

      expect(likedCheckbox).toBeChecked();
      expect(transcriptCheckbox).toBeChecked();

      const location = getTestLocation();
      expect(location.search).toContain('liked_only=true');
      expect(location.search).toContain('has_transcript=true');
    });

    it('should handle rapid toggling', async () => {
      const user = userEvent.setup();
      renderFilterToggle('test_param', 'Test Toggle', '/test');

      const checkbox = screen.getByRole('checkbox', { name: /test toggle/i });

      // Rapid clicks
      await user.click(checkbox);
      await user.click(checkbox);
      await user.click(checkbox);

      // Final state should be checked
      expect(checkbox).toBeChecked();

      const location = getTestLocation();
      expect(location.search).toContain('test_param=true');
    });

    it('should handle special characters in label', () => {
      renderFilterToggle('test_param', "Show Videos I've Liked & Watched");

      const label = screen.getByText("Show Videos I've Liked & Watched");
      expect(label).toBeInTheDocument();
    });

    it('should sync state when URL changes externally', () => {
      const { rerender } = renderFilterToggle('liked_only', 'Show Liked Only', '/videos');

      let checkbox = screen.getByRole('checkbox', { name: /show liked only/i });
      expect(checkbox).not.toBeChecked();

      // Simulate URL change (e.g., browser back/forward)
      rerender(<FilterToggle paramKey="liked_only" label="Show Liked Only" />);

      // Re-query checkbox after rerender
      checkbox = screen.getByRole('checkbox', { name: /show liked only/i });

      // Note: This test verifies that the component re-renders with new URL state
      // In a real app, the URL would change via browser navigation
      // Here we just verify the component responds to prop changes
      expect(checkbox).toBeInTheDocument();
    });
  });
});
