/**
 * TanStack Query hooks for batch correction history.
 *
 * Exports:
 * - useBatchHistory(limit?) — paginated list of past batch operations (Load More)
 * - useRevertBatch() — mutation to revert all corrections in a batch
 *
 * @module hooks/useBatchHistory
 */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { BatchSummary } from "../types/corrections";

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

/** Pagination envelope returned by the batch list endpoint. */
interface BatchListPagination {
  has_more: boolean;
  total: number;
  offset: number;
  limit: number;
}

/** Full API response envelope for GET /corrections/batch/batches. */
interface BatchListResponse {
  data: BatchSummary[];
  pagination: BatchListPagination;
}

/** API response envelope for DELETE /corrections/batch/{batchId}. */
interface BatchRevertApiResponse {
  data: {
    reverted_count: number;
    skipped_count: number;
  };
}

// ---------------------------------------------------------------------------
// useBatchHistory — infinite query for batch list
// ---------------------------------------------------------------------------

/**
 * Hook that fetches the paginated list of past batch correction operations.
 *
 * Uses `useInfiniteQuery` with manual "Load More" triggering. Call
 * `fetchNextPage()` when the user clicks the Load More button and check
 * `hasNextPage` to decide whether to show it.
 *
 * Data is flattened across pages via `data.pages.flatMap(p => p.data)`.
 *
 * @param limit - Number of items per page (default: 20)
 * @returns TanStack InfiniteQuery result for batch operations
 *
 * @example
 * ```tsx
 * const { data, hasNextPage, fetchNextPage, isLoading } = useBatchHistory();
 * const batches = data?.pages.flatMap(p => p.data) ?? [];
 * ```
 */
export function useBatchHistory(limit = 20) {
  return useInfiniteQuery({
    queryKey: ["batch-list"],
    queryFn: async ({ pageParam, signal }) => {
      const response = await apiFetch<BatchListResponse>(
        `/corrections/batch/batches?offset=${pageParam}&limit=${limit}`,
        { externalSignal: signal }
      );
      return response;
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination.has_more) return undefined;
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    staleTime: 60 * 1000, // 1 minute — batch list changes only after apply/revert
    gcTime: 5 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// useRevertBatch — mutation to revert all corrections in a batch
// ---------------------------------------------------------------------------

/** The result returned by a successful batch revert. */
export interface BatchRevertResult {
  reverted_count: number;
  skipped_count: number;
}

/**
 * Mutation hook for reverting all corrections in a batch operation.
 *
 * Calls DELETE /api/v1/corrections/batch/{batchId}. On success, invalidates
 * all caches that may reference batch-corrected data so the UI stays consistent:
 *
 * - `["batch-list"]` — removes the reverted batch from the history list
 * - `["corrections"]` — segment correction state
 * - `["transcriptSegments"]` — transcript segment text
 * - `["transcript"]` — transcript detail view
 * - `["diff-analysis"]` — ASR error pattern analysis
 * - `["cross-segment-candidates"]` — cross-segment correction suggestions
 *
 * Retries are disabled for 4xx responses (including 404 / 409 which indicate
 * the batch is not found or has already been reverted). Network/server errors
 * follow the default TanStack Query retry behaviour of 3 attempts.
 *
 * @returns UseMutationResult for the batch revert
 *
 * @example
 * ```tsx
 * const revert = useRevertBatch();
 * revert.mutate("batch-uuid-123");
 * ```
 */
export function useRevertBatch() {
  const queryClient = useQueryClient();

  return useMutation<BatchRevertResult, Error, string>({
    mutationFn: async (batchId: string): Promise<BatchRevertResult> => {
      const envelope = await apiFetch<BatchRevertApiResponse>(
        `/corrections/batch/${batchId}`,
        { method: "DELETE" }
      );
      return envelope.data;
    },

    onSuccess: () => {
      // Invalidate all caches that may contain batch-corrected data.
      // Void the promises — we do not await cache invalidations so the UI
      // doesn't block on background refetches.
      void queryClient.invalidateQueries({ queryKey: ["batch-list"] });
      void queryClient.invalidateQueries({ queryKey: ["corrections"] });
      void queryClient.invalidateQueries({ queryKey: ["transcriptSegments"] });
      void queryClient.invalidateQueries({ queryKey: ["transcript"] });
      void queryClient.invalidateQueries({ queryKey: ["diff-analysis"] });
      void queryClient.invalidateQueries({ queryKey: ["cross-segment-candidates"] });
    },
  });
}
