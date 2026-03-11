/**
 * useBatchRebuild mutation hook for rebuilding the full text of transcript segments
 * after batch corrections have been applied.
 *
 * Rebuild is a user-initiated operation — it recomputes the denormalised full-text
 * column on affected segments from the current correction log. This hook wraps
 * useMutation rather than useQuery so the caller controls when the operation
 * fires via `mutate` / `mutateAsync`.
 *
 * On success, all transcript caches are invalidated so subsequent renders
 * reflect the rebuilt text.
 *
 * @module hooks/useBatchRebuild
 */

import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { isApiError } from "../api/config";
import type {
  BatchRebuildRequest,
  BatchRebuildResult,
} from "../types/batchCorrections";

/**
 * The API response envelope returned by the batch rebuild endpoint.
 * apiFetch returns the full envelope — the `data` key wraps BatchRebuildResult.
 */
interface BatchRebuildApiResponse {
  data: BatchRebuildResult;
}

/**
 * Calls POST /api/v1/corrections/batch/rebuild-text and unwraps the ApiResponse envelope.
 *
 * @param request - The rebuild request body containing affected video_ids
 * @returns The inner BatchRebuildResult (rebuilt/skipped/failed counts, affected video IDs)
 * @throws ApiError on network failure, timeout, or server error
 */
async function postBatchRebuild(
  request: BatchRebuildRequest
): Promise<BatchRebuildResult> {
  const envelope = await apiFetch<BatchRebuildApiResponse>(
    "/corrections/batch/rebuild-text",
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
  return envelope.data;
}

/**
 * Mutation hook for rebuilding the full text of transcript segments after
 * batch corrections have been applied.
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to fire the rebuild and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (including 422 Unprocessable Entity
 * returned for validation failures). Network errors (5xx, transient) follow
 * the default TanStack Query retry behaviour of 3 attempts.
 *
 * On success, the following caches are invalidated so affected transcript
 * views are refetched with the rebuilt text:
 * - `["transcript"]` prefix — covers all transcript detail views cached by
 *   useTranscript (rebuilt text affects every transcript-level consumer)
 *
 * @returns UseMutationResult for the batch rebuild
 *
 * @example
 * ```tsx
 * const rebuild = useBatchRebuild();
 *
 * rebuild.mutate({
 *   video_ids: ["dQw4w9WgXcQ", "oHg5SJYRHA0"],
 * });
 *
 * if (rebuild.isPending) return <Spinner />;
 * if (rebuild.error) return <ErrorMessage error={rebuild.error} />;
 * if (rebuild.data) return <RebuildSummary result={rebuild.data} />;
 * ```
 */
export function useBatchRebuild(): UseMutationResult<
  BatchRebuildResult,
  Error,
  BatchRebuildRequest
> {
  const queryClient = useQueryClient();

  return useMutation<BatchRebuildResult, Error, BatchRebuildRequest>({
    mutationFn: postBatchRebuild,

    retry: (failureCount, error) => {
      // Do not retry client errors (4xx) — includes 422 validation errors.
      // Retry up to 3 times for network/server errors (5xx).
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },

    onSuccess: () => {
      // Invalidate transcript detail queries (useTranscript) so the rebuilt
      // full text is refetched on next render. Prefix matching covers every
      // (videoId, languageCode) combination without needing to enumerate them.
      void queryClient.invalidateQueries({ queryKey: ["transcript"] });
    },
  });
}
