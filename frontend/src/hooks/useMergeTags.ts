/**
 * useMergeTags mutation hook for executing a tag merge (Feature 056).
 *
 * Merge is a user-initiated, destructive action — it repoints tag_aliases to
 * the target canonical tag and marks the source tags merged. This hook wraps
 * useMutation rather than useQuery so the caller (MergeTagsPage) controls
 * when the operation fires via `mutate` / `mutateAsync`.
 *
 * On success, canonical tag list/detail caches are invalidated so the merged
 * source tags disappear from active listings and the target's counts reflect
 * the absorbed sources (Cross-Feature Data Contract Verification — merged
 * tags must vanish from Feature 030's list/detail/videos endpoints).
 *
 * @module hooks/useMergeTags
 */

import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";

import { apiFetch, isApiError } from "../api/config";
import type {
  MergeRequest,
  MergeResponse,
  MergeResult,
} from "../types/canonical-tags";

/**
 * Calls POST /api/v1/canonical-tags/merge and unwraps the ApiResponse envelope.
 *
 * @param request - The source tags, target tag, and optional reason
 * @returns The inner MergeResult (aliases moved, new counts, operation ID, entity hint)
 * @throws ApiError on network failure, timeout, or server error
 */
async function postMergeTags(request: MergeRequest): Promise<MergeResult> {
  const envelope = await apiFetch<MergeResponse>("/canonical-tags/merge", {
    method: "POST",
    body: JSON.stringify(request),
  });
  return envelope.data;
}

/**
 * Mutation hook for merging one or more source tags into a target canonical tag.
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to fire the merge and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (self-merge, duplicate source, a
 * source/target that no longer exists, or a 409 conflict from a concurrent
 * merge). Network errors (5xx, transient) follow the default TanStack Query
 * retry behaviour of 3 attempts.
 *
 * On success, invalidates:
 * - `["canonical-tags"]` prefix — covers every search/limit/matchMode
 *   combination cached by useCanonicalTags (video filter + merge selector)
 * - `["canonical-tag-detail"]` prefix — individual canonical tag detail views
 *
 * @returns UseMutationResult for the merge
 *
 * @example
 * ```tsx
 * const merge = useMergeTags();
 *
 * merge.mutate({
 *   source_normalized_forms: ["professor hannah fry"],
 *   target_normalized_form: "hannah fry",
 *   reason: "Same person, title variant",
 * });
 *
 * if (merge.isPending) return <Spinner />;
 * if (merge.data) return <MergeResultBanner result={merge.data} />;
 * ```
 */
export function useMergeTags(): UseMutationResult<
  MergeResult,
  Error,
  MergeRequest
> {
  const queryClient = useQueryClient();

  return useMutation<MergeResult, Error, MergeRequest>({
    mutationFn: postMergeTags,

    retry: (failureCount, error) => {
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },

    onSuccess: () => {
      // Merged source tags must disappear from active listings and the
      // target's alias_count/video_count must reflect the absorbed sources
      // (Cross-Feature Data Contract Verification, Feature 030 consumers).
      void queryClient.invalidateQueries({ queryKey: ["canonical-tags"] });
      void queryClient.invalidateQueries({ queryKey: ["canonical-tag-detail"] });
    },
  });
}
