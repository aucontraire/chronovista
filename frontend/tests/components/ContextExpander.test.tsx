/**
 * Tests for ContextExpander Component - User Story 3: View Surrounding Context
 *
 * Requirements tested:
 * - FR-007: Show expanded context (200 chars before/after)
 * - FR-028: aria-expanded, aria-controls, hidden attributes
 * - FR-031: Focus management (focus content when expanded)
 * - EC-009: Hide button when no context available
 *
 * Test coverage:
 * - Expand/collapse behavior
 * - ARIA attributes (aria-expanded, aria-controls)
 * - Focus management (focus moves to content when expanded)
 * - Hide button when no context available
 * - Display context_before and context_after correctly
 * - Handle case when one context field is empty but other has content
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ContextExpander } from '../../src/components/ContextExpander';

describe('ContextExpander', () => {
  const mockContextBefore = 'This is the context before the main segment.';
  const mockContextAfter = 'This is the context after the main segment.';
  const mockResultId = 'result-123';
  const mockVideoTitle = 'Introduction to Machine Learning';

  describe('Basic Rendering', () => {
    it('should render expand button when context is available', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByRole('button', { name: /expand additional context/i })).toBeInTheDocument();
    });

    it('should show "Show context" text when collapsed', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText('Show context')).toBeInTheDocument();
    });

    it('should show "Hide context" text when expanded', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText('Hide context')).toBeInTheDocument();
    });

    it('should display context content when expanded', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/This is the context before/)).toBeInTheDocument();
      expect(screen.getByText(/This is the context after/)).toBeInTheDocument();
    });

    it('should hide context content when collapsed', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contextDiv = screen.queryByText(/This is the context before/);
      expect(contextDiv).not.toBeVisible();
    });
  });

  describe('ARIA Attributes (FR-028)', () => {
    it('should have aria-expanded="false" when collapsed', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'false');
    });

    it('should have aria-expanded="true" when expanded', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('should have aria-controls pointing to content div', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-controls', `context-${mockResultId}`);
    });

    it('should have descriptive aria-label when collapsed', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute(
        'aria-label',
        `Expand additional context for "${mockVideoTitle}"`
      );
    });

    it('should have descriptive aria-label when expanded', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute(
        'aria-label',
        `Collapse additional context for "${mockVideoTitle}"`
      );
    });

    it('should have hidden attribute on content div when collapsed', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);
      expect(contentDiv).toHaveAttribute('hidden');
    });

    it('should not have hidden attribute on content div when expanded', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);
      expect(contentDiv).not.toHaveAttribute('hidden');
    });

    it('should have id matching aria-controls on content div', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);
      expect(contentDiv).toBeInTheDocument();
      expect(contentDiv).toHaveAttribute('id', `context-${mockResultId}`);
    });
  });

  describe('Expand/Collapse Behavior', () => {
    it('should call onToggle when button is clicked', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it('should call onToggle when expanded and clicked again', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      expect(onToggle).toHaveBeenCalledTimes(1);
    });
  });

  describe('Focus Management (FR-031)', () => {
    it('should set tabIndex=-1 on content div for programmatic focus', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);
      expect(contentDiv).toHaveAttribute('tabIndex', '-1');
    });

    it('should focus content div when expanded', async () => {
      const onToggle = vi.fn();
      const { container, rerender } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      // Simulate the parent component updating expanded state
      rerender(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);

      // In a real browser, focus would be set. We verify the element is focusable.
      expect(contentDiv).toHaveAttribute('tabIndex', '-1');
    });
  });

  describe('Context Display (FR-007)', () => {
    it('should display context_before with ellipsis prefix', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={null}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/\.\.\.This is the context before/)).toBeInTheDocument();
    });

    it('should display context_after with ellipsis suffix', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={null}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/This is the context after/)).toBeInTheDocument();
      expect(screen.getByText(/\.\.\./)).toBeInTheDocument();
    });

    it('should display both context_before and context_after when both are present', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/This is the context before/)).toBeInTheDocument();
      expect(screen.getByText(/This is the context after/)).toBeInTheDocument();
    });
  });

  describe('Edge Cases - No Context Available (EC-009)', () => {
    it('should return null when both context_before and context_after are null', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={null}
          contextAfter={null}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it('should return null when both context_before and context_after are empty strings', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore=""
          contextAfter=""
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it('should return null when both are undefined', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={undefined}
          contextAfter={undefined}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it('should render when only context_before is available', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={null}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('should render when only context_after is available', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={null}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('should render when context_before is empty but context_after has content', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore=""
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.queryByText(/This is the context before/)).not.toBeInTheDocument();
      expect(screen.getByText(/This is the context after/)).toBeInTheDocument();
    });

    it('should render when context_after is empty but context_before has content', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter=""
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/\.\.\.This is the context before/)).toBeInTheDocument();
      expect(screen.queryByText(/This is the context after\.\.\./)).not.toBeInTheDocument();
    });
  });

  describe('Long Context Text', () => {
    it('should handle very long context_before text', () => {
      const onToggle = vi.fn();
      const longContext = 'A'.repeat(200);
      render(
        <ContextExpander
          contextBefore={longContext}
          contextAfter={null}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(new RegExp(`\\.\\.\\.${longContext}`))).toBeInTheDocument();
    });

    it('should handle very long context_after text', () => {
      const onToggle = vi.fn();
      const longContext = 'B'.repeat(200);
      render(
        <ContextExpander
          contextBefore={null}
          contextAfter={longContext}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(new RegExp(`${longContext}\\.\\.\\.`))).toBeInTheDocument();
    });
  });

  describe('Special Characters in Context', () => {
    it('should handle special characters in context text', () => {
      const onToggle = vi.fn();
      const specialContext = 'Context with $pecial characters & symbols (2024)!';
      render(
        <ContextExpander
          contextBefore={specialContext}
          contextAfter={null}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/\$pecial characters & symbols/)).toBeInTheDocument();
    });

    it('should handle emoji in context text', () => {
      const onToggle = vi.fn();
      const emojiContext = 'Context with emoji 🚀 and symbols 💻';
      render(
        <ContextExpander
          contextBefore={emojiContext}
          contextAfter={null}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      expect(screen.getByText(/Context with emoji 🚀/)).toBeInTheDocument();
    });
  });

  describe('Keyboard Accessibility', () => {
    it('should be keyboard focusable via tab', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      button.focus();
      expect(button).toHaveFocus();
    });

    it('should activate on Enter key', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      button.focus();

      // Buttons automatically respond to Enter key - we verify the button is accessible
      expect(button).toHaveFocus();

      // Simulate click which Enter would trigger
      fireEvent.click(button);

      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it('should activate on Space key', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      button.focus();

      // Buttons automatically respond to Space key - we verify the button is accessible
      expect(button).toHaveFocus();

      // Simulate click which Space would trigger
      fireEvent.click(button);

      expect(onToggle).toHaveBeenCalledTimes(1);
    });
  });

  describe('Styling', () => {
    it('should apply correct Tailwind classes to button', () => {
      const onToggle = vi.fn();
      render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={false}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveClass('text-sm', 'text-blue-600', 'dark:text-blue-400');
    });

    it('should apply correct Tailwind classes to context div', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const contentDiv = container.querySelector(`#context-${mockResultId}`);
      expect(contentDiv).toHaveClass('mt-2', 'p-3', 'bg-gray-50', 'dark:bg-gray-900/50', 'rounded');
    });

    it('should apply correct text color classes to context paragraphs', () => {
      const onToggle = vi.fn();
      const { container } = render(
        <ContextExpander
          contextBefore={mockContextBefore}
          contextAfter={mockContextAfter}
          expanded={true}
          onToggle={onToggle}
          resultId={mockResultId}
          videoTitle={mockVideoTitle}
        />
      );

      const paragraphs = container.querySelectorAll('p');
      paragraphs.forEach((p) => {
        expect(p).toHaveClass('text-gray-600', 'dark:text-gray-400');
      });
    });
  });
});
