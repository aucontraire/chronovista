/**
 * EmptyState component displays when no videos are available.
 */

/**
 * EmptyState shows a friendly message when the video list is empty.
 * Includes instructions for syncing videos using the CLI.
 */
export function EmptyState() {
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[400px]"
      role="status"
      aria-label="No videos available"
    >
      {/* Video/Folder Icon */}
      <div className="mx-auto w-20 h-20 mb-6 text-gray-400 bg-gray-100 rounded-full p-4">
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
            d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
          />
        </svg>
      </div>

      {/* Heading */}
      <h3 className="text-xl font-semibold text-gray-900 mb-3">No videos yet</h3>

      {/* Instructions */}
      <p className="text-gray-600 mb-6 max-w-sm">
        Get started by syncing your YouTube data using the CLI.
      </p>

      {/* CLI Command */}
      <div className="inline-block mb-6">
        <code className="bg-gray-900 text-green-400 px-5 py-3 rounded-lg font-mono text-sm shadow-md block">
          $ chronovista sync
        </code>
      </div>

      {/* Additional Help */}
      <p className="text-sm text-gray-500 max-w-xs">
        This will fetch your YouTube videos, channels, and transcripts.
      </p>
    </div>
  );
}
