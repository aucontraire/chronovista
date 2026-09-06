/**
 * TanStack Query mutation hook for re-linking (or refreshing) a named
 * entity's external knowledge-base grounding (Feature 073).
 *
 * US1 (re-link, implemented here): `data.approved_identifier` present.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { regroundEntity } from "../api/entityMentions";
import type { EntityDetail, GroundingRequest } from "../api/entityMentions";
import type { ApiError } from "../types/video";

/** Variables passed to the re-grounding mutation. */
export interface RegroundEntityVariables {
  /** UUID of the named entity to re-ground */
  entityId: string;
  /** The new approved identifier and/or description */
  data: GroundingRequest;
}

/**
 * Mutation hook for re-linking (or refreshing) a named entity's external
 * knowledge-base grounding.
 *
 * On success, invalidates caches for:
 * - `entity-detail` (so the Enrichment section reflects the new identifier)
 * - `entities`      (entity list page refreshes)
 *
 * Error handling is left to the caller — use `mutation.isError` / the
 * per-call `onError` callback to display inline 404/422 errors while keeping
 * the dialog open with the user's input preserved.
 *
 * @returns UseMutationResult with `mutate({ entityId, data })`
 *
 * @example
 * ```tsx
 * const mutation = useRegroundEntity();
 * mutation.mutate({
 *   entityId,
 *   data: { approved_identifier: { source: "wikidata", id: "Q7186" } },
 * });
 * ```
 */
export function useRegroundEntity() {
  const queryClient = useQueryClient();

  return useMutation<EntityDetail, ApiError, RegroundEntityVariables>({
    mutationFn: ({ entityId, data }) => regroundEntity(entityId, data),

    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", variables.entityId],
      });
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
    },
  });
}
