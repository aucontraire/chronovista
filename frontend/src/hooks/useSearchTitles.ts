/**
 * useSearchTitles hook for searching video titles.
 *
 * Uses TanStack Query's useQuery for a single static request (no pagination).
 * Query is only enabled when the search query meets minimum length AND
 * the titles search type is toggled on.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { SEARCH_CONFIG } from "../config/search";
import type { TitleSearchResponse } from "../types/search";

/**
 * Options for the useSearchTitles hook.
 */
export interface UseSearchTitlesOptions {
  /** The search query string */
  query: string;
  /** Whether the titles search type is enabled */
  enabled?: boolean;
  /** Include unavailable content (T031, FR-021) */
  includeUnavailable?: boolean;
}

/**
 * Return type for the useSearchTitles hook.
 */
export interface UseSearchTitlesResult {
  /** Array of title search results */
  data: TitleSearchResponse["data"];
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
 * Hook for searching video titles.
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
 * Note: Title search is capped at 50 results (TITLE_SEARCH_LIMIT).
 * No pagination needed - single static request.
 *
 * @param options - Search options including query and enabled flag
 * @returns Search results with total count and loading/error states
 *
 * @example
 * ```tsx
 * const { data, totalCount, isLoading, isError, refetch } = useSearchTitles({
 *   query: debouncedQuery,
 *   enabled: enabledSearchTypes.titles,
 * });
 *
 * return (
 *   <div>
 *     {isLoading && <LoadingSpinner />}
 *     {isError && <ErrorMessage onRetry={refetch} />}
 *     {data.map(video => (
 *       <TitleSearchResult key={video.video_id} video={video} />
 *     ))}
 *     {totalCount > data.length && (
 *       <p>Showing {data.length} of {totalCount} results</p>
 *     )}
 *   </div>
 * );
 * ```
 */
export function useSearchTitles({
  query,
  enabled = true,
  includeUnavailable = false,
}: UseSearchTitlesOptions): UseSearchTitlesResult {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["search", "titles", query, includeUnavailable],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        q: query,
        limit: String(SEARCH_CONFIG.TITLE_SEARCH_LIMIT),
      });

      // T031: Add include_unavailable parameter (FR-021)
      if (includeUnavailable) {
        params.set("include_unavailable", "true");
      }

      return apiFetch<TitleSearchResponse>(
        `${SEARCH_CONFIG.TITLE_SEARCH_ENDPOINT}?${params}`,
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
