/**
 * Hooks for fetching canonical tag details and resolving raw tags.
 */

import { useQuery } from "@tanstack/react-query";

import { API_BASE_URL, isApiError } from "../api/config";
import type {
  CanonicalTagDetail,
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
      const url = `${API_BASE_URL}/canonical-tags/${encodeURIComponent(normalizedForm)}?alias_limit=10`;

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
