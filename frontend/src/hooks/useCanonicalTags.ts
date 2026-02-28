import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";

import { API_BASE_URL } from "../api/config";
import type {
  CanonicalTagListItem,
  CanonicalTagListResponse,
  CanonicalTagSuggestion,
} from "../types/canonical-tags";
import { useDebounce } from "./useDebounce";

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
  signal: AbortSignal
): Promise<CanonicalTagListResponse> {
  const params = new URLSearchParams({ q: search, limit: "10" });
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

export function useCanonicalTags(search: string): {
  tags: CanonicalTagListItem[];
  suggestions: CanonicalTagSuggestion[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  isRateLimited: boolean;
  rateLimitRetryAfter: number;
} {
  const debouncedSearch = useDebounce(search, 300);

  const [isRateLimited, setIsRateLimited] = useState(false);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState(0);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["canonical-tags", debouncedSearch],
    queryFn: ({ signal }) => fetchCanonicalTags(debouncedSearch, signal),
    enabled: debouncedSearch.length > 0,
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
