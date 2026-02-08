/**
 * SearchErrorState Component
 *
 * Implements FR-016, FR-024, EC-011-EC-016: Error state display for search failures.
 *
 * Features:
 * - Friendly error message
 * - Retry button to allow recovery
 * - Authentication error detection (401/403)
 * - Session expired handling with refresh button
 * - Accessible error announcement
 *
 * @see FR-016: Display error state with retry option
 * @see FR-024: Authentication error handling
 * @see EC-011-EC-016: Session expiration and recovery
 */

import type { ApiError } from "../types/video";

interface SearchErrorStateProps {
  /** Optional custom error message (defaults to generic message) */
  message?: string;
  /** Callback to retry the failed search */
  onRetry: () => void;
  /** Optional HTTP status code for authentication detection */
  status?: number;
  /** Optional full error object for detailed error handling */
  error?: unknown;
}

/**
 * Error state component for search failures.
 *
 * Displays when a search request fails due to network issues, server errors,
 * authentication issues, or other unexpected problems. Provides appropriate
 * recovery mechanisms based on error type.
 *
 * @example
 * ```tsx
 * // Generic error
 * <SearchErrorState
 *   message="Network error: Unable to reach server"
 *   onRetry={() => refetch()}
 * />
 *
 * // Authentication error
 * <SearchErrorState
 *   status={401}
 *   onRetry={() => refetch()}
 * />
 * ```
 */
export function SearchErrorState({
  message = "Something went wrong. Please try again.",
  onRetry,
  status,
  error,
}: SearchErrorStateProps) {
  // EC-011-EC-016: Detect authentication errors (401/403)
  const isAuthError = status === 401 || status === 403;

  // Extract status from ApiError if available
  const apiError = error as ApiError | undefined;
  const effectiveStatus = status ?? apiError?.status;
  const isAuthErrorFromApi = effectiveStatus === 401 || effectiveStatus === 403;

  const showAuthError = isAuthError || isAuthErrorFromApi;

  if (showAuthError) {
    return (
      <div
        className="flex flex-col items-center justify-center py-16 px-4 text-center"
        role="alert"
        aria-live="assertive"
      >
        {/* Lock icon for auth errors */}
        <div className="w-16 h-16 mb-4 rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
          <svg
            className="w-8 h-8 text-yellow-600 dark:text-yellow-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>

        {/* Auth error message (EC-011) */}
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Session expired
        </h2>
        <p className="text-gray-600 dark:text-gray-400 max-w-md mb-2">
          Session expired. Please refresh the page.
        </p>

        {/* Secondary help text (EC-015) */}
        <p className="text-sm text-gray-500 dark:text-gray-500 max-w-md mb-6">
          Or run <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono text-xs">chronovista auth login</code> in your terminal
        </p>

        {/* Refresh button (EC-012, EC-013) */}
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          aria-label="Refresh page to re-authenticate"
        >
          Refresh Page
        </button>
      </div>
    );
  }

  // Generic error display
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center"
      role="alert"
      aria-live="assertive"
    >
      {/* Error icon */}
      <div className="w-16 h-16 mb-4 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
        <svg
          className="w-8 h-8 text-red-600 dark:text-red-400"
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
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
        Error loading search results
      </h2>
      <p className="text-gray-600 dark:text-gray-400 max-w-md mb-6">
        {message}
      </p>

      {/* Retry button */}
      <button
        onClick={onRetry}
        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        aria-label="Retry search"
      >
        Try Again
      </button>
    </div>
  );
}
