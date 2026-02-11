import React from "react";

/**
 * Props for the SearchSection component.
 *
 * This component wraps search result sections with consistent header,
 * count display, loading state, and error handling.
 */
interface SearchSectionProps {
  /** Section title (e.g., "Video Titles", "Descriptions") */
  title: string;
  /** Total matching results (from API total_count) */
  totalCount: number;
  /** Number of results displayed (may be less than total due to cap) */
  displayedCount: number;
  /** Whether this section is currently loading */
  isLoading: boolean;
  /** Error object if the query failed */
  error: unknown;
  /** Callback to retry failed query */
  onRetry?: () => void;
  /** Loading text (e.g., "Searching titles...") */
  loadingText?: string;
  /** Child content (result cards) */
  children: React.ReactNode;
}

/**
 * SearchSection component for unified search result presentation.
 *
 * Implements FR-005, FR-006, FR-007, FR-013:
 * - Section header with count display
 * - "Showing X of Y" when results are capped
 * - Hidden when totalCount is 0 and not loading
 * - Loading state with spinner and descriptive text
 * - Error state with retry button (isolated per section)
 * - Semantic h2 heading for screen reader navigation
 *
 * @example
 * ```tsx
 * <SearchSection
 *   title="Video Titles"
 *   totalCount={75}
 *   displayedCount={50}
 *   isLoading={false}
 *   error={null}
 *   onRetry={refetch}
 *   loadingText="Searching titles..."
 * >
 *   {results.map(result => <ResultCard key={result.id} {...result} />)}
 * </SearchSection>
 * ```
 */
export function SearchSection({
  title,
  totalCount,
  displayedCount,
  isLoading,
  error,
  onRetry,
  loadingText = "Searching...",
  children,
}: SearchSectionProps) {
  // Hide section when no results and not loading
  if (!isLoading && !error && totalCount === 0) {
    return null;
  }

  // Build header text with count information
  const headerText =
    totalCount > displayedCount
      ? `${title} - Showing ${displayedCount} of ${totalCount}`
      : `${title} (${totalCount})`;

  return (
    <section aria-label={title} className="mb-8">
      {/* Section header - h2 for screen reader navigation (FR-013) */}
      <h2 className="text-lg font-bold text-slate-900 mb-4">
        {isLoading ? title : headerText}
      </h2>

      {/* Loading state - spinner with descriptive text (FR-006) */}
      {isLoading && (
        <div
          className="flex items-center gap-2 text-gray-500 dark:text-gray-400 py-4"
          role="status"
          aria-live="polite"
        >
          <svg
            className="animate-spin h-5 w-5"
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
          <span>{loadingText}</span>
        </div>
      )}

      {/* Error state - inline compact error with retry (FR-007) */}
      {!!error && !isLoading && (
        <div
          className="flex items-center gap-3 rounded-lg bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-400"
          role="alert"
          aria-live="assertive"
        >
          <span>Failed to load {title.toLowerCase()} results.</span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="ml-auto shrink-0 rounded-md bg-red-100 dark:bg-red-900/40 px-3 py-1.5 text-xs font-medium text-red-800 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/60 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
              type="button"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* Results content - only shown when not loading and no error */}
      {!isLoading && !!!error && children}
    </section>
  );
}
