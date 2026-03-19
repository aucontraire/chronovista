/**
 * TanStack Query hook for the diff analysis (ASR error patterns) endpoint.
 *
 * Wraps GET /api/v1/corrections/batch/diff-analysis and exposes the result
 * as a standard useQuery so components can react to loading / error / data
 * states without duplicating fetch logic.
 *
 * @module hooks/useDiffAnalysis
 */

import { useQuery } from "@tanstack/react-query";

import {
  fetchDiffAnalysis,
  type FetchDiffAnalysisParams,
} from "../api/batchCorrections";

/**
 * Fetches recurring ASR error patterns identified by word-level diff analysis.
 *
 * The query key includes the full params object so that changes to any filter
 * (e.g. entityName) automatically trigger a refetch. Callers should debounce
 * user-typed entity name input before passing it here to avoid redundant
 * network requests.
 *
 * @param params - Optional filter parameters forwarded to the API
 * @returns TanStack Query result containing an array of DiffErrorPattern items
 *
 * @example
 * ```tsx
 * const { data, isLoading, isError } = useDiffAnalysis({ entityName: "Obama" });
 * const patterns = data ?? [];
 * ```
 */
export function useDiffAnalysis(params?: FetchDiffAnalysisParams) {
  return useQuery({
    queryKey: ["diff-analysis", params],
    queryFn: ({ signal }) => fetchDiffAnalysis(params, signal),
  });
}
