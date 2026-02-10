/**
 * useTopics hook for fetching topic hierarchy with search support.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { TopicHierarchyItem } from "../types/filters";
import { useDebounce } from "./useDebounce";

/**
 * Response from the topics hierarchy API endpoint.
 */
interface TopicsHierarchyResponse {
  /** Array of topics with hierarchy information */
  data: TopicHierarchyItem[];
}

interface UseTopicsOptions {
  /** Search term to filter topics */
  search?: string;
  /** Debounce delay in milliseconds (default: 300) */
  debounceDelay?: number;
}

interface UseTopicsReturn {
  /** Array of topics with hierarchy (filtered if search provided) */
  topics: TopicHierarchyItem[];
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
 * Hook for fetching topic hierarchy with optional search filtering.
 *
 * Fetches the full topic hierarchy from the API and filters locally if search provided.
 * Uses debouncing to reduce re-renders during user typing.
 *
 * @example
 * ```tsx
 * const [searchTerm, setSearchTerm] = useState('');
 * const { topics, isLoading } = useTopics({ search: searchTerm });
 *
 * return (
 *   <div>
 *     <input
 *       value={searchTerm}
 *       onChange={(e) => setSearchTerm(e.target.value)}
 *       placeholder="Search topics..."
 *     />
 *     {isLoading ? (
 *       <Spinner />
 *     ) : (
 *       topics.map(topic => (
 *         <div
 *           key={topic.topic_id}
 *           style={{ paddingLeft: `${topic.depth * 16}px` }}
 *         >
 *           {topic.parent_path ? `${topic.parent_path} > ` : ''}
 *           {topic.name}
 *         </div>
 *       ))
 *     )}
 *   </div>
 * );
 * ```
 */
export function useTopics(options: UseTopicsOptions = {}): UseTopicsReturn {
  const { search = "", debounceDelay = 300 } = options;

  const debouncedSearch = useDebounce(search, debounceDelay);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["topics", "hierarchy"],
    queryFn: ({ signal }) =>
      apiFetch<TopicsHierarchyResponse>("/topics/hierarchy", { signal }),
    staleTime: 10 * 60 * 1000, // 10 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
    select: (response) => {
      // Filter locally if search provided
      if (debouncedSearch) {
        const lower = debouncedSearch.toLowerCase();
        return {
          ...response,
          data: response.data.filter(
            (topic) =>
              topic.name.toLowerCase().includes(lower) ||
              (topic.parent_path?.toLowerCase().includes(lower) ?? false)
          ),
        };
      }
      return response;
    },
  });

  return {
    topics: data?.data ?? [],
    isLoading,
    isError,
    error,
    refetch: () => void refetch(),
  };
}
