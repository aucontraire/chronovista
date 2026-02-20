/**
 * PlaylistsPage component displays the list of playlists with all states.
 *
 * Features (CHK048-CHK064):
 * - CHK048: Filter tabs (All, YouTube-Linked, Local) with URL sync
 * - CHK049: Responsive grid layout (1/2/3/4 cols)
 * - CHK050: Playlist cards with proper metadata
 * - CHK051: Loading state with skeleton cards
 * - CHK052: Error state with retry
 * - CHK053: Empty state with filter-aware messaging
 * - CHK054: Infinite scroll support
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { PlaylistCard } from "../components/PlaylistCard";
import { PlaylistFilterTabs } from "../components/PlaylistFilterTabs";
import { SortDropdown } from "../components/SortDropdown";
import { ErrorState } from "../components/ErrorState";
import { usePlaylists } from "../hooks/usePlaylists";
import type {
  PlaylistFilterType,
  PlaylistSortField,
} from "../types/playlist";
import type { SortOrder, SortOption } from "../types/filters";

/**
 * Sort options for playlists (Feature 027).
 * Matches existing PlaylistSortDropdown behavior.
 */
const PLAYLIST_SORT_OPTIONS: SortOption<PlaylistSortField>[] = [
  { field: "title", label: "Title", defaultOrder: "asc" },
  { field: "created_at", label: "Date Added", defaultOrder: "desc" },
  { field: "video_count", label: "Video Count", defaultOrder: "desc" },
];

/**
 * Skeleton card for playlist loading state.
 * Matches PlaylistCard dimensions with content placeholders.
 */
function PlaylistSkeletonCard() {
  return (
    <div
      className="bg-white rounded-xl shadow-md border border-gray-100 p-6 animate-pulse"
      aria-hidden="true"
    >
      {/* Title skeleton (2 lines) */}
      <div className="mb-3 space-y-2">
        <div className="h-5 bg-gray-200 rounded-md w-full" />
        <div className="h-5 bg-gray-200 rounded-md w-3/4" />
      </div>

      {/* Video count skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-1/3 mb-3" />

      {/* Badges skeleton */}
      <div className="flex items-center gap-2">
        <div className="h-6 bg-gray-200 rounded-full w-16" />
        <div className="h-6 bg-gray-200 rounded-full w-20" />
      </div>
    </div>
  );
}

/**
 * Loading state specifically for playlists with appropriate skeleton cards.
 */
function PlaylistLoadingState({ count = 8 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
      role="status"
      aria-label="Loading playlists"
      aria-live="polite"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <PlaylistSkeletonCard key={index} />
      ))}
      <span className="sr-only">Loading playlists...</span>
    </div>
  );
}

/**
 * Pagination status component showing "X of Y playlists".
 */
interface PaginationStatusProps {
  loadedCount: number;
  total: number | null;
}

function PaginationStatus({ loadedCount, total }: PaginationStatusProps) {
  if (total === null) {
    return (
      <p className="text-sm text-gray-500 text-center py-2">
        Showing {loadedCount} playlist{loadedCount !== 1 ? "s" : ""}
      </p>
    );
  }

  return (
    <p className="text-sm text-gray-500 text-center py-2">
      Showing {loadedCount} of {total} playlist{total !== 1 ? "s" : ""}
    </p>
  );
}

/**
 * Message shown when all playlists have been loaded.
 */
interface AllLoadedMessageProps {
  total: number;
}

function AllLoadedMessage({ total }: AllLoadedMessageProps) {
  return (
    <p className="text-sm text-gray-500 text-center py-4 border-t border-gray-200">
      All {total} playlist{total !== 1 ? "s" : ""} loaded
    </p>
  );
}

/**
 * Empty state specific to playlists with filter-aware messaging (CHK053).
 *
 * Displays different messages based on the current filter:
 * - "all": No playlists at all
 * - "linked": No YouTube-linked playlists
 * - "local": No local playlists
 */
interface PlaylistEmptyStateProps {
  filter: PlaylistFilterType;
}

