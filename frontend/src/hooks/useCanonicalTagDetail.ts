/**
 * Hooks for fetching canonical tag details and resolving raw tags.
 */

import { useQuery } from "@tanstack/react-query";

import { API_BASE_URL, isApiError } from "../api/config";
import type {
  CanonicalTagDetail,
  CanonicalTagListItem,
  CanonicalTagListResponse,
  CanonicalTagDetailResponse,
} from "../types/canonical-tags";

/**
 * Return shape for useCanonicalTagDetail.
 */
interface UseCanonicalTagDetailReturn {
  /** The canonical tag detail, or null if not found or not yet loaded */
  data: CanonicalTagDetail | null;
  /** Whether the initial fetch is in progress */
  isLoading: boolean;
  /** Whether a non-404 error occurred */
  isError: boolean;
}

/**
 * Return shape for useResolveRawTag.
 */
interface UseResolveRawTagReturn {
  /** The first matching canonical tag list item, or null if no match */
  data: CanonicalTagListItem | null;
  /** Whether the initial fetch is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
}

/**
 * Fetches the canonical tag detail for a given normalized form.
 *
 * Returns null data (not an error) when the tag is not found (HTTP 404).
 * Only fires the query when `normalizedForm` is non-empty.
 *
 * @param normalizedForm - The normalized form of the canonical tag (e.g. "javascript")
 * @returns Query state with `data`, `isLoading`, and `isError`
 *
 * @example
 * ```tsx
 * const { data, isLoading, isError } = useCanonicalTagDetail("javascript");
 *
 * if (isLoading) return <Spinner />;
 * if (isError) return <ErrorMessage />;
 * if (!data) return <p>Tag not found.</p>;
 * return <p>{data.canonical_form} — {data.video_count} videos</p>;
 * ```
 */
export function useCanonicalTagDetail(
  normalizedForm: string
): UseCanonicalTagDetailReturn {
  const { data, isLoading, isError } = useQuery<CanonicalTagDetail | null>({
    queryKey: ["canonical-tag-detail", normalizedForm],
    queryFn: async ({ signal }) => {
      const url = `${API_BASE_URL}/canonical-tags/${encodeURIComponent(normalizedForm)}?alias_limit=5`;

      const response = await fetch(url, {
        signal,
        headers: { "Content-Type": "application/json" },
      });

      // Treat 404 as "not found" rather than an error
      if (response.status === 404) {
        return null;
      }

      if (!response.ok) {
        throw new Error(
          `Failed to fetch canonical tag: ${response.status} ${response.statusText}`
        );
      }

      const json = (await response.json()) as CanonicalTagDetailResponse;
      return json.data;
    },
    enabled: normalizedForm.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
    retry: (failureCount, error) => {
      // Do not retry on 404-equivalent null returns or client errors
      if (isApiError(error) && error.status !== undefined && error.status < 500) {
        return false;
      }
      return failureCount < 3;
    },
  });

  return {
    data: data ?? null,
    isLoading,
    isError,
  };
}

/**
 * Resolves a raw tag string to its canonical tag list item via the search endpoint.
 *
 * Queries the canonical-tags list endpoint with the raw tag as the search term
 * and returns the first result, or null when no match is found.
 * Only fires the query when `rawTag` is non-empty.
 *
 * @param rawTag - The raw tag string to resolve (e.g. "JavaScript")
 * @returns Query state with `data` as the first matching list item or null
 *
 * @example
 * ```tsx
 * const { data, isLoading } = useResolveRawTag("JavaScript");
 *
 * if (isLoading) return <Spinner />;
 * if (!data) return <p>No canonical tag found.</p>;
 * return <p>Canonical: {data.canonical_form}</p>;
 * ```
 */
export function useResolveRawTag(rawTag: string): UseResolveRawTagReturn {
  const { data, isLoading, isError } = useQuery<CanonicalTagListItem | null>({
    queryKey: ["canonical-tag-resolve", rawTag],
    queryFn: async ({ signal }) => {
      const url = `${API_BASE_URL}/canonical-tags?q=${encodeURIComponent(rawTag)}&limit=1`;

      const response = await fetch(url, {
        signal,
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        throw new Error(
          `Failed to resolve raw tag: ${response.status} ${response.statusText}`
        );
      }

      const json = (await response.json()) as CanonicalTagListResponse;
      return json.data[0] ?? null;
    },
    enabled: rawTag.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
  });

  return {
    data: data ?? null,
    isLoading,
    isError,
  };
}
