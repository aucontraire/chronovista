/**
 * SearchResultList Component
 *
 * Implements FR-003, FR-009, FR-010, FR-019, FR-032: Display list of search results with infinite scroll.
 *
 * Features:
 * - Container for SearchResult components
 * - Results pre-sorted by backend (video upload date desc, segment time asc)
 * - Passes query terms to each result for highlighting
 * - Infinite scroll with Intersection Observer (FR-009)
 * - Position preservation during scroll (FR-010)
 * - CSS content-visibility optimization for large result sets (FR-032)
 * - Loading and end-of-results indicators
 * - Maximum 1000 results cap with warning
 *
 * @see FR-003: Search result display
 * @see FR-009: Infinite scroll with Intersection Observer
 * @see FR-010: Position preservation (no jump/flicker)
 * @see FR-019: Sort by video upload date (descending) then segment time (ascending)
 * @see FR-032: Large result set handling
 */

import { useEffect, useRef } from "react";
import { SearchResultSegment } from "../types/search";
import { SearchResult } from "./SearchResult";
import { SEARCH_CONFIG } from "../config/search";

interface SearchResultListProps {
  /** Array of search result segments (already sorted by backend) */
  results: SearchResultSegment[];
  /** Query terms for highlighting in each result */
  queryTerms: string[];
  /** Whether initial search is loading */
  isLoading?: boolean;
  /** Whether next page is being fetched */
  isFetchingNextPage?: boolean;
  /** Whether more pages are available */
  hasNextPage?: boolean;
  /** Function to fetch next page of results */
  fetchNextPage?: () => void;
}

/**
 * Container component for displaying a list of search results with infinite scroll.
 *
 * Results are already sorted by the backend according to FR-019:
 * - Primary sort: video upload date (descending)
 * - Secondary sort: segment time (ascending)
 *
 * Infinite scroll triggers when sentinel element enters viewport (400px margin).
 * Implements CSS content-visibility optimization for result sets > 200 items.
 * Hard cap at 1000 results to prevent performance issues.
 *
 * @example
 * ```tsx
 * <SearchResultList
 *   results={searchResults}
 *   queryTerms={["machine", "learning"]}
 *   hasNextPage={hasNextPage}
 *   isFetchingNextPage={isFetchingNextPage}
 *   fetchNextPage={fetchNextPage}
 * />
 * ```
 */
export function SearchResultList({
  results,
  queryTerms,
  isLoading = false,
  isFetchingNextPage = false,
  hasNextPage = false,
  fetchNextPage,
}: SearchResultListProps) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Cap results at MAX_ACCUMULATED_RESULTS (FR-032)
  const displayedResults = results.slice(0, SEARCH_CONFIG.MAX_ACCUMULATED_RESULTS);
  const isAtMaxResults = results.length >= SEARCH_CONFIG.MAX_ACCUMULATED_RESULTS;
  const isApproachingMax = results.length >= 950 && results.length < SEARCH_CONFIG.MAX_ACCUMULATED_RESULTS;

  // Apply CSS optimization for large result sets (FR-032)
  const shouldOptimize = results.length > SEARCH_CONFIG.VIRTUALIZATION_THRESHOLD;

  // Set up Intersection Observer for infinite scroll (FR-009, T034, T035)
  useEffect(() => {
    // Only set up observer if there's a next page and fetchNextPage is provided
    if (!hasNextPage || !fetchNextPage || !sentinelRef.current) {
      return;
    }

    const sentinel = sentinelRef.current;

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;

        // Fetch next page when sentinel enters viewport and not already fetching (T035)
        if (entry?.isIntersecting && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      {
        root: null, // Use viewport as root
        rootMargin: SEARCH_CONFIG.SCROLL_TRIGGER_MARGIN, // Trigger 400px before visible
        threshold: SEARCH_CONFIG.SCROLL_TRIGGER_THRESHOLD, // Trigger immediately
      }
    );

    observer.observe(sentinel);

    // Cleanup on unmount or when dependencies change
    return () => {
      observer.disconnect();
    };
  }, [hasNextPage, fetchNextPage, isFetchingNextPage]);

  return (
    <div
      aria-live="polite"
      className="space-y-4"
    >
      {/* Search results (T038: stable keys for position preservation) */}
      {displayedResults.map((result) => (
        <div
          key={result.segment_id}
          className={shouldOptimize ? "result-item-optimized" : undefined}
          style={
            shouldOptimize
              ? {
                  contentVisibility: "auto",
                  containIntrinsicSize: "0 120px",
                }
              : undefined
          }
        >
          <SearchResult segment={result} queryTerms={queryTerms} />
        </div>
      ))}

      {/* Approaching max results warning (FR-032) */}
      {isApproachingMax && !isAtMaxResults && (
        <div
          className="p-4 border border-yellow-300 dark:border-yellow-700 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 text-center"
          role="status"
          aria-live="polite"
        >
          <p className="text-sm font-medium">
            Approaching the maximum of {SEARCH_CONFIG.MAX_ACCUMULATED_RESULTS}{" "}
            results. Consider refining your search.
          </p>
        </div>
      )}

      {/* Maximum results reached message (FR-032) */}
      {isAtMaxResults && (
        <div
          className="p-4 border border-red-300 dark:border-red-700 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 text-center"
          role="status"
          aria-live="polite"
        >
          <p className="text-sm font-medium">
            Maximum of {SEARCH_CONFIG.MAX_ACCUMULATED_RESULTS} results reached.
            Please refine your search to see more specific results.
          </p>
        </div>
      )}

      {/* Loading indicator (T036) */}
      {isFetchingNextPage && hasNextPage && !isAtMaxResults && (
        <div className="flex items-center justify-center py-8 text-gray-600 dark:text-gray-400">
          <div
            className="flex items-center gap-3"
            role="status"
            aria-live="polite"
          >
            <svg
              className="animate-spin h-5 w-5 text-blue-600 dark:text-blue-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <span className="text-sm font-medium">Loading more results...</span>
          </div>
        </div>
      )}

      {/* Sentinel element for infinite scroll (T034) */}
      {hasNextPage && !isFetchingNextPage && !isAtMaxResults && (
        <div
          ref={sentinelRef}
          data-testid="infinite-scroll-sentinel"
          className="h-px"
          aria-hidden="true"
        />
      )}

      {/* End of results indicator (T037) */}
      {!hasNextPage && results.length > 0 && !isAtMaxResults && (
        <div className="py-8 text-center text-gray-500 dark:text-gray-400">
          <p className="text-sm font-medium" role="status" aria-live="polite">
            End of results
          </p>
        </div>
      )}
    </div>
  );
}
