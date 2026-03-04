/**
 * useRevertSegment hook for reverting transcript segment corrections.
 *
 * Implements:
 * - FR-035b: Correction revert via POST endpoint
 * - Server-confirmed cache patch (no optimistic update — revert is destructive)
 * - Cache invalidation on error
 *
 * @module hooks/useRevertSegment
 */

import {
  InfiniteData,
  useMutation,
  UseMutationResult,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { segmentsQueryKey } from "./useTranscriptSegments";
import type { SegmentListResponse } from "../types/transcript";
import type { CorrectionRevertResponse } from "../types/corrections";

/**
 * Variables passed to the revert mutation function.
 */
export interface RevertSegmentVariables {
  /** The numeric segment ID to revert */
  segmentId: number;
}

/**
 * The API response envelope returned by the revert endpoint.
 * apiFetch returns the full envelope — the `data` key wraps CorrectionRevertResponse.
 */
interface RevertSegmentApiResponse {
  data: CorrectionRevertResponse;
}

/**
 * Hook for reverting the active correction on a transcript segment.
 *
 * Unlike useCorrectSegment, this hook does NOT apply an optimistic update.
 * The revert operation is server-confirmed only: the cache is patched after
 * the server responds with the authoritative new segment state.
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - BCP-47 language code for the transcript
 * @returns UseMutationResult for the correction revert
 *
 * @example
 * ```tsx
 * const mutation = useRevertSegment(videoId, languageCode);
 *
 * mutation.mutate({ segmentId: 42 });
 * ```
 */
export function useRevertSegment(
  videoId: string,
  languageCode: string
): UseMutationResult<RevertSegmentApiResponse, Error, RevertSegmentVariables> {
  const queryClient = useQueryClient();
  const queryKey = segmentsQueryKey(videoId, languageCode);

  return useMutation<RevertSegmentApiResponse, Error, RevertSegmentVariables>({
    mutationFn: async (variables: RevertSegmentVariables) => {
      return apiFetch<RevertSegmentApiResponse>(
        `/videos/${videoId}/transcript/segments/${variables.segmentId}/corrections/revert?language_code=${encodeURIComponent(languageCode)}`,
        {
          method: "POST",
        }
      );
    },

    onSuccess: (response, variables) => {
      // Patch cache with server-authoritative segment state
      const { segment_state, correction } = response.data;

      queryClient.setQueryData<InfiniteData<SegmentListResponse>>(
        queryKey,
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((segment) => {
                if (segment.id !== variables.segmentId) return segment;

                if (!segment_state.has_correction) {
                  // Fully reverted — no active correction remains
                  return {
                    ...segment,
                    has_correction: false,
                    text: segment_state.effective_text,
                    corrected_at: null,
                    correction_count: 0,
                  };
                } else {
                  // Partial revert — a prior correction still exists
                  return {
                    ...segment,
                    has_correction: true,
                    text: segment_state.effective_text,
                    corrected_at: correction.corrected_at,
                    correction_count: Math.max(0, segment.correction_count - 1),
                  };
                }
              }),
            })),
          };
        }
      );
    },

    onError: () => {
      // Invalidate to force a fresh fetch and ensure cache consistency
      queryClient.invalidateQueries({ queryKey });
    },
  });
}
