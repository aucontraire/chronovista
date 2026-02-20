/**
 * useChannelVideos hook for fetching videos from a specific channel with infinite scroll.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type { VideoListResponse } from "../types/video";
import type { ChannelVideoSortField, SortOrder } from "../types/filters";

/**
 * Default number of videos to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

/**
 * Fetches a page of videos for a specific channel from the API.
 */
async function fetchChannelVideos(
  channelId: string,
  offset: number,
  limit: number,
  includeUnavailable: boolean,
  sortBy?: ChannelVideoSortField,
  sortOrder?: SortOrder,
  likedOnly?: boolean
): Promise<VideoListResponse> {
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

  return apiFetch<VideoListResponse>(
    `/channels/${channelId}/videos?${params.toString()}`
  );
}

interface UseChannelVideosOptions {
  /** Number of videos per page (default: 25) */
  limit?: number;
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
  /** Whether to include unavailable videos (default: true) */
  includeUnavailable?: boolean;
  /** Sort field (upload_date or title) */
  sortBy?: ChannelVideoSortField;
  /** Sort order (asc or desc) */
  sortOrder?: SortOrder;
  /** Filter to only liked videos */
  likedOnly?: boolean;
}

interface UseChannelVideosReturn {
  /** All loaded video pages flattened */
  videos: VideoListResponse["data"];
  /** Total number of videos available */
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
 * Hook for fetching videos from a specific channel with infinite scroll support.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * Includes an Intersection Observer for automatic next page loading.
 *
 * @example
 * ```tsx
 * const { videos, isLoading, loadMoreRef } = useChannelVideos(channelId);
 *
 * return (
 *   <div>
 *     {videos.map(video => <VideoCard key={video.video_id} video={video} />)}
 *     <div ref={loadMoreRef} /> // Trigger element for auto-loading
 *   </div>
 * );
 * ```
 */
export function useChannelVideos(
  channelId: string | undefined,
  options: UseChannelVideosOptions = {}
): UseChannelVideosReturn {
  const {
    limit = DEFAULT_LIMIT,
    enabled = true,
    includeUnavailable = true,
    sortBy,
    sortOrder,
    likedOnly,
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
    queryKey: ["channel-videos", channelId, limit, includeUnavailable, sortBy, sortOrder, likedOnly],
    queryFn: async ({ pageParam }) => {
      if (!channelId) {
        throw new Error("Channel ID is required");
      }
      return fetchChannelVideos(channelId, pageParam, limit, includeUnavailable, sortBy, sortOrder, likedOnly);
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination?.has_more) {
        return undefined;
      }
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    enabled: enabled && Boolean(channelId),
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
