/**
 * useCategoryDetail — category identity for the category page (Feature 086).
 */

import { useQuery } from "@tanstack/react-query";

import { fetchCategoryDetail } from "../api/wikipediaCategories";
import type { CategoryDetail } from "../api/wikipediaCategories";
import type { ApiError } from "../types/video";

interface UseCategoryDetailReturn {
  category: CategoryDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  /** True when the API answered 404 (malformed or unknown id). */
  isNotFound: boolean;
  error: ApiError | null;
  retry: () => void;
}

export function useCategoryDetail(
  categoryId: string | undefined
): UseCategoryDetailReturn {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["wikipediaCategory", categoryId ?? null],
    queryFn: ({ signal }) => fetchCategoryDetail(categoryId as string, signal),
    enabled: Boolean(categoryId),
    staleTime: 60 * 1000,
    // A 404 is a definitive answer; retrying it only delays the not-found state.
    retry: (failureCount, err) =>
      (err as Partial<ApiError>).status !== 404 && failureCount < 3,
  });

  const apiError = (error as ApiError | null) ?? null;

  return {
    category: data,
    isLoading,
    isError,
    isNotFound: isError && apiError?.status === 404,
    error: apiError,
    retry: () => void refetch(),
  };
}
