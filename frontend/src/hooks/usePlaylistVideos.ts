/**
 * usePlaylistVideos hook for fetching videos in a playlist with infinite scroll.
 *
 * Supports configurable sort order, boolean filters, and automatic refetch
 * when sort/filter options change.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type { SortOrder } from "../types/filters";
import type {
  PlaylistVideoItem,
  PlaylistVideoListResponse,
} from "../types/playlist";

/**
 * Default number of videos to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

/**
 * Fetches a page of videos from a playlist with sort/filter params.
 */
async function fetchPlaylistVideos(
  playlistId: string,
  offset: number,
  limit: number,
  includeUnavailable: boolean,
  sortBy?: string,
  sortOrder?: SortOrder,
  likedOnly?: boolean,
  hasTranscript?: boolean,
  unavailableOnly?: boolean
): Promise<PlaylistVideoListResponse> {
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
    include_unavailable: includeUnavailable.toString(),
  });

  if (sortBy) {
    params.set("sort_by", sortBy);
  }
  if (sortOrder) {
    params.set("sort_order", sortOrder);
  }
  if (likedOnly) {
    params.set("liked_only", "true");
  }
  if (hasTranscript) {
    params.set("has_transcript", "true");
  }
  if (unavailableOnly) {
    params.set("unavailable_only", "true");
  }

  return apiFetch<PlaylistVideoListResponse>(
    `/playlists/${playlistId}/videos?${params.toString()}`
  );
}

export interface UsePlaylistVideosOptions {
  /** Number of videos per page (default: 25) */
  limit?: number;
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
  /** Whether to include unavailable videos (default: true) */
  includeUnavailable?: boolean;
  /** Sort field (position, upload_date, title) */
  sortBy?: string;
  /** Sort order (asc, desc) */
  sortOrder?: SortOrder;
  /** Filter to show only liked videos */
  likedOnly?: boolean;
  /** Filter to show only videos with transcripts */
  hasTranscript?: boolean;
  /** Filter to show only unavailable videos */
  unavailableOnly?: boolean;
}

interface UsePlaylistVideosReturn {
  /** All loaded video items flattened */
  videos: PlaylistVideoItem[];
  /** Total number of videos available in the playlist */
  total: number | null;
  /** Number of videos currently loaded */
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
 * Hook for fetching videos in a playlist with infinite scroll.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * Includes an Intersection Observer for automatic next page loading.
 * Sort/filter options are included in the query key for automatic refetch.
 *
 * @example
 * ```tsx
 * const { videos, isLoading, loadMoreRef } = usePlaylistVideos("PLxxx", {
 *   sortBy: "upload_date",
 *   sortOrder: "desc",
 *   hasTranscript: true,
 * });
 *
 * return (
 *   <div>
 *     {videos.map(video => <VideoCard key={video.video_id} video={video} />)}
 *     <div ref={loadMoreRef} /> // Trigger element for auto-loading
 *   </div>
 * );
 * ```
 */
export function usePlaylistVideos(
  playlistId: string,
  options: UsePlaylistVideosOptions = {}
): UsePlaylistVideosReturn {
  const {
    limit = DEFAULT_LIMIT,
    enabled = true,
    includeUnavailable = true,
    sortBy,
    sortOrder,
    likedOnly,
    hasTranscript,
    unavailableOnly,
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
    queryKey: [
      "playlistVideos",
      playlistId,
      limit,
      includeUnavailable,
      sortBy,
      sortOrder,
      likedOnly,
      hasTranscript,
      unavailableOnly,
    ],
    queryFn: async ({ pageParam }) => {
      return fetchPlaylistVideos(
        playlistId,
        pageParam,
        limit,
        includeUnavailable,
        sortBy,
        sortOrder,
        likedOnly,
        hasTranscript,
        unavailableOnly
      );
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
  const videos = data?.pages.flatMap((page) => page.data) ?? [];

  // Get total count from the last page's pagination
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination?.total ?? null;
  const loadedCount = videos.length;

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
    videos,
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
