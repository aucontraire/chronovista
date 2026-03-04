/**
 * useSegmentCorrectionHistory hook for fetching the audit history of corrections
 * applied to a transcript segment.
 *
 * Implements:
 * - FR-035c: Correction history display via GET endpoint
 * - Controlled fetching via the `enabled` option
 * - Always-fresh data (staleTime: 0) since history changes after each correction
 *
 * @module hooks/useSegmentCorrectionHistory
 */

import { useQuery, UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { CorrectionHistoryResponse } from "../types/corrections";

/**
 * Options for configuring the correction history query.
 */
export interface UseSegmentCorrectionHistoryOptions {
  /** Whether to fetch the history (set to false when the history panel is closed) */
  enabled: boolean;
  /** Offset for paginated results (defaults to 0) */
  offset?: number;
}

/**
 * Query key factory for segment correction history.
 *
 * Includes offset so paginated requests are cached separately.
 */
export const segmentCorrectionHistoryQueryKey = (
  videoId: string,
  languageCode: string,
  segmentId: number,
  offset: number
) =>
  [
    "segmentCorrectionHistory",
    videoId,
    languageCode,
    segmentId,
    offset,
  ] as const;

/**
 * Hook for fetching the correction history of a single transcript segment.
 *
 * The query is controlled by the `enabled` option — pass `false` to defer
 * fetching until the history panel is opened.
 *
 * staleTime is set to 0 so the history is always considered stale and will
 * re-fetch when the user opens the panel after submitting a correction.
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - BCP-47 language code for the transcript
 * @param segmentId - The numeric segment ID to fetch history for
 * @param options - Control options (enabled, offset)
 * @returns UseQueryResult with CorrectionHistoryResponse data
 *
 * @example
 * ```tsx
 * const { data, isLoading } = useSegmentCorrectionHistory(
 *   videoId,
 *   languageCode,
 *   segmentId,
 *   { enabled: isHistoryPanelOpen }
 * );
 * ```
 */
export function useSegmentCorrectionHistory(
  videoId: string,
  languageCode: string,
  segmentId: number,
  options: UseSegmentCorrectionHistoryOptions
): UseQueryResult<CorrectionHistoryResponse, Error> {
  const { enabled, offset = 0 } = options;

  return useQuery<CorrectionHistoryResponse, Error>({
    queryKey: segmentCorrectionHistoryQueryKey(
      videoId,
      languageCode,
      segmentId,
      offset
    ),
    queryFn: async () => {
      const params = new URLSearchParams({
        language_code: languageCode,
        limit: "50",
        offset: offset.toString(),
      });

      return apiFetch<CorrectionHistoryResponse>(
        `/videos/${videoId}/transcript/segments/${segmentId}/corrections?${params.toString()}`
      );
    },
    staleTime: 0,
    enabled,
  });
}
