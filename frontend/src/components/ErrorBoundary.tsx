/**
 * ErrorBoundary component catches JavaScript errors in child components.
 * Implements React's error boundary pattern per FR-017, FR-018, FR-019.
 */

import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  /** Child components to render */
  children: ReactNode;
}

interface ErrorBoundaryState {
  /** Whether an error has been caught */
  hasError: boolean;
  /** The error that was caught */
  error: Error | null;
}

/**
 * ErrorBoundary catches JavaScript errors anywhere in its child component tree
 * and displays a fallback UI instead of crashing the entire application.
 *
 * Features:
 * - Displays error message with details
 * - "Try Again" button to reset error state and retry
 * - Link to navigate back to /videos (safe landing page)
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary>
 *   <ComponentThatMightError />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render shows the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log error details for debugging
    console.error("ErrorBoundary caught an error:", error);
    console.error("Component stack:", errorInfo.componentStack);
  }

  /**
   * Reset error state to allow retry.
   */
  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  /**
   * Navigate to videos page (safe landing).
   */
  handleNavigateHome = (): void => {
    // Reset error state and navigate
    this.setState({ hasError: false, error: null });
    window.location.href = "/videos";
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-amber-50 p-4"
          role="alert"
          aria-live="assertive"
        >
          <div className="bg-white border border-red-200 rounded-xl shadow-lg p-8 max-w-md w-full text-center">
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

            {/* Error Title */}
            <h1 className="text-xl font-bold text-red-800 mb-2">
              Something went wrong
            </h1>

            {/* Error Message */}
            <p className="text-red-700 mb-4">
              {this.state.error?.message ?? "An unexpected error occurred."}
            </p>

            {/* Error Details (collapsed by default) */}
            {this.state.error && (
              <details className="text-left mb-6 text-sm">
                <summary className="cursor-pointer text-gray-600 hover:text-gray-800">
                  Technical details
                </summary>
                <pre className="mt-2 p-3 bg-gray-100 rounded-lg overflow-auto text-xs text-gray-700">
                  {this.state.error.stack ?? this.state.error.message}
                </pre>
              </details>
            )}

            {/* Action Buttons */}
            <div className="flex flex-col gap-3">
              {/* Try Again Button */}
              <button
                type="button"
                onClick={this.handleReset}
                className="inline-flex items-center justify-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
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

              {/* Link to Videos */}
              <a
                href="/videos"
                onClick={this.handleNavigateHome}
                className="inline-flex items-center justify-center px-6 py-3 bg-gray-100 text-gray-700 font-semibold rounded-lg hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-all duration-200"
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
                    d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
                  />
                </svg>
                Go to Videos
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
