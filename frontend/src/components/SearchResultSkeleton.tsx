/**
 * SearchResultSkeleton Component
 *
 * Displays animated skeleton placeholders during search loading states.
 * Matches SearchResult card layout for consistent visual transition.
 *
 * @see FR-014 in spec.md
 */

import { SEARCH_CONFIG } from '../config/search';

interface SearchResultSkeletonProps {
  /** Number of skeleton cards to display (default: 8) */
  count?: number;
}

/**
 * Renders skeleton loading placeholders for search results.
 *
 * Features:
 * - Pulse animation for visual feedback
 * - Matches SearchResult card dimensions
 * - ARIA live region for screen reader updates
 * - Configurable skeleton count
 *
 * Accessibility:
 * - role="status" announces loading state
 * - aria-live="polite" for non-intrusive updates
 * - Individual cards hidden from screen readers (aria-hidden="true")
 * - Screen-reader-only text provides context
 *
 * @example
 * ```tsx
 * {isLoading && <SearchResultSkeleton count={8} />}
 * ```
 */
export function SearchResultSkeleton({
  count = SEARCH_CONFIG.SKELETON_COUNT,
}: SearchResultSkeletonProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading search results"
      className="space-y-4"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="animate-pulse space-y-3 rounded-lg border border-gray-200 bg-white p-4"
        >
          {/* Video Title - 2 lines */}
          <div className="space-y-2">
            <div className="h-5 w-3/4 rounded bg-gray-200" />
            <div className="h-5 w-1/2 rounded bg-gray-200" />
          </div>

          {/* Channel + Metadata Row */}
          <div className="flex items-center gap-2">
            <div className="h-4 w-32 rounded bg-gray-200" />
            <div className="h-1 w-1 rounded-full bg-gray-300" />
            <div className="h-4 w-20 rounded bg-gray-200" />
          </div>

          {/* Timestamp Range */}
          <div className="h-4 w-24 rounded bg-gray-200" />

          {/* Segment Text - 3 lines */}
          <div className="space-y-2 pt-2">
            <div className="h-4 w-full rounded bg-gray-200" />
            <div className="h-4 w-full rounded bg-gray-200" />
            <div className="h-4 w-2/3 rounded bg-gray-200" />
          </div>

          {/* Match count + button row */}
          <div className="flex items-center justify-between pt-2">
            <div className="h-4 w-16 rounded bg-gray-200" />
            <div className="h-8 w-20 rounded bg-gray-200" />
          </div>
        </div>
      ))}

      {/* Screen reader only text */}
      <span className="sr-only">Searching transcripts...</span>
    </div>
  );
}
