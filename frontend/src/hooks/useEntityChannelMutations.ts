/**
 * Entity-side channel-ownership mutations: add and remove a manual
 * "this entity operates this channel" link.
 *
 * Both mutations change the same link set that two pages read — the entity's
 * "Operates" list (`["entityChannels", entityId]`) and the channel's
 * "Operated by" list (`["channel-operators", channelId]`) — so every mutation,
 * on either side, goes through `invalidateOwnershipCaches`. Repeating the
 * invalidation per mutation is how one of them gets forgotten.
 */

import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  addEntityChannel,
  removeEntityChannel,
} from "../api/channelOwnership";
import type { EntityChannelLink } from "../api/channelOwnership";

/**
 * Refetch both families of ownership lists. An id narrows its family to that
 * entity/channel; omitted, the whole family is invalidated (the id is not
 * known to the caller, e.g. assigning from the channel side).
 */
export function invalidateOwnershipCaches(
  queryClient: QueryClient,
  ids: { entityId?: string; channelId?: string }
): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: ids.entityId ? ["entityChannels", ids.entityId] : ["entityChannels"],
    }),
    queryClient.invalidateQueries({
      queryKey: ids.channelId ? ["channel-operators", ids.channelId] : ["channel-operators"],
    }),
  ]);
}

/** Mutation: add a channel (raw ID or URL) to the entity. `mutate(channelRef)`. */
export function useAddEntityChannel(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<EntityChannelLink, unknown, string>({
    mutationFn: (channelRef) => addEntityChannel(entityId, channelRef),
    onSuccess: () => invalidateOwnershipCaches(queryClient, { entityId }),
  });
}

/** Mutation: remove a manual link from the entity side. `mutate(channelId)`. */
export function useRemoveEntityChannel(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<void, unknown, string>({
    mutationFn: (channelId) => removeEntityChannel(entityId, channelId),
    onSuccess: (_data, channelId) =>
      invalidateOwnershipCaches(queryClient, { entityId, channelId }),
  });
}
