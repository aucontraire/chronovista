/**
 * useChannels hook for fetching channels with infinite scroll support.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type { ChannelListResponse } from "../types/channel";

/**
 * Default number of channels to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

/**
 * Fetches a page of channels from the API.
 */
async function fetchChannels(
  offset: number,
  limit: number
): Promise<ChannelListResponse> {
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
  });

  return apiFetch<ChannelListResponse>(`/channels?${params.toString()}`);
}

interface UseChannelsOptions {
  /** Number of channels per page (default: 25) */
  limit?: number;
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
}

interface UseChannelsReturn {
  /** All loaded channel pages flattened */
  channels: ChannelListResponse["data"];
  /** Total number of channels available */
  total: number | null;
  /** Number of channels currently loaded */
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
 * Hook for fetching channels with infinite scroll support.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * Includes an Intersection Observer for automatic next page loading.
 *
 * @example
 * ```tsx
 * const { channels, isLoading, loadMoreRef } = useChannels();
 *
 * return (
 *   <div>
 *     {channels.map(channel => <ChannelCard key={channel.channel_id} channel={channel} />)}
 *     <div ref={loadMoreRef} /> // Trigger element for auto-loading
 *   </div>
 * );
 * ```
 */
export function useChannels(options: UseChannelsOptions = {}): UseChannelsReturn {
  const { limit = DEFAULT_LIMIT, enabled = true } = options;

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
    queryKey: ["channels", limit],
    queryFn: async ({ pageParam }) => {
      return fetchChannels(pageParam, limit);
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
  const channels = data?.pages.flatMap((page) => page.data) ?? [];

  // Get total count from the last page's pagination
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination?.total ?? null;
  const loadedCount = channels.length;

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
    channels,
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
