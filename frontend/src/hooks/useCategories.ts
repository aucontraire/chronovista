/**
 * useCategories hook for fetching video categories.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";

/**
 * Category information for dropdown selection.
 */
export interface Category {
  /** YouTube category ID */
  category_id: string;
  /** Human-readable category name */
  name: string;
  /** Whether the category is assignable by creators */
  assignable: boolean;
}

/**
 * Response from the categories API endpoint.
 */
interface CategoriesResponse {
  /** Array of category objects */
  data: Category[];
}

interface UseCategoriesReturn {
  /** Array of category objects */
  categories: Category[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
  /** Function to retry after an error */
  refetch: () => void;
}

/**
 * Hook for fetching video categories.
 *
 * Categories are relatively static data, so this hook uses a long stale time.
 * The data is cached for 30 minutes to minimize API calls.
 *
 * @example
 * ```tsx
 * const { categories, isLoading } = useCategories();
 *
 * return (
 *   <select>
 *     <option value="">All Categories</option>
 *     {categories.map(category => (
 *       <option key={category.category_id} value={category.category_id}>
 *         {category.name}
 *       </option>
 *     ))}
 *   </select>
 * );
 * ```
 */
export function useCategories(): UseCategoriesReturn {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["categories"],
    queryFn: ({ signal }) => apiFetch<CategoriesResponse>("/categories", { signal }),
    staleTime: 30 * 60 * 1000, // 30 minutes (categories rarely change)
    gcTime: 60 * 60 * 1000, // 60 minutes
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
  });

  return {
    categories: data?.data ?? [],
    isLoading,
    isError,
    error,
    refetch: () => void refetch(),
  };
}
