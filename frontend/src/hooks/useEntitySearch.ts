/**
 * useEntitySearch hook
 *
 * Fetches a short list of entities matching a debounced search string via the
 * dedicated autocomplete endpoint (GET /api/v1/entities/search).  Results
 * include `is_linked` context so the caller can show "Already linked" labels,
 * and `matched_alias` so the caller can display which alias triggered the
 * match.
 *
 * Implements:
 * - NFR-004 / T023: entity autocomplete for manual association UI (Feature 050)
 *
 * Design decisions:
 * - Minimum 2 characters before the query fires (prevents flooding the API
 *   with single-character requests against a large entity table).
 * - 300 ms debounce via useDebounce (NFR-004).
 * - staleTime: 30 s so rapid re-typing reuses cached results.
 * - Returns at most `limit` entities (default 10, max 20).
 * - Disabled when the debounced search is fewer than 2 characters.
 * - The debounce lives INSIDE this hook — callers pass the raw input value.
 *
 * @module hooks/useEntitySearch
 */

import { useQuery } from "@tanstack/react-query";
import { searchEntities } from "../api/entityMentions";
import type { EntitySearchResult } from "../api/entityMentions";
import { useDebounce } from "./useDebounce";

const MIN_SEARCH_CHARS = 2;
const DEFAULT_SEARCH_LIMIT = 10;

export interface UseEntitySearchReturn {
  /** Entity results matching the current search text */
  entities: EntitySearchResult[];
  /** True while the query is in flight */
  isLoading: boolean;
  /** True when the query has resolved (success or error) */
  isFetched: boolean;
  /** True when an error occurred */
  isError: boolean;
  /** True when the minimum character threshold has not been reached */
  isBelowMinChars: boolean;
}

/**
 * Debounced entity search hook for autocomplete UIs.
 *
 * Wraps GET /api/v1/entities/search with a 300 ms debounce.  The hook
 * is intentionally minimal — it does not own selection state.  Selection
 * state lives in the component that renders the autocomplete.
 *
 * When `videoId` is provided, the backend attaches `is_linked` context to each
 * result so the UI can show "Already linked" for entities already associated
 * with that video.
 *
 * @param search - Raw (un-debounced) search string from the input element
 * @param videoId - Optional video ID for is_linked context
 * @param limit  - Max results to return (default 10, max 20)
 * @returns Matching entities and loading/error flags
 *
 * @example
 * ```tsx
 * const { entities, isLoading, isBelowMinChars } = useEntitySearch(inputValue, videoId);
 * ```
 */
export function useEntitySearch(
  search: string,
  videoId?: string,
  limit: number = DEFAULT_SEARCH_LIMIT,
): UseEntitySearchReturn {
  const debouncedSearch = useDebounce(search, 300);
  const trimmed = debouncedSearch.trim();
  const isAboveMinChars = trimmed.length >= MIN_SEARCH_CHARS;

  const { data, isLoading, isFetched, isError } = useQuery({
    queryKey: ["entitySearch", trimmed, videoId ?? null, limit],
    queryFn: ({ signal }) => searchEntities(trimmed, videoId, limit, signal),
    enabled: isAboveMinChars,
    staleTime: 30 * 1000, // 30 s — rapid re-typing reuses cached results
    gcTime: 5 * 60 * 1000,
    // Do not retry on 4xx — autocomplete results are non-critical.
    retry: (failureCount, error) => {
      const status = (error as { status?: number }).status;
      if (status !== undefined && status < 500) return false;
      return failureCount < 2;
    },
  });

  return {
    entities: data ?? [],
    isLoading: isAboveMinChars && isLoading,
    isFetched,
    isError,
    isBelowMinChars: !isAboveMinChars,
  };
}
