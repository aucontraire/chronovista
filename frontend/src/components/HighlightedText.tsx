/**
 * HighlightedText Component
 *
 * Highlights query terms within text using <mark> elements with accessible colors.
 * Meets WCAG AA contrast requirements (7.2:1 ratio).
 *
 * @see FR-004 in spec.md
 */

interface HighlightedTextProps {
  /** The text content to display and highlight */
  text: string;
  /** Array of terms to highlight (case-insensitive matching) */
  queryTerms: string[];
}

/**
 * Renders text with highlighted query terms.
 *
 * Features:
 * - Case-insensitive term matching
 * - Handles special regex characters in query terms
 * - WCAG AA compliant colors (bg-yellow-200 + text-yellow-900 = 7.2:1)
 * - Semantic <mark> element for accessibility
 *
 * @example
 * ```tsx
 * <HighlightedText
 *   text="Machine learning fundamentals"
 *   queryTerms={["machine", "learning"]}
 * />
 * ```
 */
export function HighlightedText({ text, queryTerms }: HighlightedTextProps) {
  // Early return for edge cases
  if (!queryTerms.length || !text) {
    return <>{text}</>;
  }

  /**
   * Escapes special regex characters to prevent regex injection.
   * Handles characters: . * + ? ^ $ { } ( ) | [ ] \
   */
  const escapeRegex = (str: string): string =>
    str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Build case-insensitive pattern from all query terms
  const pattern = new RegExp(
    `(${queryTerms.map(escapeRegex).join('|')})`,
    'gi'
  );

  // Split text by matches (preserves matched terms in array)
  const parts = text.split(pattern);

  return (
    <>
      {parts.map((part, i) =>
        queryTerms.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
          <mark
            key={i}
            className="bg-yellow-200 text-yellow-900 font-semibold px-0.5 rounded-sm"
          >
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
}
