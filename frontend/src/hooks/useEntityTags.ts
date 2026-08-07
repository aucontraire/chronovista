/**
 * Mutations for an entity's tag section (Feature 064).
 *
 * Invalidation lives here rather than in the component because every mutation
 * on this surface invalidates the same three queries, and repeating that per
 * mutation is how one of them gets forgotten. Attaching a tag changes which
 * videos count toward the entity, so the header count and the video list below
 * it are both stale the moment it succeeds.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addEntityTag,
  fetchEntityTags,
  unlinkEntityTag,
  unMergeEntityTag,
} from "../api/entityMentions";
import type {
  AddEntityTagResult,
  EntityTagsResult,
  UnMergeResult,
} from "../api/entityMentions";

/**
 * The tags representing an entity.
 *
 * Without this the section is write-only: a curator cannot tell whether an
 * entity already has a tag, which is the question that precedes every other
 * action here.
 *
 * @param entityId - The entity to inspect
 */
export function useEntityTags(entityId: string) {
  return useQuery<EntityTagsResult>({
    queryKey: ["entity-tags", entityId],
    queryFn: () => fetchEntityTags(entityId),
  });
}

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
/**
 * Everything a tag operation makes stale.
 *
 * Shared by all three mutations rather than repeated: they invalidate the same
 * set, and repeating it is how one of them silently loses an entry. Any of
 * these operations changes which videos count toward the entity, and moves the
 * tag in or out of the searchable pool.
 */
function invalidateTagSurfaces(
  queryClient: ReturnType<typeof useQueryClient>,
  entityId: string
): void {
  void queryClient.invalidateQueries({ queryKey: ["entity-detail", entityId] });
  void queryClient.invalidateQueries({ queryKey: ["entity-videos", entityId] });
  void queryClient.invalidateQueries({ queryKey: ["entity-tags", entityId] });
  void queryClient.invalidateQueries({ queryKey: ["canonical-tags"] });
}

export function useAddEntityTag(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<AddEntityTagResult, unknown, string>({
    mutationFn: (normalizedForm: string) =>
      addEntityTag(entityId, normalizedForm),
    onSuccess: () => invalidateTagSurfaces(queryClient, entityId),
  });
}

/**
 * Reverse the merge that folded a tag into the entity's tag.
 *
 * @param entityId - The entity being edited
 * @returns A mutation taking the tag's normalized form and a confirmation flag
 */
export function useUnMergeEntityTag(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<
    UnMergeResult,
    unknown,
    { normalizedForm: string; confirmMultiSource?: boolean }
  >({
    mutationFn: ({ normalizedForm, confirmMultiSource }) =>
      unMergeEntityTag(entityId, normalizedForm, confirmMultiSource ?? false),
    onSuccess: () => invalidateTagSurfaces(queryClient, entityId),
  });
}

/**
 * Stop a tag representing the entity.
 *
 * @param entityId - The entity being edited
 * @returns A mutation taking the tag's normalized form
 */
export function useUnlinkEntityTag(entityId: string) {
  const queryClient = useQueryClient();

  return useMutation<{ unlinked: string }, unknown, string>({
    mutationFn: (normalizedForm: string) =>
      unlinkEntityTag(entityId, normalizedForm),
    onSuccess: () => invalidateTagSurfaces(queryClient, entityId),
  });
}
