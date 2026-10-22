/**
 * useSharedCategoryNeighbours — data for the shared-categories panel
 * (Feature 085). Fetches independently of the entity detail page's render.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchSharedCategoryNeighbours } from "../api/entityMentions";
import type { SharedCategoryNeighbour } from "../api/entityMentions";

/** Default bound; matches the server default. */
export const SHARED_CATEGORY_PAGE_SIZE = 12;

interface UseSharedCategoryNeighboursReturn {
  neighbours: SharedCategoryNeighbour[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useSharedCategoryNeighbours(
  entityId: string | undefined,
  limit: number = SHARED_CATEGORY_PAGE_SIZE
): UseSharedCategoryNeighboursReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["sharedCategoryNeighbours", entityId ?? null, limit],
    queryFn: ({ signal }) =>
      fetchSharedCategoryNeighbours(entityId as string, limit, 0, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
  });

  return {
    neighbours: data ?? [],
    isLoading,
    isError,
    error,
  };
}
