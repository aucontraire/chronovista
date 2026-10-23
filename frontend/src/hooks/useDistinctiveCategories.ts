/**
 * useDistinctiveCategories — data for the distinctive-categories panel
 * (Feature 089). Fetches independently of the entity detail page's render.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchDistinctiveCategories } from "../api/entityMentions";
import type { DistinctiveCategory } from "../api/entityMentions";

/** Default bound; matches the server default. */
export const DISTINCTIVE_CATEGORY_PAGE_SIZE = 50;

interface UseDistinctiveCategoriesReturn {
  categories: DistinctiveCategory[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useDistinctiveCategories(
  entityId: string | undefined,
  limit: number = DISTINCTIVE_CATEGORY_PAGE_SIZE
): UseDistinctiveCategoriesReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["distinctiveCategories", entityId ?? null, limit],
    queryFn: ({ signal }) =>
      fetchDistinctiveCategories(entityId as string, limit, 0, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
    // Keep the current chips (and the focused "Show more" button) mounted
    // while a larger page loads.
    placeholderData: keepPreviousData,
  });

  return {
    categories: data ?? [],
    isLoading,
    isError,
    error,
  };
}
