/**
 * AuthErrorState component — full-page session-expired overlay.
 *
 * Implements:
 * - FR-002: Consistent "Session Expired" UI shown on any page where a 401/403
 *           is detected by the global QueryCache interceptor.
 * - FR-022: Focus moves to the "Refresh Page" button on mount so keyboard
 *           and screen-reader users are immediately aware of the error state.
 * - NFR-001: 44×44 px minimum touch target on the action button.
 */

import { useEffect, useRef } from "react";

/**
 * AuthErrorState renders a centered session-expired message with a
 * "Refresh Page" button that auto-receives focus on mount (FR-022).
 *
 * Place this as a full-page replacement rather than an inline error so that
 * the user always sees the same UI regardless of which page triggered the
 * auth failure (FR-002).
 *
 * @example
 * ```tsx
 * // Inside AppShell, conditionally replacing <Outlet />
 * if (isAuthError) return <AuthErrorState />;
 * ```
 */
export function AuthErrorState() {
  const buttonRef = useRef<HTMLButtonElement>(null);

  // FR-022: Move focus to the action button when this state is rendered.
  // useEffect runs after paint so the element is guaranteed to be in the DOM.
  useEffect(() => {
    buttonRef.current?.focus();
  }, []);

  return (
    <div
      className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      {/* Lock icon */}
      <div className="mx-auto w-16 h-16 mb-5 text-amber-600 bg-amber-100 rounded-full p-3 flex items-center justify-center">
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
            d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
          />
        </svg>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-amber-800 uppercase tracking-wider mb-2">
        Session Expired
      </p>

      {/* Primary message */}
      <h2 className="text-xl font-bold text-slate-900 mb-3">
        Your authentication token has expired
      </h2>

      {/* Help text */}
      <p className="text-slate-600 max-w-sm mb-2">
        Please refresh the page to restore your session.
      </p>

      {/* Terminal help text */}
      <p className="text-sm text-slate-500 max-w-sm mb-8">
        Or run{" "}
        <code className="px-1.5 py-0.5 bg-slate-100 rounded font-mono text-xs text-slate-700">
          chronovista auth login
        </code>{" "}
        in your terminal to re-authenticate.
      </p>

      {/* Refresh Page button — NFR-001: min 44×44px touch target */}
      <button
        ref={buttonRef}
        type="button"
        onClick={() => window.location.reload()}
        className="inline-flex items-center gap-2 px-6 py-3 min-h-[44px] bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-all duration-200"
        aria-label="Refresh page to re-authenticate"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="w-5 h-5"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
          />
        </svg>
        Refresh Page
      </button>
    </div>
  );
}
