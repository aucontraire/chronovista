/**
 * useChannels hook for fetching channels with infinite scroll support.
 *
 * Supports sorting by video_count or name, and filtering by subscription status.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import type { ChannelListResponse } from "../types/channel";
import type { ChannelSortField, SortOrder } from "../types/filters";

/**
 * Default number of channels to fetch per page.
 */
const DEFAULT_LIMIT = 25;

/**
 * Intersection Observer threshold for triggering next page load.
 */
const INTERSECTION_THRESHOLD = 0.8;

/**
 * Subscription filter values that map to the API is_subscribed param.
 * - "all" -> omit is_subscribed param
 * - "subscribed" -> is_subscribed=true
 * - "not_subscribed" -> is_subscribed=false
 */
export type SubscriptionFilter = "all" | "subscribed" | "not_subscribed";

/**
 * Fetches a page of channels from the API.
 */
async function fetchChannels(
  offset: number,
  limit: number,
  sortBy: ChannelSortField,
  sortOrder: SortOrder,
  isSubscribed: SubscriptionFilter
): Promise<ChannelListResponse> {
  const params = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  // Map subscription filter to API param
  if (isSubscribed === "subscribed") {
    params.append("is_subscribed", "true");
  } else if (isSubscribed === "not_subscribed") {
    params.append("is_subscribed", "false");
  }
  // For "all", omit the is_subscribed parameter

  return apiFetch<ChannelListResponse>(`/channels?${params.toString()}`);
}

interface UseChannelsOptions {
  /** Sort field: "video_count" or "name" (default: "video_count") */
  sortBy?: ChannelSortField;
  /** Sort order: "asc" or "desc" (default: "desc") */
  sortOrder?: SortOrder;
  /** Subscription filter: "all", "subscribed", or "not_subscribed" (default: "all") */
  isSubscribed?: SubscriptionFilter;
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
 * Supports sorting by video_count or name, and filtering by subscription status.
 *
 * @example
 * ```tsx
 * const { channels, isLoading, loadMoreRef } = useChannels({
 *   sortBy: 'video_count',
 *   sortOrder: 'desc',
 *   isSubscribed: 'subscribed',
 * });
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
  const {
    sortBy = "video_count",
    sortOrder = "desc",
    isSubscribed = "all",
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
    queryKey: ["channels", sortBy, sortOrder, isSubscribed, limit],
    queryFn: async ({ pageParam }) => {
      return fetchChannels(pageParam, limit, sortBy, sortOrder, isSubscribed);
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
