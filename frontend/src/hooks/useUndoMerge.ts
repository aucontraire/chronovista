/**
 * useUndoMerge mutation hook for reversing a tag operation (Feature 056).
 *
 * Undo is session-scoped in the UI (FR-010): the affordance lives only in
 * the post-merge result banner for as long as that component instance stays
 * mounted, and is never persisted to storage. This hook wraps useMutation so
 * the caller (MergeResultBanner) controls when the undo fires.
 *
 * On success, canonical tag list/detail caches are invalidated so the
 * restored source tags reappear as independent canonical tags.
 *
 * @module hooks/useUndoMerge
 */

import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";

import { apiFetch, isApiError } from "../api/config";
import type { UndoResponse, UndoResult } from "../types/canonical-tags";

/**
 * Calls POST /api/v1/canonical-tags/operations/{operationId}/undo and
 * unwraps the ApiResponse envelope.
 *
 * @param operationId - The operation ID to undo (returned by useMergeTags)
 * @returns The inner UndoResult (operation type, ID, human-readable summary)
 * @throws ApiError on network failure, timeout, not-found (404), or
 *         already-undone (409)
 */
async function postUndoMerge(operationId: string): Promise<UndoResult> {
  const envelope = await apiFetch<UndoResponse>(
    `/canonical-tags/operations/${encodeURIComponent(operationId)}/undo`,
    { method: "POST" }
  );
  return envelope.data;
}

/**
 * Mutation hook for undoing a previously logged tag operation (e.g. a merge).
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to fire the undo and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (404 not found, 409 already
 * undone). Network errors (5xx, transient) follow the default TanStack
 * Query retry behaviour of 3 attempts.
 *
 * On success, invalidates:
 * - `["canonical-tags"]` prefix — restored source tags reappear in search
 * - `["canonical-tag-detail"]` prefix — individual canonical tag detail views
 *
 * @returns UseMutationResult for the undo (variables: the operation ID string)
 *
 * @example
 * ```tsx
 * const undo = useUndoMerge();
 *
 * undo.mutate(result.operation_id, {
 *   onSuccess: () => setUndoSuccess(true),
 * });
 * ```
 */
export function useUndoMerge(): UseMutationResult<UndoResult, Error, string> {
  const queryClient = useQueryClient();

  return useMutation<UndoResult, Error, string>({
    mutationFn: postUndoMerge,

    retry: (failureCount, error) => {
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },

    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["canonical-tags"] });
      void queryClient.invalidateQueries({ queryKey: ["canonical-tag-detail"] });
    },
  });
}
