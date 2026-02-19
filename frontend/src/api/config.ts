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
 * Classifies an error into a specific error type.
 */
function classifyError(error: unknown, response?: Response): ApiErrorType {
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return "network";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "timeout";
  }
  if (response && response.status >= 500) {
    return "server";
  }
  if (response && response.status >= 400) {
    return "server";
  }
  return "unknown";
}

/**
 * Creates an ApiError from a caught error or response.
 */
function createApiError(error: unknown, response?: Response): ApiError {
  const type = classifyError(error, response);

  const messages: Record<ApiErrorType, string> = {
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
 * Extended fetch options that include an optional timeout override.
 */
export interface ApiFetchOptions extends RequestInit {
  /** Timeout in milliseconds. Defaults to API_TIMEOUT (10s). */
  timeout?: number;
}

/**
 * Fetch wrapper with timeout and error handling.
 *
 * @param endpoint - API endpoint path (without base URL)
 * @param options - Fetch options with optional timeout override
 * @returns Parsed JSON response
 * @throws ApiError on failure
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { timeout, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout ?? API_TIMEOUT);

  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
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
