/**
 * useChannelOperators — data for the channel "Operated by" panel.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchChannelOperators } from "../api/channelOwnership";
import type { ChannelOperatorsResponse } from "../api/channelOwnership";
import type { ApiError } from "../types/video";

interface UseChannelOperatorsReturn {
  data: ChannelOperatorsResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: ApiError | null;
  refetch: () => void;
}

export function useChannelOperators(
  channelId: string | undefined
): UseChannelOperatorsReturn {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["channel-operators", channelId],
    queryFn: ({ signal }) => fetchChannelOperators(channelId as string, signal),
    enabled: Boolean(channelId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  return {
    data,
    isLoading,
    isError,
    error: error as ApiError | null,
    refetch: () => void refetch(),
  };
}
