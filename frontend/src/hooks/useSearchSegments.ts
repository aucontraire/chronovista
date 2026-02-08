/**
 * useSearchSegments hook for searching transcript segments with infinite scroll.
 *
 * Uses TanStack Query's useInfiniteQuery for paginated search results.
 * Query is only enabled when the search query meets minimum length requirements.
 */

import { useInfiniteQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { SEARCH_CONFIG } from "../config/search";
import type { SearchResponse } from "../types/search";

/**
 * Options for the useSearchSegments hook.
 */
export interface UseSearchSegmentsOptions {
  /** The search query string */
  query: string;
  /** Optional language filter (BCP-47 code) */
  language?: string | null;
}

/**
 * Return type for the useSearchSegments hook.
 */
export interface UseSearchSegmentsResult {
  /** All loaded search result pages flattened */
  segments: SearchResponse["data"];
  /** Total number of matching results */
  total: number | null;
  /** Number of segments currently loaded */
  loadedCount: number;
  /** All unique languages in full result set (from API) */
  availableLanguages: string[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
  /** Whether more pages are available */
  hasNextPage: boolean;
  /** Whether a next page is currently being fetched */
  isFetchingNextPage: boolean;
  /** Function to manually fetch the next page */
  fetchNextPage: () => void;
}

/**
 * Hook for searching transcript segments with infinite scroll support.
 *
 * Uses TanStack Query's useInfiniteQuery for data fetching and caching.
 * The query is only enabled when the search query is at least MIN_QUERY_LENGTH characters.
 *
 * Concurrent Search Handling (T057, FR-023, EC-019):
 * - TanStack Query automatically cancels previous requests when queryKey changes
 * - AbortController signal is passed to apiFetch for proper cancellation
 * - No race conditions: only the latest query results are displayed
 * - AbortError is handled gracefully by TanStack Query
 *
 * Note: Special characters in the query are handled by the backend (EC-005).
 * No frontend escaping is needed.
 *
 * @param options - Search options including query and optional language filter
 * @returns Search results with pagination support
 *
 * @example
 * ```tsx
 * const { segments, isLoading, fetchNextPage, hasNextPage } = useSearchSegments({
 *   query: debouncedQuery,
 *   language: 'en',
 * });
 *
 * return (
 *   <div>
 *     {segments.map(segment => (
 *       <SearchResult key={segment.segment_id} segment={segment} />
 *     ))}
 *     {hasNextPage && <button onClick={fetchNextPage}>Load More</button>}
 *   </div>
 * );
 * ```
 */
export function useSearchSegments({
  query,
  language,
}: UseSearchSegmentsOptions): UseSearchSegmentsResult {
  const {
    data,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: ["search", "segments", query, language],
    queryFn: async ({ pageParam = 0, signal }) => {
      const params = new URLSearchParams({
        q: query,
        limit: String(SEARCH_CONFIG.PAGE_SIZE),
        offset: String(pageParam),
      });

      if (language) {
        params.set("language", language);
      }

      // T057: Pass signal for request cancellation (EC-019)
      // TanStack Query automatically cancels when queryKey changes
      return apiFetch<SearchResponse>(`/search/segments?${params}`, { signal });
    },
    getNextPageParam: (lastPage) => {
      // T059: Safely handle malformed backend response (EC-017)
      try {
        if (
          lastPage?.pagination?.has_more &&
          typeof lastPage.pagination.offset === "number" &&
          typeof lastPage.pagination.limit === "number"
        ) {
          return lastPage.pagination.offset + lastPage.pagination.limit;
        }
        return undefined;
      } catch {
        // Malformed response - stop pagination
        return undefined;
      }
    },
    enabled: query.length >= SEARCH_CONFIG.MIN_QUERY_LENGTH,
    initialPageParam: 0,
    staleTime: 2 * 60 * 1000, // 2 minutes - searches can change frequently
    gcTime: 5 * 60 * 1000, // 5 minutes
  });

  // T059: Safely flatten pages with fallback for malformed responses (EC-017)
  let segments: SearchResponse["data"] = [];
  try {
    segments = data?.pages?.flatMap((page) => page?.data ?? []) ?? [];
  } catch {
    // Malformed response structure - return empty array
    segments = [];
  }

  // T059: Safely extract pagination metadata and available languages (EC-017)
  let total: number | null = null;
  let availableLanguages: string[] = [];
  try {
    const lastPage = data?.pages?.[data.pages.length - 1];
    total = typeof lastPage?.pagination?.total === "number"
      ? lastPage.pagination.total
      : null;
    // Extract available_languages from the most recent page response
    // This field contains ALL languages in the full result set, not just current page
    availableLanguages = Array.isArray(lastPage?.available_languages)
      ? lastPage.available_languages
      : [];
  } catch {
    // Malformed response - keep defaults
    total = null;
    availableLanguages = [];
  }

  const loadedCount = segments.length;

  return {
    segments,
    total,
    loadedCount,
    availableLanguages,
    isLoading,
    isError,
    error,
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    fetchNextPage: () => void fetchNextPage(),
  };
}
