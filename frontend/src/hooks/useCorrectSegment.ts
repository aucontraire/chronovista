/**
 * useCorrectSegment hook for submitting transcript segment corrections.
 *
 * Implements:
 * - US-10: Optimistic update for immediate feedback before server confirmation
 * - FR-035a: Correction submission via POST endpoint
 * - Cache patch with server-authoritative values on success
 * - Rollback on error with cache invalidation
 *
 * @module hooks/useCorrectSegment
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
import type {
  CorrectionSubmitRequest,
  CorrectionSubmitResponse,
  CorrectionType,
} from "../types/corrections";

/**
 * Variables passed to the mutation function.
 */
export interface CorrectSegmentVariables {
  /** The numeric segment ID to correct */
  segmentId: number;
  /** The corrected text to submit */
  corrected_text: string;
  /** The category of correction being made */
  correction_type: CorrectionType;
  /** An optional note explaining the correction rationale */
  correction_note: string | null;
}

/**
 * The API response envelope returned by the submit endpoint.
 * apiFetch returns the full envelope — the `data` key wraps CorrectionSubmitResponse.
 */
interface CorrectSegmentApiResponse {
  data: CorrectionSubmitResponse;
}

/**
 * Hook for submitting a correction for a transcript segment.
 *
 * Applies an optimistic cache update immediately (US-10) and then overwrites
 * with server-authoritative values on success. Rolls back to the pre-mutation
 * snapshot on error.
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - BCP-47 language code for the transcript
 * @returns UseMutationResult for the correction submission
 *
 * @example
 * ```tsx
 * const mutation = useCorrectSegment(videoId, languageCode);
 *
 * mutation.mutate({
 *   segmentId: 42,
 *   corrected_text: "Corrected text here",
 *   correction_type: "proper_noun",
 *   correction_note: null,
 * });
 * ```
 */
export function useCorrectSegment(
  videoId: string,
  languageCode: string
): UseMutationResult<
  CorrectSegmentApiResponse,
  Error,
  CorrectSegmentVariables,
  { previousData: InfiniteData<SegmentListResponse> | undefined }
> {
  const queryClient = useQueryClient();
  const queryKey = segmentsQueryKey(videoId, languageCode);

  return useMutation<
    CorrectSegmentApiResponse,
    Error,
    CorrectSegmentVariables,
    { previousData: InfiniteData<SegmentListResponse> | undefined }
  >({
    mutationFn: async (variables: CorrectSegmentVariables) => {
      const { segmentId, corrected_text, correction_type, correction_note } =
        variables;

      const requestBody: CorrectionSubmitRequest = {
        corrected_text,
        correction_type,
        correction_note,
      };

      return apiFetch<CorrectSegmentApiResponse>(
        `/videos/${videoId}/transcript/segments/${segmentId}/corrections?language_code=${encodeURIComponent(languageCode)}`,
        {
          method: "POST",
          body: JSON.stringify(requestBody),
        }
      );
    },

    onMutate: async (variables: CorrectSegmentVariables) => {
      // Cancel any in-flight segment queries to prevent cache overwrites
      await queryClient.cancelQueries({ queryKey });

      // Snapshot current cache before applying the optimistic update
      const previousData =
        queryClient.getQueryData<InfiniteData<SegmentListResponse>>(queryKey);

      // Apply optimistic patch: update the target segment immediately
      queryClient.setQueryData<InfiniteData<SegmentListResponse>>(
        queryKey,
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((segment) =>
                segment.id === variables.segmentId
                  ? {
                      ...segment,
                      has_correction: true,
                      text: variables.corrected_text,
                      corrected_at: new Date().toISOString(),
                      correction_count: segment.correction_count + 1,
                    }
                  : segment
              ),
            })),
          };
        }
      );

      return { previousData };
    },

    onError: (
      _error,
      _variables,
      context
    ) => {
      // Restore the pre-mutation snapshot on failure
      if (context?.previousData !== undefined) {
        queryClient.setQueryData(queryKey, context.previousData);
      }
      // Invalidate to ensure cache is consistent with server state
      queryClient.invalidateQueries({ queryKey });
    },

    onSuccess: (response, variables) => {
      // Overwrite optimistic values with server-authoritative data
      const { segment_state, correction } = response.data;

      queryClient.setQueryData<InfiniteData<SegmentListResponse>>(
        queryKey,
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((segment) =>
                segment.id === variables.segmentId
                  ? {
                      ...segment,
                      has_correction: true,
                      text: segment_state.effective_text,
                      corrected_at: correction.corrected_at,
                      correction_count: segment.correction_count,
                    }
                  : segment
              ),
            })),
          };
        }
      );
    },
  });
}
