/**
 * useSearchDescriptions hook for searching video descriptions.
 *
 * Uses TanStack Query's useQuery for a single static request (no pagination).
 * Query is only enabled when the search query meets minimum length AND
 * the descriptions search type is toggled on.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { SEARCH_CONFIG } from "../config/search";
import type { DescriptionSearchResponse } from "../types/search";

/**
 * Options for the useSearchDescriptions hook.
 */
export interface UseSearchDescriptionsOptions {
  /** The search query string */
  query: string;
  /** Whether the descriptions search type is enabled */
  enabled?: boolean;
}

/**
 * Return type for the useSearchDescriptions hook.
 */
export interface UseSearchDescriptionsResult {
  /** Array of description search results */
  data: DescriptionSearchResponse["data"];
  /** Total number of matching videos */
  totalCount: number;
  /** Whether the query is loading */
  isLoading: boolean;
  /** Whether the query errored */
  isError: boolean;
  /** The error if any */
  error: unknown;
  /** Function to refetch (for retry) */
  refetch: () => void;
}

/**
 * Hook for searching video descriptions.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * The query is only enabled when the search query is at least MIN_QUERY_LENGTH characters
 * AND the enabled flag is true.
 *
 * Concurrent Search Handling:
 * - TanStack Query automatically cancels previous requests when queryKey changes
 * - AbortController signal is passed to apiFetch for proper cancellation
 * - No race conditions: only the latest query results are displayed
 * - AbortError is handled gracefully by TanStack Query
 *
 * Note: Description search is capped at 50 results (DESCRIPTION_SEARCH_LIMIT).
 * No pagination needed - single static request.
 *
 * @param options - Search options including query and enabled flag
 * @returns Search results with total count and loading/error states
 *
 * @example
 * ```tsx
 * const { data, totalCount, isLoading, isError, refetch } = useSearchDescriptions({
 *   query: debouncedQuery,
 *   enabled: enabledSearchTypes.descriptions,
 * });
 *
 * return (
 *   <div>
 *     {isLoading && <LoadingSpinner />}
 *     {isError && <ErrorMessage onRetry={refetch} />}
 *     {data.map(video => (
 *       <DescriptionSearchResult key={video.video_id} video={video} />
 *     ))}
 *     {totalCount > data.length && (
 *       <p>Showing {data.length} of {totalCount} results</p>
 *     )}
 *   </div>
 * );
 * ```
 */
export function useSearchDescriptions({
  query,
  enabled = true,
}: UseSearchDescriptionsOptions): UseSearchDescriptionsResult {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["search", "descriptions", query],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        q: query,
        limit: String(SEARCH_CONFIG.DESCRIPTION_SEARCH_LIMIT),
      });
      return apiFetch<DescriptionSearchResponse>(
        `${SEARCH_CONFIG.DESCRIPTION_SEARCH_ENDPOINT}?${params}`,
        { signal }
      );
    },
    enabled: enabled && query.length >= SEARCH_CONFIG.MIN_QUERY_LENGTH,
    staleTime: SEARCH_CONFIG.SEARCH_STALE_TIME,
    gcTime: 5 * 60 * 1000,
  });

  return {
    data: data?.data ?? [],
    totalCount: data?.total_count ?? 0,
    isLoading,
    isError,
    error,
    refetch: () => void refetch(),
  };
}
