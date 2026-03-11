/**
 * HighlightedDiff Component
 *
 * Renders a before/after text diff with inline match highlighting.
 * Used in batch correction preview cards to show what text will change.
 *
 * Accessibility (NFR-003):
 * - Does NOT rely on color alone — removed text uses strikethrough,
 *   added text uses bold + underline in addition to color cues.
 * - Highlighted spans carry descriptive aria-labels for screen readers.
 * - The container is wrapped in a `role="group"` landmark so assistive
 *   technology can announce the group as a single "Text change preview".
 *
 * @see T014 in batch corrections spec
 */

export interface HighlightedDiffProps {
  /** The original text before replacement */
  currentText: string;
  /** The text after replacement */
  proposedText: string;
  /** Character offset where the match starts in currentText */
  matchStart: number;
  /** Character offset where the match ends (exclusive) in currentText */
  matchEnd: number;
  /** Optional className for the outermost container */
  className?: string;
}

/**
 * Computes the character length of the replacement string inside `proposedText`.
 *
 * The replacement length equals the match length in `currentText` plus whatever
 * net characters the substitution added or removed:
 *   replacementLength = matchLength + (proposedText.length - currentText.length)
 */
function computeReplacementLength(
  currentText: string,
  proposedText: string,
  matchStart: number,
  matchEnd: number
): number {
  const matchLength = matchEnd - matchStart;
  const delta = proposedText.length - currentText.length;
  return Math.max(0, matchLength + delta);
}

/**
 * Renders a two-zone diff card showing the original ("Current") text alongside
 * the replacement ("Proposed") text. The matched portion in the before-zone is
 * highlighted in red with strikethrough; the replacement in the after-zone is
 * highlighted in green with bold and underline.
 *
 * @example
 * ```tsx
 * <HighlightedDiff
 *   currentText="The colour is red."
 *   proposedText="The color is red."
 *   matchStart={4}
 *   matchEnd={10}
 * />
 * ```
 */
export function HighlightedDiff({
  currentText,
  proposedText,
  matchStart,
  matchEnd,
  className,
}: HighlightedDiffProps) {
  const replacementLength = computeReplacementLength(
    currentText,
    proposedText,
    matchStart,
    matchEnd
  );

  // Slices for the "Current" (before) zone
  const beforePrefix = currentText.slice(0, matchStart);
  const beforeMatch = currentText.slice(matchStart, matchEnd);
  const beforeSuffix = currentText.slice(matchEnd);

  // Slices for the "Proposed" (after) zone
  const afterPrefix = proposedText.slice(0, matchStart);
  const afterReplacement = proposedText.slice(
    matchStart,
    matchStart + replacementLength
  );
  const afterSuffix = proposedText.slice(matchStart + replacementLength);

  return (
    <div
      role="group"
      aria-label="Text change preview"
      className={`flex flex-col sm:flex-row gap-3 ${className ?? ""}`}
    >
      {/* Before zone — Current text */}
      <div className="flex-1 min-w-0">
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
          Current
        </p>
        <p className="text-sm text-gray-800 leading-relaxed break-words">
          {beforePrefix}
          <span
            className="text-red-600 line-through bg-red-50 rounded-sm px-0.5"
            aria-label={`removed: ${beforeMatch}`}
          >
            {beforeMatch}
          </span>
          {beforeSuffix}
        </p>
      </div>

      {/* Divider — hidden from screen readers */}
      <div
        aria-hidden="true"
        className="hidden sm:flex items-center text-gray-300 shrink-0 select-none"
      >
        →
      </div>

      {/* After zone — Proposed text */}
      <div className="flex-1 min-w-0">
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
          Proposed
        </p>
        <p className="text-sm text-gray-800 leading-relaxed break-words">
          {afterPrefix}
          <span
            className="text-green-700 font-bold underline bg-green-50 rounded-sm px-0.5"
            aria-label={`added: ${afterReplacement}`}
          >
            {afterReplacement}
          </span>
          {afterSuffix}
        </p>
      </div>
    </div>
  );
}
