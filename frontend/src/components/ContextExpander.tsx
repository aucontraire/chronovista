/**
 * ContextExpander Component - User Story 3: View Surrounding Context
 *
 * Implements FR-007, FR-028, FR-031, EC-009: Expandable context display for search results.
 *
 * Features:
 * - Expand/collapse button for viewing additional context
 * - ARIA attributes for accessibility (aria-expanded, aria-controls, hidden)
 * - Focus management (FR-031, T054):
 *   - Focus moves to content when expanded
 *   - Focus returns to button when collapsed
 * - Automatic hiding when no context is available
 * - Display context_before and context_after with ellipsis indicators
 *
 * @see FR-007: Show expanded context (200 chars before/after)
 * @see FR-028: ARIA attributes for accessibility
 * @see FR-031: Focus management
 * @see EC-009: Hide button when no context available
 */

import { useRef, useEffect } from 'react';

interface ContextExpanderProps {
  /** Previous segment text (up to 200 chars, null if first segment) */
  contextBefore: string | null | undefined;
  /** Next segment text (up to 200 chars, null if last segment) */
  contextAfter: string | null | undefined;
  /** Whether the context is currently expanded */
  expanded: boolean;
  /** Callback when expand/collapse is toggled */
  onToggle: () => void;
  /** Unique identifier for the result (used for ARIA attributes) */
  resultId: string;
  /** Video title for accessible button labels */
  videoTitle: string;
}

/**
 * Displays expandable context (previous/next segment text) for search results.
 *
 * Shows a button to expand/collapse additional context from surrounding segments.
 * When expanded, displays context_before and context_after with ellipsis indicators.
 * Automatically hides when no context is available.
 *
 * @example
 * ```tsx
 * <ContextExpander
 *   contextBefore="Previous segment text..."
 *   contextAfter="Next segment text..."
 *   expanded={isExpanded}
 *   onToggle={() => setIsExpanded(!isExpanded)}
 *   resultId="result-123"
 *   videoTitle="Introduction to Machine Learning"
 * />
 * ```
 */
export function ContextExpander({
  contextBefore,
  contextAfter,
  expanded,
  onToggle,
  resultId,
  videoTitle,
}: ContextExpanderProps) {
  // Check if any context is available
  const hasContext = contextBefore || contextAfter;

  // Return null if no context is available (EC-009)
  if (!hasContext) {
    return null;
  }

  const contentId = `context-${resultId}`;
  const contentRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Focus management: focus content when expanded, button when collapsed (FR-031, T054)
  useEffect(() => {
    if (expanded && contentRef.current) {
      // Move focus to content when expanded
      contentRef.current.focus();
    }
    // Note: When collapsed, button naturally retains focus as it's the element that was clicked
  }, [expanded]);

  const handleToggle = () => {
    onToggle();
  };

  return (
    <div className="mt-3">
      <button
        ref={buttonRef}
        onClick={handleToggle}
        aria-expanded={expanded}
        aria-controls={contentId}
        aria-label={
          expanded
            ? `Collapse additional context for "${videoTitle}"`
            : `Expand additional context for "${videoTitle}"`
        }
        className="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 rounded px-2 py-1 transition-colors"
      >
        {expanded ? 'Hide context' : 'Show context'}
      </button>

      <div
        id={contentId}
        hidden={!expanded}
        tabIndex={-1}
        ref={contentRef}
        className="mt-2 p-3 bg-gray-50 dark:bg-gray-900/50 rounded outline-none"
      >
        {contextBefore && (
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            ...{contextBefore}
          </p>
        )}
        {contextAfter && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {contextAfter}...
          </p>
        )}
      </div>
    </div>
  );
}
