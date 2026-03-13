/**
 * useEntitySearch hook
 *
 * Fetches a short list of active entities matching a debounced search string,
 * including alias matching (search_aliases=true) while excluding ASR-error
 * aliases (exclude_alias_types=asr_error).
 *
 * Implements:
 * - FR-010 / FR-025 (T022–T023): entity autocomplete for batch corrections
 *
 * Design decisions:
 * - Minimum 2 characters before the query fires (prevents flooding the API
 *   with single-character requests against a large entity table).
 * - 300 ms debounce (matches the pattern used in useCanonicalTags).
 * - staleTime: 60 s so rapid re-typing reuses cached results.
 * - Returns at most 10 entities (limit=10 sent in query string).
 * - Disabled when the debounced search is fewer than 2 characters.
 *
 * @module hooks/useEntitySearch
 */

import { useQuery } from "@tanstack/react-query";
import { fetchEntities } from "../api/entityMentions";
import type { EntityListItem } from "../api/entityMentions";
import { useDebounce } from "./useDebounce";

const MIN_SEARCH_CHARS = 2;
const SEARCH_LIMIT = 10;

export interface UseEntitySearchReturn {
  /** Entity results matching the current search text */
  entities: EntityListItem[];
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
 * The hook is intentionally minimal — it does not own selection state.
 * Selection state lives in the component that renders the autocomplete.
 *
 * @param search - Raw (un-debounced) search string from the input element
 * @returns Matching entities and loading/error flags
 *
 * @example
 * ```tsx
 * const { entities, isLoading } = useEntitySearch(inputValue);
 * ```
 */
export function useEntitySearch(search: string): UseEntitySearchReturn {
  const debouncedSearch = useDebounce(search, 300);
  const isAboveMinChars = debouncedSearch.trim().length >= MIN_SEARCH_CHARS;

  const { data, isLoading, isFetched, isError } = useQuery({
    queryKey: [
      "entity-search-autocomplete",
      debouncedSearch.trim(),
    ],
    queryFn: ({ signal }) =>
      fetchEntities(
        {
          search: debouncedSearch.trim(),
          search_aliases: true,
          exclude_alias_types: "asr_error",
          status: "active",
          limit: SEARCH_LIMIT,
        },
        signal
      ),
    enabled: isAboveMinChars,
    staleTime: 60 * 1000, // 60 s — rapid re-typing reuses cached results
    gcTime: 5 * 60 * 1000,
    // Do not retry on 4xx — autocomplete results are non-critical.
    retry: (failureCount, error) => {
      const status = (error as { status?: number }).status;
      if (status !== undefined && status < 500) return false;
      return failureCount < 2;
    },
  });

  return {
    entities: data?.data ?? [],
    isLoading,
    isFetched,
    isError,
    isBelowMinChars: !isAboveMinChars,
  };
}