function PlaylistEmptyState({ filter }: PlaylistEmptyStateProps) {
  // Get filter-specific messaging
  const getEmptyStateContent = () => {
    switch (filter) {
      case "linked":
        return {
          heading: "No YouTube-linked playlists",
          message:
            "You don't have any YouTube-linked playlists yet. Sync your YouTube data to import your playlists.",
          showCommand: true,
        };
      case "local":
        return {
          heading: "No local playlists",
          message:
            "You haven't created any local playlists yet. Local playlists are managed within ChronoVista.",
          showCommand: false,
        };
      default: // "all"
        return {
          heading: "No playlists yet",
          message:
            "You don't have any playlists yet. Get started by syncing your YouTube data.",
          showCommand: true,
        };
    }
  };

  const { heading, message, showCommand } = getEmptyStateContent();

  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[400px]"
      role="status"
      aria-label={heading}
    >
      {/* Playlist Icon */}
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
            d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 0 1 0 3.75H5.625a1.875 1.875 0 0 1 0-3.75Z"
          />
        </svg>
      </div>

      {/* Heading */}
      <h3 className="text-xl font-semibold text-gray-900 mb-3">{heading}</h3>

      {/* Instructions */}
      <p className="text-gray-600 mb-6 max-w-sm">{message}</p>

      {/* CLI Command (only shown for "all" and "linked" filters) */}
      {showCommand && (
        <>
          <div className="inline-block mb-6">
            <code className="bg-gray-900 text-green-400 px-5 py-3 rounded-lg font-mono text-sm shadow-md block">
              $ chronovista sync
            </code>
          </div>

          {/* Additional Help */}
          <p className="text-sm text-gray-500 max-w-xs">
            This will fetch your YouTube playlists, videos, and transcripts.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * PlaylistsPage displays playlists with loading, error, and empty states.
 * Includes filter tabs and infinite scroll with Intersection Observer.
 *
 * Features:
 * - Filter tabs synchronized with URL params
 * - Responsive grid layout (1 col mobile → 4 cols desktop)
 * - Loading skeleton state
 * - Error state with retry functionality
 * - Empty state with filter-aware messaging
 * - Infinite scroll for pagination
 */
export function PlaylistsPage() {
  // URL params for filter and sort (CHK048: URL sync)
  const [searchParams, setSearchParams] = useSearchParams();

  // Parse filter from URL
  const filterParam = searchParams.get("filter") || "all";
  const filter = (
    ["all", "linked", "local"].includes(filterParam) ? filterParam : "all"
  ) as PlaylistFilterType;

  // Parse sort from URL (Feature 027: default is video_count desc)
  const sortByParam = searchParams.get("sort_by") || "video_count";
  const sortOrderParam = searchParams.get("sort_order") || "desc";
  const sortBy = (
    ["title", "created_at", "video_count"].includes(sortByParam)
      ? sortByParam
      : "video_count"
  ) as PlaylistSortField;
  const sortOrder = (
    ["asc", "desc"].includes(sortOrderParam) ? sortOrderParam : "desc"
  ) as SortOrder;

  // Fetch playlists with the current filter and sort
  const {
    playlists,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    retry,
    loadMoreRef,
  } = usePlaylists({ filter, sortBy, sortOrder });

  // Set page title
  useEffect(() => {
    document.title = "Playlists - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Scroll to top when filter or sort changes (FR-031)
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [filter, sortBy, sortOrder]);

  // Handle filter change (update URL param)
  const handleFilterChange = (newFilter: PlaylistFilterType) => {
    const newParams = new URLSearchParams(searchParams);
    if (newFilter === "all") {
      // Remove filter param for "all" (cleaner URL)
      newParams.delete("filter");
    } else {
      newParams.set("filter", newFilter);
    }
    setSearchParams(newParams);
  };


  // Initial loading state (CHK051)
  if (isLoading) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Playlists</h1>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <PlaylistFilterTabs
            currentFilter={filter}
            onFilterChange={handleFilterChange}
          />
          <SortDropdown
            options={PLAYLIST_SORT_OPTIONS}
            defaultField="video_count"
            defaultOrder="desc"
            label="Sort by"
          />
        </div>
        <PlaylistLoadingState count={12} />
      </main>
    );
  }

  // Error state (only if no playlists loaded) (CHK052)
  if (isError && playlists.length === 0) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Playlists</h1>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <PlaylistFilterTabs
            currentFilter={filter}
            onFilterChange={handleFilterChange}
          />
          <SortDropdown
            options={PLAYLIST_SORT_OPTIONS}
            defaultField="video_count"
            defaultOrder="desc"
            label="Sort by"
          />
        </div>
        <ErrorState error={error} onRetry={retry} />
      </main>
    );
  }

  // Empty state (CHK053)
  if (playlists.length === 0) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Playlists</h1>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <PlaylistFilterTabs
            currentFilter={filter}
            onFilterChange={handleFilterChange}
          />
          <SortDropdown
            options={PLAYLIST_SORT_OPTIONS}
            defaultField="video_count"
            defaultOrder="desc"
            label="Sort by"
          />
        </div>
        <PlaylistEmptyState filter={filter} />
      </main>
    );
  }

  // Playlists list with pagination (CHK050, CHK054)
  return (
    <main className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Playlists</h1>

      {/* Filter Tabs and Sort Dropdown (CHK048) */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <PlaylistFilterTabs
          currentFilter={filter}
          onFilterChange={handleFilterChange}
        />
        <SortDropdown
          options={PLAYLIST_SORT_OPTIONS}
          defaultField="video_count"
          defaultOrder="desc"
          label="Sort by"
        />
      </div>

      {/* ARIA live region announcing filtered count (FR-005) */}
      {total !== null && (
        <div role="status" aria-live="polite" className="sr-only">
          Showing {total} playlist{total !== 1 ? "s" : ""}
        </div>
      )}

      <div className="space-y-4">
        {/* Pagination Status - Top (only show if more to load) */}
        {hasNextPage && <PaginationStatus loadedCount={loadedCount} total={total} />}

        {/* Playlist Cards Grid (CHK049: responsive grid) */}
        <div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
          role="list"
          aria-label="Playlist list"
        >
          {playlists.map((playlist) => (
            <div key={playlist.playlist_id} role="listitem">
              <PlaylistCard playlist={playlist} />
            </div>
          ))}
        </div>

        {/* Loading more indicator */}
        {isFetchingNextPage && (
          <div aria-live="polite">
            <p className="text-sm text-gray-500 text-center py-2">
              Loading more playlists...
            </p>
            <PlaylistLoadingState count={4} />
          </div>
        )}

        {/* Inline error when playlists are loaded but next page fails */}
        {isError && playlists.length > 0 && (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-4 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-2">
              {typeof error === "object" && error !== null && "message" in error
                ? (error as { message: string }).message
                : "Failed to load more playlists"}
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

        {/* Intersection Observer Trigger Element (CHK054: infinite scroll) */}
        {!isError && <div ref={loadMoreRef} className="h-4" aria-hidden="true" />}

        {/* All Loaded Message */}
        {!hasNextPage && !isError && total !== null && total > 0 && (
          <AllLoadedMessage total={total} />
        )}
      </div>
    </main>
  );
}
