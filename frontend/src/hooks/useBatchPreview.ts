/**
 * useBatchPreview mutation hook for triggering a batch correction preview.
 *
 * Preview is a user-initiated action (not a background fetch), so this hook
 * wraps useMutation rather than useQuery. The caller controls when the preview
 * fires by calling `mutate` or `mutateAsync`.
 *
 * @module hooks/useBatchPreview
 */

import { useMutation, UseMutationResult } from "@tanstack/react-query";

import { apiFetch, BATCH_PREVIEW_TIMEOUT } from "../api/config";
import { isApiError } from "../api/config";
import type {
  BatchPreviewRequest,
  BatchPreviewResponse,
} from "../types/batchCorrections";

/**
 * The API response envelope returned by the batch preview endpoint.
 * apiFetch returns the full envelope — the `data` key wraps BatchPreviewResponse.
 */
interface BatchPreviewApiResponse {
  data: BatchPreviewResponse;
}

/**
 * Calls POST /api/v1/corrections/batch/preview and unwraps the ApiResponse envelope.
 *
 * @param request - The preview request body
 * @returns The inner BatchPreviewResponse (matches, total_count, echoed params)
 * @throws ApiError on network failure, timeout, or server error
 */
async function fetchBatchPreview(
  request: BatchPreviewRequest
): Promise<BatchPreviewResponse> {
  const envelope = await apiFetch<BatchPreviewApiResponse>(
    "/corrections/batch/preview",
    {
      method: "POST",
      body: JSON.stringify(request),
      timeout: BATCH_PREVIEW_TIMEOUT,
    }
  );
  return envelope.data;
}

/**
 * Mutation hook for triggering a batch correction preview.
 *
 * Returns the standard TanStack Query mutation result — callers use
 * `mutate` / `mutateAsync` to fire the preview and `isPending`, `data`,
 * `error`, and `reset` to drive the UI.
 *
 * Retries are disabled for 4xx responses (including 422 Unprocessable Entity
 * returned for validation failures or backend timeout on large scans).
 * Network errors (5xx, transient) follow the default TanStack Query retry
 * behaviour of 3 attempts.
 *
 * No cache invalidation is performed — preview results are ephemeral and
 * live only in the mutation state.
 *
 * @returns UseMutationResult for the batch preview
 *
 * @example
 * ```tsx
 * const preview = useBatchPreview();
 *
 * preview.mutate({
 *   pattern: "teh",
 *   replacement: "the",
 *   is_regex: false,
 *   case_insensitive: true,
 * });
 *
 * if (preview.isPending) return <Spinner />;
 * if (preview.error) return <ErrorMessage error={preview.error} />;
 * if (preview.data) return <MatchList matches={preview.data.matches} />;
 * ```
 */
export function useBatchPreview(): UseMutationResult<
  BatchPreviewResponse,
  Error,
  BatchPreviewRequest
> {
  return useMutation<BatchPreviewResponse, Error, BatchPreviewRequest>({
    mutationFn: fetchBatchPreview,

    retry: (failureCount, error) => {
      // Do not retry client errors (4xx) — includes 422 validation/timeout errors.
      // Retry up to 3 times for network/server errors (5xx).
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },
  });
}
