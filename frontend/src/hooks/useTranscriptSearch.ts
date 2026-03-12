/**
 * useTranscriptSearch hook for client-side transcript segment search.
 *
 * Implements:
 * - FR-011: Client-side search field in transcript panel
 * - FR-013: Auto-scroll to first match, Previous/Next with "N of M" counter
 * - FR-020: 300ms debounce on search input
 *
 * @module hooks/useTranscriptSearch
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { TranscriptSegment } from "../types/transcript";
import { DEBOUNCE_CONFIG } from "../styles/tokens";

/**
 * Represents a single search match within a transcript segment.
 */
export interface TranscriptSearchMatch {
  /** Index of the segment in the segments array that contains this match */
  segmentIndex: number;
  /** Character offset where the match starts in the segment text */
  startOffset: number;
  /** Length of the matched string */
  length: number;
}

/**
 * Return type for the useTranscriptSearch hook.
 */
export interface UseTranscriptSearchResult {
  /** All matches across all segments */
  matches: TranscriptSearchMatch[];
  /** Index of the currently active/highlighted match (0-based) */
  currentIndex: number;
  /** Total number of matches */
  total: number;
  /** Navigate to the next match (wraps from last to first) */
  next: () => void;
  /** Navigate to the previous match (wraps from first to last) */
  prev: () => void;
  /** The debounced query string currently applied */
  query: string;
  /** Set a new search query (debounced 300ms per FR-020) */
  setQuery: (q: string) => void;
  /** Clear the search query and reset navigation state */
  reset: () => void;
}

/**
 * Hook for searching transcript segments client-side.
 *
 * Features:
 * - Case-insensitive search using String.toLowerCase().indexOf()
 * - 300ms debounce on input (FR-020)
 * - Wraparound navigation: last→first and first→last
 * - Empty query returns no matches
 *
 * @param segments - Array of transcript segments to search within
 * @param initialQuery - Optional initial search query
 * @returns UseTranscriptSearchResult with match state and navigation functions
 *
 * @example
 * ```tsx
 * const {
 *   matches,
 *   currentIndex,
 *   total,
 *   next,
 *   prev,
 *   query,
 *   setQuery,
 *   reset,
 * } = useTranscriptSearch(segments);
 * ```
 */
export function useTranscriptSearch(
  segments: TranscriptSegment[],
  initialQuery: string = ""
): UseTranscriptSearchResult {
  // Raw (un-debounced) query from user input
  const [rawQuery, setRawQuery] = useState<string>(initialQuery);
  // Debounced query that drives actual matching
  const [query, setDebouncedQuery] = useState<string>(initialQuery);
  // Index of the currently active match
  const [currentIndex, setCurrentIndex] = useState<number>(0);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Apply 300ms debounce when rawQuery changes (FR-020)
  useEffect(() => {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      setDebouncedQuery(rawQuery);
      // Reset navigation to first match when query changes
      setCurrentIndex(0);
    }, DEBOUNCE_CONFIG.searchInput);

    return () => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [rawQuery]);

  // Compute all matches whenever the debounced query or segments change
  const matches = useMemo<TranscriptSearchMatch[]>(() => {
    if (!query.trim()) {
      return [];
    }

    const lowerQuery = query.toLowerCase();
    const results: TranscriptSearchMatch[] = [];

    for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex++) {
      const segment = segments[segmentIndex];
      if (!segment) continue;

      const lowerText = segment.text.toLowerCase();
      let searchFrom = 0;

      while (searchFrom < lowerText.length) {
        const matchStart = lowerText.indexOf(lowerQuery, searchFrom);
        if (matchStart === -1) break;

        results.push({
          segmentIndex,
          startOffset: matchStart,
          length: lowerQuery.length,
        });

        // Advance past this match to find subsequent matches in same segment
        searchFrom = matchStart + lowerQuery.length;
      }
    }

    return results;
  }, [query, segments]);

  // Clamp currentIndex whenever matches array changes
  useEffect(() => {
    setCurrentIndex((prev) => {
      if (matches.length === 0) return 0;
      // Keep current position if still within bounds
      return prev < matches.length ? prev : 0;
    });
  }, [matches]);

  /**
   * Navigate to the next match with wraparound (last→first).
   */
  const next = useCallback(() => {
    if (matches.length === 0) return;
    setCurrentIndex((prev) => (prev + 1) % matches.length);
  }, [matches.length]);

  /**
   * Navigate to the previous match with wraparound (first→last).
   */
  const prev = useCallback(() => {
    if (matches.length === 0) return;
    setCurrentIndex((prev) => (prev - 1 + matches.length) % matches.length);
  }, [matches.length]);

  /**
   * Set a new search query. The actual search is debounced by 300ms.
   */
  const setQuery = useCallback((q: string) => {
    setRawQuery(q);
  }, []);

  /**
   * Clear the search and reset all navigation state immediately (no debounce).
   */
  const reset = useCallback(() => {
    // Cancel any pending debounce
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    setRawQuery("");
    setDebouncedQuery("");
    setCurrentIndex(0);
  }, []);

  return {
    matches,
    currentIndex,
    total: matches.length,
    next,
    prev,
    query,
    setQuery,
    reset,
  };
}
