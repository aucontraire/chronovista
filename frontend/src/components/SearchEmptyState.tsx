/**
 * SearchEmptyState Component
 *
 * Implements FR-015, FR-020: Empty state displays for search.
 *
 * Supports two modes:
 * 1. Initial hero state: Shown when no search query is entered
 * 2. No-results state: Shown when search returns no results
 *
 * @see FR-015: Display initial search prompt
 * @see FR-020: Display no-results message
 */

interface SearchEmptyStateProps {
  /** Display mode: initial hero or no-results */
  mode: "initial" | "no-results";
  /** Current search query (used in no-results mode) */
  query?: string;
  /** Callback when example search chip is clicked */
  onExampleClick?: (example: string) => void;
}

// Example search queries for the initial state
const EXAMPLE_QUERIES = [
  "machine learning",
  "react hooks",
  "typescript tutorial",
];

/**
 * Empty state component for search page.
 *
 * Displays contextual empty state based on whether the user has entered a query:
 * - Initial state: Encouraging prompt with example searches
 * - No-results state: Helpful message suggesting query refinement
 *
 * @example
 * ```tsx
 * // Initial state (no query)
 * <SearchEmptyState mode="initial" onExampleClick={setQuery} />
 *
 * // No-results state (query returned nothing)
 * <SearchEmptyState mode="no-results" query="xyz123" />
 * ```
 */
export function SearchEmptyState({
  mode,
  query,
  onExampleClick,
}: SearchEmptyStateProps) {
  if (mode === "no-results") {
    return (
      <div
        className="flex flex-col items-center justify-center py-16 px-4 text-center"
        role="status"
        aria-live="polite"
      >
        <svg
          className="w-16 h-16 text-gray-400 dark:text-gray-600 mb-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          No transcripts match your search
        </h2>
        <p className="text-gray-600 dark:text-gray-400 max-w-md">
          Try different keywords or check your spelling.
        </p>
        {query && (
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-500">
            Searched for: <span className="font-mono">&quot;{query}&quot;</span>
          </p>
        )}
      </div>
    );
  }

  // Initial hero state
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center"
      role="status"
    >
      {/* Search icon */}
      <div className="w-20 h-20 mb-6 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
        <svg
          className="w-10 h-10 text-blue-600 dark:text-blue-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>

      {/* Hero text */}
      <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
        Search across video transcripts
      </h2>
      <p className="text-gray-600 dark:text-gray-400 max-w-md mb-8">
        Enter keywords to find specific moments in videos
      </p>

      {/* Example search chips */}
      <div className="flex flex-wrap gap-2 justify-center">
        <span className="text-sm text-gray-500 dark:text-gray-500 mr-2">
          Try:
        </span>
        {EXAMPLE_QUERIES.map((example) => (
          <button
            key={example}
            onClick={() => onExampleClick?.(example)}
            className="px-3 py-1.5 text-sm font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            aria-label={`Search for ${example}`}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
