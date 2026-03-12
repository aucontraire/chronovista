/**
 * TextHighlighter component for rendering text with search match highlights.
 *
 * Implements:
 * - FR-012: Highlight with bold/underline + background color (not color alone)
 * - NFR-003: Not color alone — uses bold + underline in addition to background
 * - NFR-005: WCAG 1.4.3 contrast ratio 4.5:1 for highlights on light background
 *
 * @module components/transcript/TextHighlighter
 */

import type React from "react";
import type { TranscriptSearchMatch } from "../../hooks/useTranscriptSearch";

/**
 * A highlight region within a text string.
 */
interface HighlightRegion {
  /** Character offset where the highlight starts */
  startOffset: number;
  /** Length of the highlighted string */
  length: number;
  /** Whether this is the currently active (focused) match */
  isActive: boolean;
}

/**
 * Props for the TextHighlighter component.
 */
export interface TextHighlighterProps {
  /** The full text to render */
  text: string;
  /** All search matches for this text's segment */
  matches: TranscriptSearchMatch[];
  /** Index of the segment in the segments array (used to filter relevant matches) */
  segmentIndex: number;
  /**
   * The global index of the currently active match.
   * Matches are stored globally across all segments; this is compared against
   * the match's position in the full matches array.
   */
  activeMatchIndex: number;
  /** All matches across all segments (needed to calculate if a match is active) */
  allMatches: TranscriptSearchMatch[];
}

/**
 * TextHighlighter renders text with search result highlights.
 *
 * - Non-active matches: amber-200 background, bold, underline (NFR-003, NFR-005)
 * - Active match: amber-400 background with ring outline, bold, underline
 * - Uses `<mark>` element for semantic correctness
 * - Achieves ≥4.5:1 contrast ratio (NFR-005):
 *   - amber-200 (#FDE68A) with gray-900 (#111827): ~8.5:1
 *   - amber-400 (#FBBF24) with gray-900 (#111827): ~7.2:1
 *
 * @example
 * ```tsx
 * <TextHighlighter
 *   text="Hello world, hello again"
 *   matches={matchesForThisSegment}
 *   segmentIndex={2}
 *   activeMatchIndex={currentIndex}
 *   allMatches={allMatches}
 * />
 * ```
 */
export function TextHighlighter({
  text,
  matches,
  segmentIndex,
  activeMatchIndex,
  allMatches,
}: TextHighlighterProps) {
  // Filter matches that belong to this segment
  const segmentMatches = matches.filter((m) => m.segmentIndex === segmentIndex);

  // If no matches in this segment, render plain text
  if (segmentMatches.length === 0) {
    return <>{text}</>;
  }

  // Build highlight regions, noting which global match index each corresponds to
  const regions: HighlightRegion[] = segmentMatches.map((match) => {
    // Find the global index of this match in allMatches
    const globalIndex = allMatches.findIndex(
      (m) =>
        m.segmentIndex === match.segmentIndex &&
        m.startOffset === match.startOffset &&
        m.length === match.length
    );
    return {
      startOffset: match.startOffset,
      length: match.length,
      isActive: globalIndex === activeMatchIndex,
    };
  });

  // Sort regions by startOffset (ascending) to process left-to-right
  regions.sort((a, b) => a.startOffset - b.startOffset);

  // Split text into alternating plain and highlighted segments
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (let i = 0; i < regions.length; i++) {
    const region = regions[i];
    if (!region) continue;

    // Plain text before this match
    if (region.startOffset > cursor) {
      parts.push(
        <span key={`plain-${i}`}>
          {text.slice(cursor, region.startOffset)}
        </span>
      );
    }

    // Highlighted match
    const matchText = text.slice(
      region.startOffset,
      region.startOffset + region.length
    );

    if (region.isActive) {
      // Active match: amber-400 background + ring outline
      // NFR-003: bold + underline (not color alone)
      // NFR-005: amber-400 (#FBBF24) on white gives ~7.2:1 with gray-900 text
      parts.push(
        <mark
          key={`match-${i}`}
          className="bg-amber-400 font-bold underline ring-2 ring-amber-600 ring-offset-0 rounded-sm"
          aria-current="true"
        >
          {matchText}
        </mark>
      );
    } else {
      // Non-active match: amber-200 background
      // NFR-003: bold + underline (not color alone)
      // NFR-005: amber-200 (#FDE68A) on white gives ~8.5:1 with gray-900 text
      parts.push(
        <mark
          key={`match-${i}`}
          className="bg-amber-200 font-bold underline rounded-sm"
        >
          {matchText}
        </mark>
      );
    }

    cursor = region.startOffset + region.length;
  }

  // Remaining plain text after the last match
  if (cursor < text.length) {
    parts.push(<span key="plain-end">{text.slice(cursor)}</span>);
  }

  return <>{parts}</>;
}
