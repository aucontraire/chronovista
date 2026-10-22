/**
 * useCategoryEntities — paginated members of a category with
 * IntersectionObserver-driven incremental loading (Feature 086).
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { fetchCategoryEntities } from "../api/wikipediaCategories";
import type { CategoryEntity } from "../api/wikipediaCategories";
import type { ApiError } from "../types/video";

export const CATEGORY_ENTITIES_PAGE_SIZE = 25;
const INTERSECTION_THRESHOLD = 0.8;

interface UseCategoryEntitiesReturn {
  entities: CategoryEntity[];
  total: number | null;
  isLoading: boolean;
  isError: boolean;
  error: ApiError | null;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  retry: () => void;
  loadMoreRef: React.RefObject<HTMLDivElement | null>;
}

export function useCategoryEntities(
  categoryId: string | undefined
): UseCategoryEntitiesReturn {
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const {
    data,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["wikipediaCategoryEntities", categoryId ?? null],
    queryFn: ({ pageParam, signal }) =>
      fetchCategoryEntities(
        categoryId as string,
        { limit: CATEGORY_ENTITIES_PAGE_SIZE, offset: pageParam },
        signal
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.pagination.has_more
        ? lastPage.pagination.offset + lastPage.pagination.limit
        : undefined,
    enabled: Boolean(categoryId),
    staleTime: 60 * 1000,
  });

  const entities = data?.pages.flatMap((p) => p.data) ?? [];
  const lastPage = data?.pages[data.pages.length - 1];

  const handleIntersect = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  useEffect(() => {
    const element = loadMoreRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (observed) => {
        if (observed[0]?.isIntersecting) {
          handleIntersect();
        }
      },
      { threshold: INTERSECTION_THRESHOLD, rootMargin: "100px" }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [handleIntersect]);

  return {
    entities,
    total: lastPage?.pagination.total ?? null,
    isLoading,
    isError,
    error: (error as ApiError | null) ?? null,
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    retry: () => void refetch(),
    loadMoreRef,
  };
}
