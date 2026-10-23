/**
 * useAllCategories — data for the "All categories" panel (Feature 090).
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchEntityCategories } from "../api/entityMentions";
import type { EntityCategoryWithCount } from "../api/entityMentions";

/** Default bound; matches the server default. */
export const DEFAULT_ENTITY_CATEGORIES_PAGE_SIZE = 50;

interface UseAllCategoriesReturn {
  categories: EntityCategoryWithCount[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useAllCategories(
  entityId: string | undefined,
  limit: number = DEFAULT_ENTITY_CATEGORIES_PAGE_SIZE
): UseAllCategoriesReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["allCategories", entityId ?? null, limit],
    queryFn: ({ signal }) =>
      fetchEntityCategories(entityId as string, limit, 0, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
    // Keep the current list (and the focused "Show more" button) mounted
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
