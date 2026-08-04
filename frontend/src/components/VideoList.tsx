/**
 * VideoList component displays the list of videos with all states.
 */

import { useVideos } from "../hooks/useVideos";
import type { ApiError } from "../types/video";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { VideoCard } from "./VideoCard";
import type { VideoSortField, SortOrder } from "../types/filters";

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
  /**
   * Filter by legacy raw tags (OR logic).
   * @deprecated Use `canonicalTags` instead for canonical tag filtering.
   */
  tags?: string[];
  /** Filter by canonical tag normalized forms (OR logic, Feature 030) */
  canonicalTags?: string[];
  /** Filter by category ID */
  category?: string | null;
  /** Filter by topic IDs (OR logic) */
  topicIds?: string[];
  /** Include unavailable content (T031, FR-021) */
  includeUnavailable?: boolean;
  /** Sort field (Feature 027) */
  sortBy?: VideoSortField;
  /** Sort order (Feature 027) */
  sortOrder?: SortOrder;
  /** Filter to liked videos only (Feature 027) */
  likedOnly?: boolean;
  /** Filter to videos with transcripts (Feature 027) */
  hasTranscript?: boolean;
  /** Filter to videos saved in a curated playlist and never watched */
  savedUnwatched?: boolean;
  /** Required entity UUIDs — AND logic across all of them (Feature 062) */
  entityIds?: string[];
  /** Excluded entity UUIDs — a video mentioning ANY is removed (Feature 062) */
  excludedEntityIds?: string[];
  /** Restrict which mentions qualify; omit for all three sources (Feature 062) */
  minEvidence?: "transcript" | undefined;
}

/**
 * VideoList displays videos with loading, error, and empty states.
 * Includes infinite scroll with Intersection Observer and fallback Load More button.
 */
export function VideoList({
  entityIds = [],
  excludedEntityIds = [],
  minEvidence,
  tags = [],
  canonicalTags = [],
  category = null,
  topicIds = [],
  includeUnavailable = true,
  sortBy,
  sortOrder,
  likedOnly = false,
  hasTranscript,
  savedUnwatched,
}: VideoListProps = {}) {
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
  } = useVideos({
    entityIds,
    excludedEntityIds,
    ...(minEvidence !== undefined && { minEvidence }),
    tags,
    canonicalTags,
    category,
    topicIds,
    includeUnavailable,
    likedOnly,
    ...(sortBy !== undefined && { sortBy }),
    ...(sortOrder !== undefined && { sortOrder }),
    ...(hasTranscript !== undefined && { hasTranscript }),
    ...(savedUnwatched !== undefined && { savedUnwatched }),
  });

  // Initial loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingState count={3} />
      </div>
    );
  }

  // A 4xx rejection is the user's filter being unacceptable, not the page
  // being broken. FR-016a: present it as a RECOVERABLE state that names the
  // offending value and leaves the rest of the filter intact, rather than the
  // retry-oriented ErrorState, which offers an action that cannot help --
  // retrying an invalid request just fails again.
  // `error` is typed `unknown` by the hook, so narrow before reading it
  // rather than asserting a shape the runtime may not have.
  const apiError: ApiError | null =
    error !== null && typeof error === "object" ? (error as ApiError) : null;
  const rejectionStatus = apiError?.status;
  const isRejection =
    isError &&
    rejectionStatus !== undefined &&
    rejectionStatus >= 400 &&
    rejectionStatus < 500;

  if (isRejection) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-amber-200 bg-amber-50 p-6"
        data-testid="filter-rejected"
      >
        <h3 className="text-sm font-semibold text-amber-900">
          This filter can&apos;t be applied
        </h3>
        <p className="mt-1 text-sm text-amber-800">
          {apiError?.detail ??
            "One of the active filters was rejected. Remove it to continue."}
        </p>
        <p className="mt-2 text-xs text-amber-700">
          Your other filters are still active — remove the offending one from
          the filter pills above.
        </p>
      </div>
    );
  }

  // Error state — genuine failures, where retrying is a sensible offer.
  if (isError) {
    return <ErrorState error={error} onRetry={retry} />;
  }

  // Empty state. FR-012 requires the filtered-empty case to be
  // distinguishable from an error AND from an unfiltered library: "no videos
  // at all" and "no videos matching these entities" are different facts and
  // suggest different next actions.
  if (videos.length === 0) {
    const hasEntityFilter =
      entityIds.length > 0 || excludedEntityIds.length > 0;
    if (hasEntityFilter) {
      return (
        <div
          role="status"
          className="rounded-lg border border-slate-200 bg-white p-12 text-center"
          data-testid="empty-intersection"
        >
          <h3 className="text-sm font-semibold text-slate-800">
            No videos mention all of these entities
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {entityIds.length > 1
              ? "Each entity you add narrows the result. Try removing one."
              : "Try a different entity, or widen the evidence scope."}
          </p>
          {minEvidence === "transcript" && (
            <p className="mt-2 text-xs text-slate-500">
              Transcript-only is active — title and description mentions are
              being excluded.
            </p>
          )}
        </div>
      );
    }
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
