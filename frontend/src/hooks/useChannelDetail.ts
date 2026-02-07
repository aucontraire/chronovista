/**
 * useChannelDetail hook for fetching a single channel's details.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { ChannelDetailResponse } from "../types/channel";
import type { ApiError } from "../types/video";

/**
 * Fetches a channel's details from the API.
 */
async function fetchChannelDetail(
  channelId: string
): Promise<ChannelDetailResponse> {
  return apiFetch<ChannelDetailResponse>(`/channels/${channelId}`);
}

interface UseChannelDetailReturn {
  /** Channel detail data */
  data: ChannelDetailResponse["data"] | undefined;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: ApiError | null;
  /** Function to refetch channel details */
  refetch: () => void;
}

/**
 * Hook for fetching a single channel's details.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Handles 404 errors separately from other errors for specialized UI treatment.
 *
 * @example
 * ```tsx
 * const { data: channel, isLoading, error } = useChannelDetail(channelId);
 *
 * if (error?.status === 404) {
 *   return <NotFound />;
 * }
 * ```
 */
export function useChannelDetail(
  channelId: string | undefined
): UseChannelDetailReturn {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["channel", channelId],
    queryFn: async () => {
      if (!channelId) {
        throw new Error("Channel ID is required");
      }
      return fetchChannelDetail(channelId);
    },
    enabled: Boolean(channelId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime in v4)
  });

  return {
    data: data?.data,
    isLoading,
    isError,
    error: error as ApiError | null,
    refetch: () => void refetch(),
  };
}
