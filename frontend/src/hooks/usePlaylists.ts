/**
 * usePlaylists hook for fetching playlists with infinite scroll and filter support.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type {
  PlaylistFilterType,
  PlaylistListItem,
  PlaylistListResponse,
  PlaylistSortField,
  SortOrder,
} from "../types/playlist";

/**
 * Default number of playlists to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

/**
 * Fetches a page of playlists from the API.
 */
async function fetchPlaylists(
  offset: number,
  limit: number,
  filter: PlaylistFilterType,
  sortBy: PlaylistSortField,
  sortOrder: SortOrder
): Promise<PlaylistListResponse> {
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  // Add linked parameter based on filter type
  if (filter === "linked") {
    params.append("linked", "true");
  } else if (filter === "local") {
    params.append("linked", "false");
  }
  // For "all", omit the linked parameter

  return apiFetch<PlaylistListResponse>(`/playlists?${params.toString()}`);
}

interface UsePlaylistsOptions {
  /** Filter type: "all", "linked", or "local" (default: "all") */
  filter?: PlaylistFilterType;
  /** Sort field: "title", "created_at", or "video_count" (default: "created_at") */
  sortBy?: PlaylistSortField;
  /** Sort order: "asc" or "desc" (default: "desc") */
  sortOrder?: SortOrder;
  /** Number of playlists per page (default: 25) */
  limit?: number;
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
}

interface UsePlaylistsReturn {
  /** All loaded playlist items flattened */
  playlists: PlaylistListItem[];
  /** Total number of playlists available */
  total: number | null;
  /** Number of playlists currently loaded */
  loadedCount: number;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
  /** Whether more pages are available */
  hasNextPage: boolean;
  /** Whether a next page is currently being fetched */
  isFetchingNextPage: boolean;
  /** Function to manually fetch the next page */
  fetchNextPage: () => void;
  /** Function to retry after an error */
  retry: () => void;
  /** Ref to attach to the trigger element for auto-loading */
  loadMoreRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Hook for fetching playlists with infinite scroll and filter support.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * Includes an Intersection Observer for automatic next page loading.
 *
 * @example
 * ```tsx
 * const { playlists, isLoading, loadMoreRef } = usePlaylists({ filter: "linked" });
 *
 * return (
 *   <div>
 *     {playlists.map(playlist => <PlaylistCard key={playlist.playlist_id} playlist={playlist} />)}
 *     <div ref={loadMoreRef} /> // Trigger element for auto-loading
 *   </div>
 * );
 * ```
 */
export function usePlaylists(
  options: UsePlaylistsOptions = {}
): UsePlaylistsReturn {
  const {
    filter = "all",
    sortBy = "created_at",
    sortOrder = "desc",
    limit = DEFAULT_LIMIT,
    enabled = true,
  } = options;

  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const {
    data,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["playlists", filter, sortBy, sortOrder, limit],
    queryFn: async ({ pageParam }) => {
      return fetchPlaylists(pageParam, limit, filter, sortBy, sortOrder);
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination?.has_more) {
        return undefined;
      }
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime in v4)
  });

  // Flatten all pages into a single array
  const playlists = data?.pages.flatMap((page) => page.data) ?? [];

  // Get total count from the last page's pagination
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination?.total ?? null;
  const loadedCount = playlists.length;

  // Memoized fetch function for intersection observer
  const handleIntersect = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Set up Intersection Observer for auto-loading
  useEffect(() => {
    const element = loadMoreRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          handleIntersect();
        }
      },
      {
        threshold: INTERSECTION_THRESHOLD,
        rootMargin: "100px", // Start loading a bit before element is visible
      }
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [handleIntersect]);

  // Retry function for error recovery
  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);

  return {
    playlists,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    fetchNextPage: () => void fetchNextPage(),
    retry,
    loadMoreRef,
  };
}
