/**
 * TanStack Query mutation hook for undoing an alias deletion (Feature #298).
 *
 * Restores the alias and its removed mentions and recomputes counts — an
 * association-level change, the same shape of change the delete itself
 * made. So this invalidates the same query families the entity detail
 * page's `refreshEntityAssociations` helper does for the delete path (see
 * `EntityDetailPage.tsx`), scoped to the entity the undone alias belongs to.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { undoAliasDeletion } from "../api/entityMentions";
import type { EntityDetail } from "../api/entityMentions";
import type { ApiError } from "../types/video";

/** Variables passed to the undo mutation. */
export interface UndoAliasDeletionVariables {
  /** The `operation_id` returned by the original `deleteEntityAlias` call. */
  operationId: string;
  /**
   * UUID of the entity the deleted alias belonged to. Not sent to the API —
   * `undoAliasDeletion` only needs the operation id — used here purely to
   * scope the entity-specific cache invalidation below.
   */
  entityId: string;
}

/**
 * Mutation hook for reversing an alias deletion.
 *
 * On success, invalidates the same association/mention query families the
 * delete flow's `refreshEntityAssociations` does:
 * - `entity-detail` (alias list, counts)
 * - `entity-videos` (the entity's video list)
 * - `video-entities` (every mounted EntityMentionsPanel)
 * - `entities` (aggregate counts elsewhere)
 * - `entitySearch` (autocomplete results)
 *
 * Error handling is left to the caller — use the per-call `onError`
 * callback to surface a 409 (already undone, or a colliding alias was
 * created since — restore rejected, nothing changed) or 404.
 *
 * @returns UseMutationResult with `mutate({ operationId, entityId })`
 *
 * @example
 * ```tsx
 * const undo = useUndoAliasDeletion();
 * undo.mutate(
 *   { operationId, entityId },
 *   { onError: (err) => setUndoError(err.message) }
 * );
 * ```
 */
export function useUndoAliasDeletion() {
  const queryClient = useQueryClient();

  return useMutation<EntityDetail, ApiError, UndoAliasDeletionVariables>({
    mutationFn: ({ operationId }) => undoAliasDeletion(operationId),

    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", variables.entityId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["entity-videos", variables.entityId],
      });
      void queryClient.invalidateQueries({ queryKey: ["video-entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
    },
  });
}
