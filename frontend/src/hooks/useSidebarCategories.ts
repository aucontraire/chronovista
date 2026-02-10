/**
 * useSidebarCategories hook for fetching categories for sidebar navigation.
 *
 * This hook provides categories with video counts for sidebar display,
 * formatted for navigation with pre-built href links.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";

/**
 * Category information for sidebar navigation.
 */
export interface SidebarCategory {
  /** YouTube category ID */
  category_id: string;
  /** Human-readable category name */
  name: string;
  /** Number of videos in this category */
  video_count: number;
  /** Navigation URL (e.g., '/videos?category=10') */
  href: string;
}

/**
 * Response from the sidebar categories API endpoint.
 */
interface SidebarCategoriesResponse {
  /** Array of category objects with video counts */
  data: SidebarCategory[];
}

/**
 * Fetches sidebar categories from the API.
 *
 * Returns categories ordered by video_count descending,
 * including only categories with at least one video by default.
 */
async function fetchSidebarCategories(): Promise<SidebarCategoriesResponse> {
  return apiFetch<SidebarCategoriesResponse>("/sidebar/categories");
}

interface UseSidebarCategoriesReturn {
  /** Array of category objects with video counts */
  categories: SidebarCategory[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
}

/**
 * Hook for fetching sidebar categories with video counts.
 *
 * Categories are relatively static data with video counts that change over time,
 * so this hook uses a moderate stale time. The data is cached for 30 minutes
 * to minimize API calls while keeping counts reasonably fresh.
 *
 * @example
 * ```tsx
 * const { categories, isLoading } = useSidebarCategories();
 *
 * return (
 *   <div>
 *     {categories.map(category => (
 *       <Link key={category.category_id} to={category.href}>
 *         {category.name} ({category.video_count})
 *       </Link>
 *     ))}
 *   </div>
 * );
 * ```
 */
export function useSidebarCategories(): UseSidebarCategoriesReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["sidebar", "categories"],
    queryFn: fetchSidebarCategories,
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 60 minutes
  });

  return {
    categories: data?.data ?? [],
    isLoading,
    isError,
    error,
  };
}
