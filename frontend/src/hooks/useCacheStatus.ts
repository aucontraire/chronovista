/**
 * useCacheStatus hook for querying and purging the local image cache.
 *
 * Implements:
 * - GET /api/v1/settings/cache — image cache statistics
 * - DELETE /api/v1/settings/cache — purge all cached images
 *
 * On a successful purge the cache-status query is invalidated so the UI
 * immediately reflects the empty cache without a manual refresh.
 *
 * @module hooks/useCacheStatus
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchCacheStatus,
  purgeCache as purgeCacheApi,
  type CacheStatus,
  type CachePurgeResult,
} from "../api/settings";

// ---------------------------------------------------------------------------
// Query key constant
// ---------------------------------------------------------------------------

export const CACHE_STATUS_KEY = ["cache-status"] as const;

// ---------------------------------------------------------------------------
// Public hook return type
// ---------------------------------------------------------------------------

export interface UseCacheStatusReturn {
  /** Current image cache statistics, or undefined while loading. */
  cacheStatus: CacheStatus | undefined;
  /** True while the cache-status query is fetching for the first time. */
  isLoading: boolean;
  /** Error from the cache-status query, or null. */
  error: Error | null;
  /**
   * Trigger a full cache purge (DELETE /api/v1/settings/cache).
   * The cache-status query is automatically invalidated on success.
   */
  purgeCache: () => void;
  /** True while the purge mutation is in flight. */
  isPurging: boolean;
  /** The result data from the most recent successful purge, or undefined. */
  purgeResult: CachePurgeResult | undefined;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Provides cache statistics and a purge action for the local image cache.
 *
 * @example
 * ```tsx
 * const {
 *   cacheStatus,
 *   isLoading,
 *   error,
 *   purgeCache,
 *   isPurging,
 * } = useCacheStatus();
 *
 * if (isLoading) return <Spinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return (
 *   <div>
 *     <p>{cacheStatus?.total_size_display}</p>
 *     <button onClick={purgeCache} disabled={isPurging}>
 *       {isPurging ? "Purging…" : "Clear cache"}
 *     </button>
 *   </div>
 * );
 * ```
 */
export function useCacheStatus(): UseCacheStatusReturn {
  const queryClient = useQueryClient();

  // ------------------------------------------------------------------
  // Query: cache statistics
  // ------------------------------------------------------------------
  const cacheStatusQuery = useQuery<
    Awaited<ReturnType<typeof fetchCacheStatus>>,
    Error
  >({
    queryKey: CACHE_STATUS_KEY,
    queryFn: ({ signal }) => fetchCacheStatus(signal),
    staleTime: 30 * 1000, // 30 seconds — cache size can change frequently
  });

  // ------------------------------------------------------------------
  // Mutation: purge cache
  // ------------------------------------------------------------------
  const purgeMutation = useMutation<
    Awaited<ReturnType<typeof purgeCacheApi>>,
    Error,
    void
  >({
    mutationFn: () => purgeCacheApi(),
    onSuccess: () => {
      // Invalidate so the GET query re-fetches and reflects the cleared cache
      queryClient.invalidateQueries({ queryKey: CACHE_STATUS_KEY });
    },
  });

  // ------------------------------------------------------------------
  // Derived state
  // ------------------------------------------------------------------
  const cacheStatus = cacheStatusQuery.data?.data;
  const isLoading = cacheStatusQuery.isLoading;
  const error: Error | null = cacheStatusQuery.error as Error | null;
  const purgeResult = purgeMutation.data?.data;

  return {
    cacheStatus,
    isLoading,
    error,
    purgeCache: () => purgeMutation.mutate(),
    isPurging: purgeMutation.isPending,
    purgeResult,
  };
}
