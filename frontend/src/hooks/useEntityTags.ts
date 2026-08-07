/**
 * Mutations for an entity's tag section (Feature 064).
 *
 * Invalidation lives here rather than in the component because every mutation
 * on this surface invalidates the same three queries, and repeating that per
 * mutation is how one of them gets forgotten. Attaching a tag changes which
 * videos count toward the entity, so the header count and the video list below
 * it are both stale the moment it succeeds.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { addEntityTag } from "../api/entityMentions";
import type { AddEntityTagResult } from "../api/entityMentions";

/**
 * Attach a canonical tag to an entity.
 *
 * The server decides between linking and merging; the returned `operation`
 * says which, so the caller can word its confirmation truthfully instead of
 * guessing.
 *
 * @param entityId - The entity being edited
 * @returns A TanStack mutation taking the tag's normalized form
 */
export function useAddEntityTag(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<AddEntityTagResult, unknown, string>({
    mutationFn: (normalizedForm: string) =>
      addEntityTag(entityId, normalizedForm),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", entityId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["entity-videos", entityId],
      });
      // The attached tag has just left the searchable set — by status for a
      // merge, by entity_id for a link — so cached search results now offer a
      // tag the next request would reject.
      void queryClient.invalidateQueries({ queryKey: ["canonical-tags"] });
    },
  });
}
