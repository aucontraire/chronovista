/**
 * ChannelsPage component displays the list of channels with all states.
 */

import { ChannelCard } from "../components/ChannelCard";
import { useChannels } from "../hooks/useChannels";

/**
 * Skeleton card for channel loading state.
 * Matches ChannelCard dimensions with circular thumbnail placeholder.
 */
function ChannelSkeletonCard() {
  return (
    <div
      className="bg-white rounded-xl shadow-md border border-gray-100 p-5 animate-pulse"
      aria-hidden="true"
    >
      {/* Circular thumbnail skeleton */}
      <div className="mb-4 flex justify-center">
        <div className="w-22 h-22 bg-gray-200 rounded-full" />
      </div>

      {/* Channel name skeleton */}
      <div className="h-5 bg-gray-200 rounded-md w-3/4 mx-auto mb-3" />

      {/* Subscriber count skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-1/2 mx-auto mb-2" />

      {/* Video count skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-2/5 mx-auto" />
    </div>
  );
}

/**
 * Loading state specifically for channels with appropriate skeleton cards.
 */
function ChannelLoadingState({ count = 6 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
      role="status"
      aria-label="Loading channels"
      aria-live="polite"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <ChannelSkeletonCard key={index} />
      ))}
      <span className="sr-only">Loading channels...</span>
    </div>
  );
}

/**
 * Pagination status component showing "X of Y channels".
 */
interface PaginationStatusProps {
  loadedCount: number;
  total: number | null;
}

function PaginationStatus({ loadedCount, total }: PaginationStatusProps) {
  if (total === null) {
    return (
      <p className="text-sm text-gray-500 text-center py-2">
        Showing {loadedCount} channel{loadedCount !== 1 ? "s" : ""}
      </p>
    );
  }

  return (
    <p className="text-sm text-gray-500 text-center py-2">
      Showing {loadedCount} of {total} channel{total !== 1 ? "s" : ""}
    </p>
  );
}

/**
 * Message shown when all channels have been loaded.
 */
interface AllLoadedMessageProps {
  total: number;
}

function AllLoadedMessage({ total }: AllLoadedMessageProps) {
  return (
    <p className="text-sm text-gray-500 text-center py-4 border-t border-gray-200">
      All {total} channel{total !== 1 ? "s" : ""} loaded
    </p>
  );
}

/**
 * Empty state specific to channels.
 */
function ChannelEmptyState() {
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[400px]"
      role="status"
      aria-label="No channels available"
    >
      {/* Channel Icon */}
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
            d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z"
          />
        </svg>
      </div>

      {/* Heading */}
      <h3 className="text-xl font-semibold text-gray-900 mb-3">
        No channels yet
      </h3>

      {/* Instructions */}
      <p className="text-gray-600 mb-6 max-w-sm">
        You haven&apos;t synced any channels yet. Get started by syncing your YouTube data.
      </p>

      {/* CLI Command */}
      <div className="inline-block mb-6">
        <code className="bg-gray-900 text-green-400 px-5 py-3 rounded-lg font-mono text-sm shadow-md block">
          $ chronovista sync
        </code>
      </div>

      {/* Additional Help */}
      <p className="text-sm text-gray-500 max-w-xs">
        This will fetch your YouTube channels, videos, and transcripts.
      </p>
    </div>
  );
}

/**
 * ChannelsPage displays channels with loading, error, and empty states.
 * Includes infinite scroll with Intersection Observer.
 */
export function ChannelsPage() {
  const {
    channels,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    retry,
    loadMoreRef,
  } = useChannels();

  // Initial loading state
  if (isLoading) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
        <ChannelLoadingState count={8} />
      </main>
    );
  }

  // Error state (only if no channels loaded)
  if (isError && channels.length === 0) {
    // Extract error message if it's an API error object
    const errorMessage = typeof error === 'object' && error !== null && 'message' in error
      ? (error as { message: string }).message
      : 'An error occurred while loading channels';

    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
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

          {/* Error Title */}
          <p className="text-sm font-semibold text-red-800 uppercase tracking-wider mb-2">
            Could not load channels
          </p>

          {/* Error Message */}
          <p className="text-red-700 mb-8 max-w-md mx-auto">{errorMessage}</p>

          {/* Retry Button */}
          <button
            type="button"
            onClick={retry}
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
            Retry
          </button>
        </div>
      </main>
    );
  }

  // Empty state
  if (channels.length === 0) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
        <ChannelEmptyState />
      </main>
    );
  }

  // Channels list with pagination
  return (
    <main className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>

      <div className="space-y-4">
        {/* Pagination Status - Top (only show if more to load) */}
        {hasNextPage && <PaginationStatus loadedCount={loadedCount} total={total} />}

        {/* Channel Cards Grid */}
        <div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
          role="list"
          aria-label="Channel list"
        >
          {channels.map((channel) => (
            <div key={channel.channel_id} role="listitem">
              <ChannelCard channel={channel} />
            </div>
          ))}
        </div>

        {/* Loading more indicator */}
        {isFetchingNextPage && (
          <div aria-live="polite">
            <p className="text-sm text-gray-500 text-center py-2">Loading more channels...</p>
            <ChannelLoadingState count={4} />
          </div>
        )}

        {/* Inline error when channels are loaded but next page fails */}
        {isError && channels.length > 0 && (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-4 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-2">
              {typeof error === 'object' && error !== null && 'message' in error
                ? (error as { message: string }).message
                : 'Failed to load more channels'}
            </p>
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Intersection Observer Trigger Element */}
        {!isError && (
          <div
            ref={loadMoreRef}
            className="h-4"
            aria-hidden="true"
          />
        )}

        {/* All Loaded Message */}
        {!hasNextPage && !isError && total !== null && total > 0 && (
          <AllLoadedMessage total={total} />
        )}
      </div>
    </main>
  );
}
