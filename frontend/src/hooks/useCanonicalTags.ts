import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";

import { API_BASE_URL } from "../api/config";
import type {
  CanonicalTagListItem,
  CanonicalTagListResponse,
  CanonicalTagSuggestion,
  MatchMode,
} from "../types/canonical-tags";
import { useDebounce } from "./useDebounce";

/** Default match mode — preserves the video filter's existing behavior (FR-004). */
const DEFAULT_MATCH_MODE: MatchMode = "prefix";

/** Default result limit — preserves the video filter's existing behavior (FR-004). */
const DEFAULT_LIMIT = 10;

/** Minimum query length enforced for contains-mode search (FR-003). */
const CONTAINS_MIN_QUERY_LENGTH = 2;

interface RateLimitError extends Error {
  status: 429;
  retryAfter: number;
}

function isRateLimitError(error: unknown): error is RateLimitError {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    (error as RateLimitError).status === 429
  );
}

async function fetchCanonicalTags(
  search: string,
  signal: AbortSignal,
  matchMode: MatchMode,
  limit: number
): Promise<CanonicalTagListResponse> {
  const params = new URLSearchParams({ q: search, limit: String(limit) });
  // Only send match_mode when it differs from the backend default ("prefix")
  // so the video filter's request stays byte-for-byte identical (FR-004).
  if (matchMode !== DEFAULT_MATCH_MODE) {
    params.set("match_mode", matchMode);
  }
  const response = await fetch(
    `${API_BASE_URL}/canonical-tags?${params.toString()}`,
    { signal }
  );

  if (response.status === 429) {
    const retryAfterHeader = response.headers.get("Retry-After");
    const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 10;
    const err = Object.assign(new Error("Rate limited"), {
      status: 429 as const,
      retryAfter: isNaN(retryAfter) ? 10 : retryAfter,
    });
    throw err;
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json() as Promise<CanonicalTagListResponse>;
}

/** Optional parameters for {@link useCanonicalTags}. */
export interface UseCanonicalTagsOptions {
  /**
   * Search match mode. Defaults to `"prefix"`, preserving the video filter's
   * existing behavior (FR-004). Pass `"contains"` for merge-context variant
   * discovery (FR-005).
   */
  matchMode?: MatchMode;
  /**
   * Maximum results to request. Defaults to `10`, preserving the video
   * filter's existing behavior (FR-004). The merge UI passes `50` (FR-005).
   */
  limit?: number;
}

export function useCanonicalTags(
  search: string,
  options: UseCanonicalTagsOptions = {}
): {
  tags: CanonicalTagListItem[];
  suggestions: CanonicalTagSuggestion[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  isRateLimited: boolean;
  rateLimitRetryAfter: number;
} {
  const matchMode = options.matchMode ?? DEFAULT_MATCH_MODE;
  const limit = options.limit ?? DEFAULT_LIMIT;

  const debouncedSearch = useDebounce(search, 300);

  const [isRateLimited, setIsRateLimited] = useState(false);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState(0);

  // FR-003: contains-mode search requires a minimum query length of 2 to
  // avoid excessively broad result sets. Prefix mode keeps its original
  // "any non-empty string" threshold (FR-004 — byte-identical to before).
  const meetsMinLength =
    matchMode === "contains"
      ? debouncedSearch.length >= CONTAINS_MIN_QUERY_LENGTH
      : debouncedSearch.length > 0;

  // Only extend the query key beyond the original 2-tuple when non-default
  // options are used, so the video filter's cache entries (and any code that
  // reads the ["canonical-tags", search] key directly) stay unaffected.
  const queryKey =
    matchMode === DEFAULT_MATCH_MODE && limit === DEFAULT_LIMIT
      ? (["canonical-tags", debouncedSearch] as const)
      : (["canonical-tags", debouncedSearch, matchMode, limit] as const);

  const { data, isLoading, isError, error } = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      fetchCanonicalTags(debouncedSearch, signal, matchMode, limit),
    enabled: meetsMinLength,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
    retry: (failureCount, err) => {
      if (isRateLimitError(err)) return false;
      return failureCount < 3;
    },
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
  });

  useEffect(() => {
    if (isError && isRateLimitError(error)) {
      const retryAfter = error.retryAfter;
      setIsRateLimited(true);
      setRateLimitRetryAfter(retryAfter);
      const timer = setTimeout(() => {
        setIsRateLimited(false);
        setRateLimitRetryAfter(0);
      }, retryAfter * 1000);
      return () => clearTimeout(timer);
    }
  }, [isError, error]);

  return {
    tags: data?.data ?? [],
    suggestions: data?.suggestions ?? [],
    isLoading,
    isError,
    error: error as Error | null,
    isRateLimited,
    rateLimitRetryAfter,
  };
}
