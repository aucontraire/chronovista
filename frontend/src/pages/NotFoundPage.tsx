/**
 * NotFoundPage component - displays a 404 error message.
 */

import { Link } from "react-router-dom";

/**
 * Warning/exclamation icon for the 404 page.
 */
function WarningIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
      />
    </svg>
  );
}

/**
 * NotFoundPage displays a 404 error message with a link back to the videos page.
 *
 * Features:
 * - Centered content layout
 * - Warning icon visual indicator
 * - "Page Not Found" heading
 * - Descriptive message
 * - Prominent link back to /videos using react-router-dom Link
 */
export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] p-8">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md">
        {/* 404 Badge */}
        <div className="mb-4">
          <span className="text-6xl font-bold text-slate-300">404</span>
        </div>

        {/* Warning Icon */}
        <div className="mx-auto w-16 h-16 mb-6 text-slate-400 bg-slate-100 rounded-full p-4">
          <WarningIcon className="w-full h-full" />
        </div>

        {/* Heading */}
        <h2 className="text-2xl font-bold text-slate-900 mb-3">
          Page Not Found
        </h2>

        {/* Description */}
        <p className="text-slate-600">
          The page you're looking for doesn't exist.
        </p>

        {/* Navigation Link */}
        <Link
          to="/videos"
          className="inline-block mt-6 px-6 py-3 bg-slate-900 text-white font-semibold rounded-lg hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
        >
          Go to Videos
        </Link>
      </div>
    </div>
  );
}
