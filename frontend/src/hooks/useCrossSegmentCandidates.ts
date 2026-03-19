/**
 * TanStack Query hook for fetching cross-segment ASR error candidates.
 *
 * Cross-segment candidates are adjacent segment pairs where an ASR error
 * spans the boundary between segments. Each candidate includes both segment
 * texts, a proposed correction, a source pattern, and a confidence score.
 *
 * @module hooks/useCrossSegmentCandidates
 */

import { useQuery } from "@tanstack/react-query";

import {
  fetchCrossSegmentCandidates,
  type FetchCrossSegmentParams,
} from "../api/batchCorrections";

/**
 * Hook that fetches cross-segment ASR error candidates.
 *
 * The query result is used by CrossSegmentPanel to display ranked candidates
 * that the user can click to pre-fill the batch find-replace form.
 *
 * @param params - Optional filter parameters (minCorrections, entityName)
 * @returns TanStack Query result for cross-segment candidates
 *
 * @example
 * ```tsx
 * const { data, isLoading, isError } = useCrossSegmentCandidates();
 * const candidates = data ?? [];
 * ```
 */
export function useCrossSegmentCandidates(params?: FetchCrossSegmentParams) {
  return useQuery({
    queryKey: ["cross-segment-candidates", params],
    queryFn: ({ signal }) => fetchCrossSegmentCandidates(params, signal),
  });
}
