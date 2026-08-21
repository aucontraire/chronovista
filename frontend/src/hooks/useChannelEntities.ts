/**
 * useChannelEntities hook for fetching a channel's entity ranking.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { ChannelEntitiesResponse } from "../types/channel";
import type { ApiError } from "../types/video";

/**
 * Fetches a channel's entity ranking from the API.
 */
async function fetchChannelEntities(
  channelId: string,
  signal?: AbortSignal
): Promise<ChannelEntitiesResponse> {
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  return apiFetch<ChannelEntitiesResponse>(`/channels/${channelId}/entities`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

interface UseChannelEntitiesReturn {
  /** Channel entity ranking data */
  data: ChannelEntitiesResponse | undefined;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: ApiError | null;
  /** Function to refetch the channel entity ranking */
  refetch: () => void;
}

/**
 * Hook for fetching a channel's entity ranking (Feature 070).
 *
 * Uses TanStack Query's useQuery for data fetching and caching. Mirrors
 * `useChannelDetail`'s return-shape conventions.
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useChannelEntities(channelId);
 * ```
 */
export function useChannelEntities(
  channelId: string | undefined
): UseChannelEntitiesReturn {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["channel-entities", channelId],
    queryFn: async ({ signal }) => {
      if (!channelId) {
        throw new Error("Channel ID is required");
      }
      // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
      return fetchChannelEntities(channelId, signal);
    },
    enabled: Boolean(channelId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime in v4)
  });

  return {
    data,
    isLoading,
    isError,
    error: error as ApiError | null,
    refetch: () => void refetch(),
  };
}
