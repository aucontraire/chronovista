/**
 * API configuration and fetch wrapper for Chronovista.
 */

import type { ApiError, ApiErrorType } from "../types/video";

/**
 * Base URL for API requests.
 * Defaults to localhost:8765 for local development.
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8765/api/v1";

/**
 * Default timeout for API requests in milliseconds.
 */
export const API_TIMEOUT = 10000;

/**
 * Timeout for recovery operations in milliseconds.
 * Recovery can take up to 600s on the backend + 60s buffer.
 */
export const RECOVERY_TIMEOUT = 660000;

/**
 * Timeout for batch preview requests in milliseconds.
 * Unfiltered cross-segment scans can take ~12-15s on the backend.
 */
export const BATCH_PREVIEW_TIMEOUT = 30000;

/**
 * Classifies an error into a specific error type.
 *
 * FR-001: HTTP 401/403 responses are classified as "auth" — distinct from
 * generic server errors — so callers can trigger an auth recovery flow.
 */
function classifyError(error: unknown, response?: Response): ApiErrorType {
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return "network";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "timeout";
  }
  if (response) {
    // FR-001: Classify 401 Unauthorized and 403 Forbidden as auth errors.
    if (response.status === 401 || response.status === 403) {
      return "auth";
    }
    if (response.status >= 500) {
      return "server";
    }
    if (response.status >= 400) {
      return "server";
    }
  }
  return "unknown";
}

/**
 * Creates an ApiError from a caught error or response.
 */
function createApiError(error: unknown, response?: Response): ApiError {
  const type = classifyError(error, response);

  const messages: Record<ApiErrorType, string> = {
    auth: "You are not authorized to access this resource. Please check your credentials.",
    network:
      "Cannot reach the API server. Make sure the backend is running on port 8765.",
    timeout: "The server took too long to respond.",
    server: "Something went wrong on the server.",
    unknown: "An unexpected error occurred.",
  };

  return {
    type,
    message: messages[type],
    status: response?.status,
  };
}

/**
 * Extended fetch options that include an optional timeout override and an
 * optional external AbortSignal for caller-controlled cancellation.
 */
export interface ApiFetchOptions extends RequestInit {
  /** Timeout in milliseconds. Defaults to API_TIMEOUT (10s). */
  timeout?: number;
  /**
   * External AbortSignal supplied by the caller (e.g. from React's use() or
   * TanStack Query's signal). Combined with the internal timeout signal via
   * AbortSignal.any() so that whichever fires first wins.
   *
   * FR-006: When this signal fires, the resulting AbortError must NOT trigger
   * an error state or retry — the query was deliberately cancelled.
   */
  externalSignal?: AbortSignal;
}

/**
 * Fetch wrapper with timeout, cancellation, and error handling.
 *
 * @param endpoint - API endpoint path (without base URL)
 * @param options - Fetch options with optional timeout override and external signal
 * @returns Parsed JSON response
 * @throws ApiError on failure
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { timeout, externalSignal, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout ?? API_TIMEOUT);

  // Combine the internal timeout signal with any caller-supplied signal.
  // AbortSignal.any() resolves as soon as the first signal fires.
  // This lets TanStack Query (or React) cancel in-flight requests while the
  // timeout guard remains independently active.
  const combinedSignal: AbortSignal =
    externalSignal !== undefined
      ? AbortSignal.any([controller.signal, externalSignal])
      : controller.signal;

  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: combinedSignal,
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw createApiError(null, response);
    }

    const data = (await response.json()) as T;
    return data;
  } catch (error) {
    clearTimeout(timeoutId);

    // Re-throw if already an ApiError
    if (
      typeof error === "object" &&
      error !== null &&
      "type" in error &&
      "message" in error
    ) {
      throw error;
    }

    throw createApiError(error);
  }
}

/**
 * Type guard to check if an error is an ApiError.
 */
export function isApiError(error: unknown): error is ApiError {
  return (
    typeof error === "object" &&
    error !== null &&
    "type" in error &&
    "message" in error &&
    typeof (error as ApiError).type === "string" &&
    typeof (error as ApiError).message === "string"
  );
}
