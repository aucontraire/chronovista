/**
 * ErrorState component displays contextual error messages with retry option.
 */

import type { ApiErrorType } from "../types/video";
import { isApiError } from "../api/config";

interface ErrorStateProps {
  /** The error that occurred (alternative to message) */
  error?: unknown;
  /** Simple error message string (alternative to error object) */
  message?: string;
  /** Optional title for the error (defaults based on error type) */
  title?: string;
  /** Callback to retry the failed operation (optional) */
  onRetry?: () => void;
}

/**
 * Error messages for each error type.
 */
const errorMessages: Record<ApiErrorType, string> = {
  network:
    "Cannot reach the API server. Make sure the backend is running on port 8765.",
  timeout: "The server took too long to respond.",
  server: "Something went wrong on the server.",
  unknown: "An unexpected error occurred.",
};

/**
 * Gets a user-friendly error message from an error or returns provided message.
 */
function getErrorMessage(error: unknown | undefined, providedMessage?: string): string {
  // If message is explicitly provided, use it
  if (providedMessage) {
    return providedMessage;
  }

  // If no error object, use default
  if (!error) {
    return errorMessages.unknown;
  }

  if (isApiError(error)) {
    return errorMessages[error.type];
  }

  if (error instanceof Error) {
    // Check for common fetch errors
    if (error.message.includes("fetch") || error.message.includes("network")) {
      return errorMessages.network;
    }
    if (error.name === "AbortError" || error.message.includes("timeout")) {
      return errorMessages.timeout;
    }
    return error.message;
  }

  return errorMessages.unknown;
}

/**
 * Gets the error type from an error.
 */
function getErrorType(error: unknown | undefined): ApiErrorType {
  if (!error) {
    return "unknown";
  }

  if (isApiError(error)) {
    return error.type;
  }

  if (error instanceof Error) {
    if (error.message.includes("fetch") || error.message.includes("network")) {
      return "network";
    }
    if (error.name === "AbortError" || error.message.includes("timeout")) {
      return "timeout";
    }
  }

  return "unknown";
}

/**
 * ErrorState displays error messages with appropriate styling and retry button.
 * Supports both error object and simple message string interfaces.
 */
export function ErrorState({ error, message: providedMessage, title, onRetry }: ErrorStateProps) {
  const message = getErrorMessage(error, providedMessage);
  const errorType = getErrorType(error);

  // Use provided title or generate from error type
  const errorTitle = title || (() => {
    switch (errorType) {
      case "network":
        return "Connection Error";
      case "timeout":
        return "Timeout Error";
      case "server":
        return "Server Error";
      default:
        return "Error";
    }
  })();

  return (
    <div
      className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center"
      role="alert"
      aria-live="polite"
    >
      {/* Error Icon */}
      <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
          />
        </svg>
      </div>

      {/* Error Type Label */}
      <p className="text-sm font-semibold text-red-800 uppercase tracking-wider mb-2">
        {errorTitle}
      </p>

      {/* Error Message */}
      <p className="text-red-700 mb-8 max-w-md mx-auto">{message}</p>

      {/* Retry Button - only shown if onRetry callback provided */}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-5 h-5 mr-2"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
            />
          </svg>
          Try Again
        </button>
      )}
    </div>
  );
}
