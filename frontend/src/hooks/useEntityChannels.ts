/**
 * useEntityChannels — data for the entity "Operates" panel.
 * A single (non-paginated) query: the backend returns every linked channel.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchEntityChannels } from "../api/channelOwnership";
import type { EntityChannelLink } from "../api/channelOwnership";

interface UseEntityChannelsReturn {
  channels: EntityChannelLink[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useEntityChannels(entityId: string | undefined): UseEntityChannelsReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["entityChannels", entityId ?? null],
    queryFn: ({ signal }) => fetchEntityChannels(entityId as string, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
  });

  return { channels: Array.isArray(data) ? data : [], isLoading, isError, error };
}
