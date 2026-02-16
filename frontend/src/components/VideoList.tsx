/**
 * VideoList component displays the list of videos with all states.
 */

import { useVideos } from "../hooks/useVideos";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { VideoCard } from "./VideoCard";

/**
 * Pagination status component showing "X of Y videos".
 */
interface PaginationStatusProps {
  loadedCount: number;
  total: number | null;
}

function PaginationStatus({ loadedCount, total }: PaginationStatusProps) {
  if (total === null) {
    return (
      <p className="text-sm text-gray-500 text-center py-2">
        Showing {loadedCount} video{loadedCount !== 1 ? "s" : ""}
      </p>
    );
  }

  return (
    <p className="text-sm text-gray-500 text-center py-2">
      Showing {loadedCount} of {total} video{total !== 1 ? "s" : ""}
    </p>
  );
}

/**
 * Load More button with disabled state during loading.
 */
interface LoadMoreButtonProps {
  onClick: () => void;
  isLoading: boolean;
  disabled: boolean;
}

function LoadMoreButton({ onClick, isLoading, disabled }: LoadMoreButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full py-3 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
      aria-busy={isLoading}
    >
      {isLoading ? (
        <span className="flex items-center justify-center gap-2">
          <svg
            className="animate-spin h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          Loading...
        </span>
      ) : (
        "Load More"
      )}
    </button>
  );
}

/**
 * Message shown when all videos have been loaded.
 */
interface AllLoadedMessageProps {
  total: number;
}

function AllLoadedMessage({ total }: AllLoadedMessageProps) {
  return (
    <p className="text-sm text-gray-500 text-center py-4 border-t border-gray-200">
      All {total} video{total !== 1 ? "s" : ""} loaded
    </p>
  );
}

interface VideoListProps {
  /** Filter by tags (OR logic) */
  tags?: string[];
  /** Filter by category ID */
  category?: string | null;
  /** Filter by topic IDs (OR logic) */
  topicIds?: string[];
  /** Include unavailable content (T031, FR-021) */
  includeUnavailable?: boolean;
}

/**
 * VideoList displays videos with loading, error, and empty states.
 * Includes infinite scroll with Intersection Observer and fallback Load More button.
 */
export function VideoList({ tags = [], category = null, topicIds = [], includeUnavailable = true }: VideoListProps = {}) {
  const {
    videos,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    retry,
    loadMoreRef,
  } = useVideos({ tags, category, topicIds, includeUnavailable });

  // Initial loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingState count={3} />
      </div>
    );
  }

  // Error state
  if (isError) {
    return <ErrorState error={error} onRetry={retry} />;
  }

  // Empty state
  if (videos.length === 0) {
    return <EmptyState />;
  }

  // Videos list with pagination
  return (
    <div className="space-y-4">
      {/* Pagination Status - Top */}
      <PaginationStatus loadedCount={loadedCount} total={total} />

      {/* Video Cards */}
      <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" role="list" aria-label="Video list">
        {videos.map((video) => (
          <li key={video.video_id}>
            <VideoCard video={video} />
          </li>
        ))}
      </ul>

      {/* Loading more indicator */}
      {isFetchingNextPage && (
        <LoadingState count={2} />
      )}

      {/* Intersection Observer Trigger Element */}
      <div
        ref={loadMoreRef}
        className="h-4"
        aria-hidden="true"
      />

      {/* Load More Button (fallback) */}
      {hasNextPage && !isFetchingNextPage && (
        <LoadMoreButton
          onClick={fetchNextPage}
          isLoading={isFetchingNextPage}
          disabled={isFetchingNextPage}
        />
      )}

      {/* All Loaded Message */}
      {!hasNextPage && total !== null && total > 0 && (
        <AllLoadedMessage total={total} />
      )}
    </div>
  );
}
