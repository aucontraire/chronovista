/**
 * SearchErrorState Component
 *
 * Implements FR-016: Error state display for search failures.
 *
 * FR-003: Authentication errors (401/403) are handled globally by the
 * QueryCache interceptor in `src/lib/queryClient.ts`, which calls
 * `setAuthError()` and causes AppShell to render `AuthErrorState` instead of
 * this component. This component therefore only renders generic (non-auth)
 * errors and no longer contains per-component 401/403 handling.
 *
 * @see FR-016: Display error state with retry option
 * @see FR-003: Global auth interception — no per-page 401 handling
 */

interface SearchErrorStateProps {
  /** Optional custom error message (defaults to generic message) */
  message?: string;
  /** Callback to retry the failed search */
  onRetry: () => void;
}

/**
 * Error state component for search failures (non-auth errors only).
 *
 * Auth errors are intercepted globally via the QueryCache and rendered by
 * AppShell as `AuthErrorState`. This component handles network failures,
 * server errors, and other unexpected problems with a retry button.
 *
 * @example
 * ```tsx
 * <SearchErrorState
 *   message="Network error: Unable to reach server"
 *   onRetry={() => refetch()}
 * />
 * ```
 */
export function SearchErrorState({
  message = "Something went wrong. Please try again.",
  onRetry,
}: SearchErrorStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center"
      role="alert"
      aria-live="assertive"
    >
      {/* Error icon */}
      <div className="w-16 h-16 mb-4 rounded-full bg-red-100 flex items-center justify-center">
        <svg
          className="w-8 h-8 text-red-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      {/* Error message */}
      <h2 className="text-xl font-semibold text-gray-900 mb-2">
        Error loading search results
      </h2>
      <p className="text-gray-600 max-w-md mb-6">
        {message}
      </p>

      {/* Retry button */}
      <button
        type="button"
        onClick={onRetry}
        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        aria-label="Retry search"
      >
        Try Again
      </button>
    </div>
  );
}
