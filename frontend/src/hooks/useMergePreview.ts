/**
 * useMergePreview mutation hook for previewing a tag merge (Feature 056).
 *
 * The preview endpoint is read-only — it computes exact post-merge alias and
 * video counts over the union of source and target tags without mutating any
 * data (FR-008a). It is exposed as a POST endpoint (the request body is a
 * list of source tags plus a target), so — mirroring useBatchPreview — this
 * hook wraps useMutation rather than useQuery. The caller (MergeConfirmation)
 * triggers it whenever the selected source/target combination changes.
 *
 * @module hooks/useMergePreview
 */

import { useMutation, UseMutationResult } from "@tanstack/react-query";

import { apiFetch, isApiError } from "../api/config";
import type {
  MergePreview,
  MergePreviewRequest,
  MergePreviewResponse,
} from "../types/canonical-tags";

/**
 * Calls POST /api/v1/canonical-tags/merge/preview and unwraps the ApiResponse envelope.
 *
 * @param request - The source tags and target tag to preview
 * @returns The inner MergePreview (exact resulting alias/video counts)
 * @throws ApiError on network failure, timeout, or server error
 */
async function postMergePreview(
  request: MergePreviewRequest
): Promise<MergePreview> {
  const envelope = await apiFetch<MergePreviewResponse>(
    "/canonical-tags/merge/preview",
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
  return envelope.data;
}

/**
 * Mutation hook for previewing a tag merge without mutating any data.
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to trigger the preview and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (e.g. 400 for a self-merge, 404 for
 * a missing tag). Network errors (5xx, transient) follow the default
 * TanStack Query retry behaviour of 3 attempts.
 *
 * @returns UseMutationResult for the merge preview
 *
 * @example
 * ```tsx
 * const preview = useMergePreview();
 *
 * useEffect(() => {
 *   preview.mutate({
 *     source_normalized_forms: ["professor hannah fry"],
 *     target_normalized_form: "hannah fry",
 *   });
 * }, [sources, target]);
 *
 * if (preview.isPending) return <Spinner />;
 * if (preview.data) return <p>{preview.data.resulting_video_count} videos</p>;
 * ```
 */
export function useMergePreview(): UseMutationResult<
  MergePreview,
  Error,
  MergePreviewRequest
> {
  return useMutation<MergePreview, Error, MergePreviewRequest>({
    mutationFn: postMergePreview,

    retry: (failureCount, error) => {
      // Do not retry client errors (4xx) — self-merge, duplicate source, or
      // a missing/deprecated tag are all validation failures, not transient.
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },
  });
}
