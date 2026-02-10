/**
 * useTags hook for fetching video tags with autocomplete support.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import { useDebounce } from "./useDebounce";

/**
 * Single tag item from the API.
 */
interface TagItem {
  /** The tag string */
  tag: string;
  /** Number of videos with this tag */
  video_count: number;
}

/**
 * Response from the tags API endpoint.
 */
interface TagsResponse {
  /** Array of tag items */
  data: TagItem[];
  /** Fuzzy match suggestions when no exact matches found */
  suggestions?: string[];
}

interface UseTagsOptions {
  /** Search term to filter tags */
  search?: string;
  /** Debounce delay in milliseconds (default: 300) */
  debounceDelay?: number;
}

interface UseTagsReturn {
  /** Array of tag strings matching the search */
  tags: string[];
  /** Fuzzy match suggestions when no exact matches found */
  suggestions: string[];
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
 * Hook for fetching video tags with autocomplete support.
 *
 * Uses debouncing to reduce API calls during user typing.
 * Only fetches when search term is non-empty.
 *
 * @example
 * ```tsx
 * const [searchTerm, setSearchTerm] = useState('');
 * const { tags, isLoading } = useTags({ search: searchTerm });
 *
 * return (
 *   <input
 *     value={searchTerm}
 *     onChange={(e) => setSearchTerm(e.target.value)}
 *     placeholder="Search tags..."
 *   />
 *   {isLoading ? <Spinner /> : tags.map(tag => <div key={tag}>{tag}</div>)}
 * );
 * ```
 */
export function useTags(options: UseTagsOptions = {}): UseTagsReturn {
  const { search = "", debounceDelay = 300 } = options;

  const debouncedSearch = useDebounce(search, debounceDelay);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["tags", debouncedSearch],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams();
      if (debouncedSearch) params.set("q", debouncedSearch);

      return apiFetch<TagsResponse>(`/tags?${params.toString()}`, { signal });
    },
    enabled: debouncedSearch.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
  });

  // Extract tag strings from the API response objects
  const tags = (data?.data ?? []).map((item) => item.tag);

  // Extract fuzzy suggestions when no exact matches found
  const suggestions = data?.suggestions ?? [];

  return {
    tags,
    suggestions,
    isLoading,
    isError,
    error,
    refetch: () => void refetch(),
  };
}
