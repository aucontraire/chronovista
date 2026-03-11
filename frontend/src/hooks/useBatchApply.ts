/**
 * useBatchApply mutation hook for applying a batch correction to transcript segments.
 *
 * Apply is a user-initiated destructive action — it persists corrections to the
 * database and optionally triggers a full-text rebuild. This hook wraps
 * useMutation rather than useQuery so the caller controls when the operation
 * fires via `mutate` / `mutateAsync`.
 *
 * On success, all transcript segment and transcript detail caches are
 * invalidated so subsequent renders reflect the corrected text.
 *
 * @module hooks/useBatchApply
 */

import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { isApiError } from "../api/config";
import type {
  BatchApplyRequest,
  BatchApplyResult,
} from "../types/batchCorrections";

/**
 * The API response envelope returned by the batch apply endpoint.
 * apiFetch returns the full envelope — the `data` key wraps BatchApplyResult.
 */
interface BatchApplyApiResponse {
  data: BatchApplyResult;
}

/**
 * Calls POST /api/v1/corrections/batch/apply and unwraps the ApiResponse envelope.
 *
 * @param request - The apply request body
 * @returns The inner BatchApplyResult (applied/skipped/failed counts, affected video IDs)
 * @throws ApiError on network failure, timeout, or server error
 */
async function postBatchApply(
  request: BatchApplyRequest
): Promise<BatchApplyResult> {
  const envelope = await apiFetch<BatchApplyApiResponse>(
    "/corrections/batch/apply",
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
  return envelope.data;
}

/**
 * Mutation hook for applying a batch correction to transcript segments.
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to fire the apply and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (including 422 Unprocessable Entity
 * returned for validation failures). Network errors (5xx, transient) follow
 * the default TanStack Query retry behaviour of 3 attempts.
 *
 * On success, the following caches are invalidated so affected segments and
 * transcript views are refetched with the corrected text:
 * - `["transcriptSegments"]` prefix — covers all video+language combinations
 *   cached by useTranscriptSegments (segmentsQueryKey factory)
 * - `["transcript"]` prefix — covers all transcript detail views cached by
 *   useTranscript
 *
 * @returns UseMutationResult for the batch apply
 *
 * @example
 * ```tsx
 * const apply = useBatchApply();
 *
 * apply.mutate({
 *   pattern: "teh",
 *   replacement: "the",
 *   segment_ids: [42, 99, 137],
 *   correction_type: "typo",
 * });
 *
 * if (apply.isPending) return <Spinner />;
 * if (apply.error) return <ErrorMessage error={apply.error} />;
 * if (apply.data) return <ApplySummary result={apply.data} />;
 * ```
 */
export function useBatchApply(): UseMutationResult<
  BatchApplyResult,
  Error,
  BatchApplyRequest
> {
  const queryClient = useQueryClient();

  return useMutation<BatchApplyResult, Error, BatchApplyRequest>({
    mutationFn: postBatchApply,

    retry: (failureCount, error) => {
      // Do not retry client errors (4xx) — includes 422 validation errors.
      // Retry up to 3 times for network/server errors (5xx).
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },

    onSuccess: () => {
      // Invalidate all cached transcript segment pages so the corrected text
      // is refetched on next render. Prefix matching covers every
      // (videoId, languageCode) combination without needing to enumerate them.
      void queryClient.invalidateQueries({ queryKey: ["transcriptSegments"] });

      // Invalidate transcript detail queries (useTranscript) for the same reason.
      void queryClient.invalidateQueries({ queryKey: ["transcript"] });
    },
  });
}
