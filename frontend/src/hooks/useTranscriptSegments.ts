/**
 * useTranscriptSegments hook for fetching transcript segments with infinite scroll.
 *
 * Implements:
 * - FR-020a: Initial batch of 50 segments
 * - FR-020b: Subsequent batches of 25 segments
 * - NFR-P02: 5 second timeout for segment batch loads
 * - NFR-P04-P06: Request cancellation on language change
 *
 * @module hooks/useTranscriptSegments
 */

import {
  InfiniteData,
  useInfiniteQuery,
  UseInfiniteQueryResult,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "../api/config";
import { INFINITE_SCROLL_CONFIG, DEBOUNCE_CONFIG } from "../styles/tokens";
import type { ApiError } from "../types/video";
import type { TranscriptSegment, SegmentListResponse } from "../types/transcript";

/**
 * Query key factory for transcript segments.
 */
export const segmentsQueryKey = (videoId: string, languageCode: string) =>
  ["transcriptSegments", videoId, languageCode] as const;

/**
 * Page parameter structure for infinite query.
 */
interface PageParam {
  offset: number;
  limit: number;
}

/**
 * Return type for the useTranscriptSegments hook.
 * Extends the base infinite query result with helper properties.
 */
export interface UseTranscriptSegmentsResult {
  /** All loaded segments flattened into a single array */
  segments: TranscriptSegment[];
  /** Total number of segments available */
  totalCount: number;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether fetching the next page */
  isFetchingNextPage: boolean;
  /** Whether there are more segments to load */
  hasNextPage: boolean;
  /** Whether fetching the previous page (bidirectional paging around a deep-link window) */
  isFetchingPreviousPage: boolean;
  /** Whether there are earlier segments to load (bidirectional paging around a deep-link window) */
  hasPreviousPage: boolean;
  /** Whether an error occurred */
  isError: boolean;
  /** Error object if an error occurred */
  error: ApiError | null;
  /** Function to fetch the next page of segments */
  fetchNextPage: () => void;
  /** Function to fetch the previous (earlier) page of segments */
  fetchPreviousPage: () => void;
  /** Function to retry after an error */
  retry: () => void;
  /** Function to cancel in-flight requests (for language switching) */
  cancelRequests: () => void;
  /**
   * Seek to a target timestamp for deep-link navigation. Resets the
   * infinite-query cache to a single, contiguous, offset-paginated window
   * centered on the target instead of appending a disjoint time-windowed
   * page — this is what fixes the timestamp-discontinuity bug (a gap of
   * un-fetched segments between the offset-0 pages and the appended page).
   * Subsequent fetchNextPage/fetchPreviousPage calls page contiguously by
   * pure offset from this window in either direction.
   */
  seekToTimestamp: (targetTimestamp: number) => Promise<boolean>;
}

/**
 * Fetches a page of transcript segments from the API.
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - BCP-47 language code
 * @param pageParam - Pagination parameters (offset and limit)
 * @param signal - AbortSignal for request cancellation
 * @returns SegmentListResponse with segments and pagination info
 */
async function fetchSegments(
  videoId: string,
  languageCode: string,
  pageParam: PageParam,
  signal?: AbortSignal
): Promise<SegmentListResponse> {
  const params = new URLSearchParams({
    language: languageCode, // Backend expects 'language', not 'language_code'
    offset: pageParam.offset.toString(),
    limit: pageParam.limit.toString(),
  });

  const endpoint = `/videos/${videoId}/transcript/segments?${params.toString()}`;

  // NFR-P02: 5s timeout for segment batch loads — stricter than the global 10s.
  // FR-004/FR-005: The TanStack Query signal and the 5s timeout are combined via
  // AbortSignal.any() inside apiFetch when both are passed as externalSignal.
  // We use AbortSignal.any() here to merge the two external signals before
  // passing them, keeping apiFetch's own timeout guard as the fallback.
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), 5000);

  // Merge the 5s segment timeout with the TanStack Query signal (if present).
  const mergedExternal: AbortSignal = signal
    ? AbortSignal.any([signal, timeoutController.signal])
    : timeoutController.signal;

  try {
    const response = await apiFetch<SegmentListResponse>(endpoint, {
      externalSignal: mergedExternal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

/**
 * Hook for fetching transcript segments with infinite scroll support.
 *
 * Features:
 * - Initial batch of 50 segments (FR-020a)
 * - Subsequent batches of 25 segments (FR-020b)
 * - Automatic request cancellation on language change (NFR-P04-P06)
 * - Debounced language switching (NFR-P05)
 * - Error handling with retry capability
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - BCP-47 language code for the transcript
 * @param enabled - Whether to enable the query (default: true)
 * @returns UseTranscriptSegmentsResult with segments and control functions
 *
 * @example
 * ```tsx
 * const {
 *   segments,
 *   isLoading,
 *   hasNextPage,
 *   fetchNextPage,
 *   isFetchingNextPage,
 * } = useTranscriptSegments(videoId, selectedLanguage);
 *
 * // Use Intersection Observer to trigger fetchNextPage
 * ```
 */
export function useTranscriptSegments(
  videoId: string,
  languageCode: string,
  enabled: boolean = true
): UseTranscriptSegmentsResult {
  const queryClient = useQueryClient();
  const previousLanguageRef = useRef<string>(languageCode);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cancel previous requests when language changes (NFR-P04)
  useEffect(() => {
    if (previousLanguageRef.current !== languageCode) {
      // Cancel in-flight requests for the previous language
      queryClient.cancelQueries({
        queryKey: segmentsQueryKey(videoId, previousLanguageRef.current),
      });

      previousLanguageRef.current = languageCode;
    }
  }, [videoId, languageCode, queryClient]);

  // Cleanup debounce timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, []);

  const query: UseInfiniteQueryResult<InfiniteData<SegmentListResponse, PageParam>, ApiError> =
    useInfiniteQuery<SegmentListResponse, ApiError, InfiniteData<SegmentListResponse, PageParam>, readonly [string, string, string], PageParam>({
      queryKey: segmentsQueryKey(videoId, languageCode),
      queryFn: async ({ pageParam, signal }) => {
        // Apply debounce for language switching (NFR-P05)
        if (pageParam.offset === 0 && debounceTimeoutRef.current === null) {
          await new Promise<void>((resolve) => {
            debounceTimeoutRef.current = setTimeout(() => {
              debounceTimeoutRef.current = null;
              resolve();
            }, DEBOUNCE_CONFIG.languageSwitch);
          });
        }

        return fetchSegments(videoId, languageCode, pageParam, signal);
      },
      initialPageParam: {
        offset: 0,
        limit: INFINITE_SCROLL_CONFIG.initialBatchSize,
      },
      getNextPageParam: (lastPage) => {
        if (!lastPage.pagination.has_more) {
          return undefined;
        }
        return {
          offset: lastPage.pagination.offset + lastPage.pagination.limit,
          limit: INFINITE_SCROLL_CONFIG.subsequentBatchSize,
        };
      },
      // Bidirectional paging: lets scrolling UP from a deep-link window load
      // earlier segments. Always offset-based (never start_time-based), so
      // every page — forward or backward — is contiguous with its neighbors.
      // Contiguous by construction: previousOffset + previousLimit === the
      // current first page's offset, so there is never a gap or overlap.
      getPreviousPageParam: (_firstPage, _allPages, firstPageParam) => {
        if (firstPageParam.offset <= 0) {
          return undefined;
        }
        const previousLimit = Math.min(
          INFINITE_SCROLL_CONFIG.subsequentBatchSize,
          firstPageParam.offset
        );
        const previousOffset = firstPageParam.offset - previousLimit;
        return { offset: previousOffset, limit: previousLimit };
      },
      enabled: enabled && !!videoId && !!languageCode,
      staleTime: 5 * 60 * 1000, // 5 minutes
    });

  // Flatten all pages into a single array of segments
  const segments: TranscriptSegment[] =
    query.data?.pages.flatMap((page) => page.data) ?? [];

  // Get total count from the first page's pagination
  const totalCount = query.data?.pages[0]?.pagination.total ?? 0;

  // Cancel requests function for external use (e.g., language selector)
  const cancelRequests = useCallback(() => {
    queryClient.cancelQueries({
      queryKey: segmentsQueryKey(videoId, languageCode),
    });
  }, [queryClient, videoId, languageCode]);

  // Retry function for error recovery
  const retry = useCallback(() => {
    query.refetch();
  }, [query]);

  // Fetches a single page with a 5s timeout, wired through apiFetch's
  // `externalSignal` (NOT `signal` — apiFetch only merges caller cancellation
  // via `externalSignal`; a bare `signal` in fetchOptions is silently
  // overwritten by apiFetch's own internal AbortController).
  const fetchWithTimeout = useCallback(
    (searchParams: URLSearchParams): Promise<SegmentListResponse> => {
      const endpoint = `/videos/${videoId}/transcript/segments?${searchParams.toString()}`;
      const timeoutController = new AbortController();
      const timeoutId = setTimeout(() => timeoutController.abort(), 5000);
      return apiFetch<SegmentListResponse>(endpoint, {
        externalSignal: timeoutController.signal,
      }).finally(() => clearTimeout(timeoutId));
    },
    [videoId]
  );

  // Seek to a target timestamp for deep-link navigation (batch find-&-replace
  // results and the search page both land here via `?seg=&t=`).
  //
  // Computes the target's ABSOLUTE offset without guessing:
  //   full_total     = pagination.total from an offset=0 (no start_time) call
  //   filtered_total = pagination.total from a start_time=target call
  //                    (count of segments AT/AFTER the target — segments are
  //                    ordered ASC by start_time, so these are the LAST
  //                    `filtered_total` rows of the full ordered set)
  //   absoluteOffset = full_total − filtered_total
  //
  // Then RESETS the infinite-query cache (does not append) to a single,
  // contiguous, pure-offset window centered on that absolute offset. This is
  // the fix for the timestamp-discontinuity bug: the old implementation
  // appended a start_time-windowed page after the offset-0 pages already in
  // the cache, leaving an un-fetched gap between them that the flattened,
  // unsorted render made visible as a timestamp jump. Because every page
  // (including the ones fetchNextPage/fetchPreviousPage load afterward) is
  // now pure offset paging from this window, there is no gap in either
  // scroll direction.
  //
  // Returns true if the window was fetched and installed successfully.
  const seekToTimestamp = useCallback(
    async (targetTimestamp: number): Promise<boolean> => {
      try {
        const [fullTotalResponse, filteredTotalResponse] = await Promise.all([
          fetchWithTimeout(
            new URLSearchParams({ language: languageCode, offset: "0", limit: "1" })
          ),
          fetchWithTimeout(
            new URLSearchParams({
              language: languageCode,
              start_time: targetTimestamp.toString(),
              offset: "0",
              limit: "1",
            })
          ),
        ]);

        const fullTotal = fullTotalResponse.pagination.total;
        const filteredTotal = filteredTotalResponse.pagination.total;
        if (fullTotal === 0) return false;

        const absoluteOffset = Math.max(0, fullTotal - filteredTotal);
        const radius = INFINITE_SCROLL_CONFIG.deepLinkWindowRadius;
        const windowOffset = Math.max(0, absoluteOffset - radius);
        const windowLimit = radius * 2;

        const windowData = await fetchWithTimeout(
          new URLSearchParams({
            language: languageCode,
            offset: windowOffset.toString(),
            limit: windowLimit.toString(),
          })
        );

        if (windowData.data.length === 0) return false;

        // Reset — not append — so the cache holds exactly this contiguous
        // window and nothing else.
        const qKey = segmentsQueryKey(videoId, languageCode);
        queryClient.setQueryData<InfiniteData<SegmentListResponse, PageParam>>(qKey, {
          pages: [windowData],
          pageParams: [
            { offset: windowData.pagination.offset, limit: windowData.pagination.limit },
          ],
        });
        return true;
      } catch {
        return false;
      }
    },
    [videoId, languageCode, queryClient, fetchWithTimeout]
  );

  return {
    segments,
    totalCount,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage ?? false,
    isFetchingPreviousPage: query.isFetchingPreviousPage,
    hasPreviousPage: query.hasPreviousPage ?? false,
    isError: query.isError,
    error: query.error ?? null,
    fetchNextPage: query.fetchNextPage,
    fetchPreviousPage: query.fetchPreviousPage,
    retry,
    cancelRequests,
    seekToTimestamp,
  };
}
