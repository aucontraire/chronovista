/**
 * Channel-side channel-ownership mutations: assign and remove a manual
 * operator. Both route through the shared `invalidateOwnershipCaches` so the
 * entity page's "Operates" list is refreshed along with this channel's
 * "Operated by" list.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  assignChannelOperator,
  removeChannelOperator,
} from "../api/channelOwnership";
import type { ChannelOperatorItem } from "../api/channelOwnership";
import { invalidateOwnershipCaches } from "./useEntityChannelMutations";

/** Mutation: assign an entity as operator by ID. `mutate(entityId)`. */
export function useAssignChannelOperator(channelId: string) {
  const queryClient = useQueryClient();

  return useMutation<ChannelOperatorItem, unknown, string>({
    mutationFn: (entityId) => assignChannelOperator(channelId, entityId),
    onSuccess: (_data, entityId) =>
      invalidateOwnershipCaches(queryClient, { entityId, channelId }),
  });
}

/** Mutation: remove a manual operator from the channel side. `mutate(entityId)`. */
export function useRemoveChannelOperator(channelId: string) {
  const queryClient = useQueryClient();

  return useMutation<void, unknown, string>({
    mutationFn: (entityId) => removeChannelOperator(channelId, entityId),
    onSuccess: (_data, entityId) =>
      invalidateOwnershipCaches(queryClient, { entityId, channelId }),
  });
}
