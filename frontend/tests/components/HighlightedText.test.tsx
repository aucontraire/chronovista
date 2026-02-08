/**
 * Tests for HighlightedText Component
 *
 * Validates query term highlighting, case-insensitivity, and edge cases.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HighlightedText } from '../../src/components/HighlightedText';

describe('HighlightedText', () => {
  describe('Basic Highlighting', () => {
    it('highlights single term', () => {
      const { container } = render(
        <HighlightedText text="Machine learning basics" queryTerms={['learning']} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toBeInTheDocument();
      expect(mark).toHaveTextContent('learning');
      expect(mark).toHaveClass('bg-yellow-200', 'text-yellow-900');
    });

    it('highlights multiple terms', () => {
      const { container } = render(
        <HighlightedText
          text="Machine learning with Python"
          queryTerms={['machine', 'python']}
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(marks[0]).toHaveTextContent('Machine');
      expect(marks[1]).toHaveTextContent('Python');
    });

    it('highlights repeated terms', () => {
      const { container } = render(
        <HighlightedText
          text="Python is great, Python is versatile"
          queryTerms={['python']}
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      marks.forEach((mark) => {
        expect(mark).toHaveTextContent('Python');
      });
    });
  });

  describe('Case Sensitivity', () => {
    it('matches terms case-insensitively', () => {
      const { container } = render(
        <HighlightedText text="MACHINE learning Machine" queryTerms={['machine']} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(marks[0]).toHaveTextContent('MACHINE');
      expect(marks[1]).toHaveTextContent('Machine');
    });

    it('preserves original case in highlighted text', () => {
      const { container } = render(
        <HighlightedText text="PyTorch Tutorial" queryTerms={['pytorch']} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toHaveTextContent('PyTorch'); // Original casing preserved
    });
  });

  describe('Special Characters', () => {
    it('handles special regex characters in query terms', () => {
      const { container } = render(
        <HighlightedText
          text="Use $variable in code (important)"
          queryTerms={['$variable', '(important)']}
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(marks[0]).toHaveTextContent('$variable');
      expect(marks[1]).toHaveTextContent('(important)');
    });

    it('handles dots and asterisks', () => {
      const { container } = render(
        <HighlightedText text="file.txt and *.py files" queryTerms={['file.txt', '*.py']} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(marks[0]).toHaveTextContent('file.txt');
      expect(marks[1]).toHaveTextContent('*.py');
    });
  });

  describe('Edge Cases', () => {
    it('returns plain text when queryTerms is empty', () => {
      const { container } = render(
        <HighlightedText text="Machine learning" queryTerms={[]} />
      );

      expect(container.querySelector('mark')).not.toBeInTheDocument();
      expect(container.textContent).toBe('Machine learning');
    });

    it('returns plain text when text is empty', () => {
      const { container } = render(<HighlightedText text="" queryTerms={['machine']} />);

      expect(container.querySelector('mark')).not.toBeInTheDocument();
      expect(container.textContent).toBe('');
    });

    it('handles no matches gracefully', () => {
      const { container } = render(
        <HighlightedText text="Machine learning" queryTerms={['python', 'javascript']} />
      );

      expect(container.querySelector('mark')).not.toBeInTheDocument();
      expect(container.textContent).toBe('Machine learning');
    });

    it('handles partial word matches', () => {
      const { container } = render(
        <HighlightedText text="understanding" queryTerms={['stand']} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toBeInTheDocument();
      expect(mark).toHaveTextContent('stand');
      expect(container.textContent).toBe('understanding');
    });
  });

  describe('Styling', () => {
    it('applies correct Tailwind classes for WCAG AA compliance', () => {
      const { container } = render(
        <HighlightedText text="Machine learning" queryTerms={['learning']} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toHaveClass(
        'bg-yellow-200', // Background
        'text-yellow-900', // Text color (7.2:1 contrast)
        'font-semibold', // Emphasis
        'px-0.5', // Padding
        'rounded-sm' // Rounded corners
      );
    });
  });

  describe('Multiple Adjacent Matches', () => {
    it('highlights adjacent terms separately', () => {
      const { container } = render(
        <HighlightedText
          text="machine learning"
          queryTerms={['machine', 'learning']}
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(marks[0]).toHaveTextContent('machine');
      expect(marks[1]).toHaveTextContent('learning');
    });
  });
});
