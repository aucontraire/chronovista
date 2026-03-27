/**
 * TanStack Query client configuration with retry logic and global auth error state.
 *
 * FR-001: Classify HTTP 401/403 as auth errors and expose a global signal so
 *         AppShell (and any other consumer) can render a session-expired banner.
 * FR-006: Cancelled requests (AbortError) must NOT trigger error states or retries.
 * FR-007: Retry only transient errors: network errors (fetch TypeError), HTTP 5xx, 408, 429.
 * FR-008: Never retry 4xx errors (except 408/429) or mutations.
 * FR-020: Implements automatic retry with exponential backoff:
 *         - Up to 3 retry attempts
 *         - Exponential backoff: 1s, 2s, 4s (capped at 30s)
 */

import { QueryCache, QueryClient } from "@tanstack/react-query";
import { isApiError } from "../api/config";

// ---------------------------------------------------------------------------
// Global auth error state (FR-001)
//
// This is a minimal reactive store compatible with React's useSyncExternalStore.
// It intentionally has no external dependency — a single boolean is sufficient
// since the only action is "session expired, please re-authenticate".
//
// Usage in a component:
//
//   import { useAuthErrorState } from "../lib/queryClient";
//   const isAuthError = useAuthErrorState();
//
// ---------------------------------------------------------------------------

type Listener = () => void;

let authErrorState = false;
const authErrorListeners = new Set<Listener>();

/**
 * Subscribe to auth error state changes (useSyncExternalStore contract).
 * Returns an unsubscribe function.
 */
export function subscribeToAuthError(listener: Listener): () => void {
  authErrorListeners.add(listener);
  return () => {
    authErrorListeners.delete(listener);
  };
}

/**
 * Returns a snapshot of the current auth error state
 * (useSyncExternalStore contract).
 */
export function getAuthErrorSnapshot(): boolean {
  return authErrorState;
}

/**
 * Marks the session as having an auth error.
 * Idempotent — calling it multiple times only notifies listeners once per
 * state transition (false → true).
 */
export function setAuthError(): void {
  if (!authErrorState) {
    authErrorState = true;
    authErrorListeners.forEach((listener) => listener());
  }
}

/**
 * Clears the auth error state (e.g., after the user re-authenticates or
 * dismisses the banner).
 * Idempotent — only notifies listeners on a true → false transition.
 */
export function clearAuthError(): void {
  if (authErrorState) {
    authErrorState = false;
    authErrorListeners.forEach((listener) => listener());
  }
}

// ---------------------------------------------------------------------------
// Retry logic (FR-006, FR-007, FR-008)
// ---------------------------------------------------------------------------

/**
 * Determines if a failed request should be retried.
 *
 * Retry conditions (FR-007):
 * - Network failures (TypeError from fetch — no response at all)
 * - 5xx server errors
 * - 408 Request Timeout
 * - 429 Too Many Requests
 *
 * Do NOT retry (FR-006, FR-008):
 * - AbortError — the request was deliberately cancelled by the caller or
 *   by the timeout guard; retrying a cancelled request is never correct.
 * - 4xx client errors (except 408, 429)
 * - Auth errors (401, 403) — re-auth is needed, not a retry
 * - Successful responses (2xx, 3xx)
 *
 * @param failureCount - Number of times the request has already failed
 * @param error - The error that occurred
 * @returns true if the request should be retried, false otherwise
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  // Don't retry if we've already tried 3 times
  if (failureCount >= 3) {
    return false;
  }

  // FR-006: AbortError means the request was deliberately cancelled (either
  // by the caller's signal or by the internal timeout controller).  In both
  // cases we must NOT retry — the cancellation was intentional.
  if (error instanceof DOMException && error.name === "AbortError") {
    return false;
  }

  // Network errors should be retried (no response object at all)
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return true;
  }

  // For structured ApiError objects check the status code
  if (isApiError(error)) {
    const { status, type } = error;

    // FR-001: Auth errors require re-authentication, not a retry.
    if (type === "auth") {
      return false;
    }

    if (typeof status === "number") {
      // Retry 5xx server errors (FR-007)
      if (status >= 500) {
        return true;
      }

      // Retry specific transient 4xx errors (FR-007)
      if (status === 408 || status === 429) {
        return true;
      }

      // FR-008: Don't retry any other 4xx (bad request, not found, etc.)
      if (status >= 400 && status < 500) {
        return false;
      }
    }
  }

  // For plain objects with a status property (belt-and-suspenders)
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status?: number }).status;

    if (typeof status === "number") {
      if (status >= 500) return true;
      if (status === 408 || status === 429) return true;
      if (status >= 400 && status < 500) return false;
    }
  }

  // For unknown error types, retry to be safe
  return true;
}

// ---------------------------------------------------------------------------
// QueryClient (FR-001, FR-020)
// ---------------------------------------------------------------------------

/**
 * QueryClient with optimized defaults for YouTube data management.
 *
 * Configuration:
 * - FR-001: QueryCache.onError detects auth errors and sets global state
 * - FR-020: Automatic retry with exponential backoff (max 3 attempts)
 * - Data stays fresh for 5 minutes (YouTube data doesn't change frequently)
 * - Inactive data cached for 10 minutes
 * - Refetch on window focus to catch updates
 * - Refetch on network reconnect
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    /**
     * FR-001: Intercept every query error at the cache level.
     * If the error is an auth error (401/403), set the global auth error
     * state so that AppShell can render a session-expired banner without
     * every individual query needing its own error handler.
     */
    onError(error) {
      if (isApiError(error) && error.type === "auth") {
        setAuthError();
      }
    },
  }),
  defaultOptions: {
    queries: {
      // FR-020: Retry failed requests up to 3 times (only for network/5xx/408/429)
      retry: shouldRetry,
      // FR-020: Exponential backoff - 1s, 2s, 4s (max 30s)
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      // Data is considered fresh for 5 minutes
      staleTime: 5 * 60 * 1000,
      // Keep inactive data in cache for 10 minutes
      gcTime: 10 * 60 * 1000,
      // Refetch on window focus (useful for stale data)
      refetchOnWindowFocus: true,
      // Refetch on network reconnect
      refetchOnReconnect: true,
    },
  },
});
