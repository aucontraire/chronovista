/**
 * useVideos hook for fetching videos with infinite scroll support.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type { VideoListResponse } from "../types/video";

/**
 * Default number of videos to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

interface UseVideosOptions {
  /** Number of videos per page (default: 25) */
  limit?: number;
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
  /** Filter by tags (OR logic) */
  tags?: string[];
  /** Filter by category ID */
  category?: string | null;
  /** Filter by topic IDs (OR logic) */
  topicIds?: string[];
  /** Include unavailable content (T031, FR-021) */
  includeUnavailable?: boolean;
}

interface UseVideosReturn {
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
 * Hook for fetching videos with infinite scroll support.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * Includes an Intersection Observer for automatic next page loading.
 *
 * @example
 * ```tsx
 * const { videos, isLoading, loadMoreRef } = useVideos();
 *
 * return (
 *   <div>
 *     {videos.map(video => <VideoCard key={video.video_id} video={video} />)}
 *     <div ref={loadMoreRef} /> // Trigger element for auto-loading
 *   </div>
 * );
 * ```
 */
export function useVideos(options: UseVideosOptions = {}): UseVideosReturn {
  const {
    limit = DEFAULT_LIMIT,
    enabled = true,
    tags = [],
    category = null,
    topicIds = [],
    includeUnavailable = false
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
    queryKey: ["videos", { limit, tags, category, topicIds, includeUnavailable }],
    queryFn: async ({ pageParam, signal }) => {
      const params = new URLSearchParams({
        offset: pageParam.toString(),
        limit: limit.toString(),
      });

      // Add filter parameters
      tags.forEach(tag => params.append('tag', tag));
      if (category) params.set('category', category);
      topicIds.forEach(id => params.append('topic_id', id));

      // T031: Add include_unavailable parameter (FR-021)
      if (includeUnavailable) {
        params.set('include_unavailable', 'true');
      }

      return apiFetch<VideoListResponse>(`/videos?${params.toString()}`, { signal });
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
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
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
