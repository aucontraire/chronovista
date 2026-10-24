/**
 * Hooks for hiding a video from an entity and restoring it (Feature 091).
 *
 * Excluding or restoring changes the entity↔video association set, so both
 * mutations invalidate the same query families the manual-association
 * mutations do — otherwise the connected-videos list and the header count
 * (`entity.video_count`, served by `["entity-detail", entityId]`) drift apart.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  createEntityVideoExclusion,
  deleteEntityVideoExclusion,
  fetchEntityVideoExclusions,
  type CreateEntityVideoExclusionResponse,
  type EntityVideoExclusionListResponse,
} from "../api/entityMentions";
import type { ApiError } from "../types/video";

/** Page size for the hidden-videos list; the section is expected to be tiny. */
export const ENTITY_EXCLUSIONS_LIMIT = 100;

function invalidateAssociationCaches(
  queryClient: QueryClient,
  entityId: string,
  videoId: string
): void {
  void queryClient.invalidateQueries({ queryKey: ["entity-videos"] });
  void queryClient.invalidateQueries({ queryKey: ["video-entities", videoId] });
  void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
  // Header count (entity.video_count) lives on the entity-detail query.
  void queryClient.invalidateQueries({ queryKey: ["entity-detail", entityId] });
  void queryClient.invalidateQueries({
    queryKey: ["entity-exclusions", entityId],
  });
}

/** Variables for the exclude / restore mutations. */
export interface EntityExclusionVariables {
  videoId: string;
  reason?: string;
}

/** Mutation: hide a video from the entity. */
export function useExcludeEntityVideo(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CreateEntityVideoExclusionResponse,
    ApiError,
    EntityExclusionVariables
  >({
    mutationFn: (variables) => createEntityVideoExclusion(entityId, variables),
    onSuccess: (_data, variables) =>
      invalidateAssociationCaches(queryClient, entityId, variables.videoId),
  });
}

/** Mutation: restore a hidden video to the entity. */
export function useRestoreEntityVideo(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, { videoId: string }>({
    mutationFn: ({ videoId }) => deleteEntityVideoExclusion(entityId, videoId),
    onSuccess: (_data, variables) =>
      invalidateAssociationCaches(queryClient, entityId, variables.videoId),
  });
}

/** Query: videos currently hidden from the entity. */
export function useEntityExclusions(entityId: string) {
  return useQuery<EntityVideoExclusionListResponse, ApiError>({
    queryKey: ["entity-exclusions", entityId],
    queryFn: ({ signal }) =>
      fetchEntityVideoExclusions(
        entityId,
        { limit: ENTITY_EXCLUSIONS_LIMIT, offset: 0 },
        signal
      ),
    enabled: entityId !== "",
  });
}
