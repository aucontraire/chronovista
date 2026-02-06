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
  /** Whether an error occurred */
  isError: boolean;
  /** Error object if an error occurred */
  error: ApiError | null;
  /** Function to fetch the next page of segments */
  fetchNextPage: () => void;
  /** Function to retry after an error */
  retry: () => void;
  /** Function to cancel in-flight requests (for language switching) */
  cancelRequests: () => void;
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
    language_code: languageCode,
    offset: pageParam.offset.toString(),
    limit: pageParam.limit.toString(),
  });

  const endpoint = `/videos/${videoId}/transcript/segments?${params.toString()}`;

  // Create a timeout-specific AbortController for 5s timeout (NFR-P02)
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), 5000);

  // Combine signals if we have an external abort signal
  const combinedSignal = signal
    ? combineAbortSignals(signal, timeoutController.signal)
    : timeoutController.signal;

  try {
    const response = await apiFetch<SegmentListResponse>(endpoint, {
      signal: combinedSignal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

/**
 * Combines multiple AbortSignals into one.
 */
function combineAbortSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();

  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  return controller.signal;
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

  return {
    segments,
    totalCount,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage ?? false,
    isError: query.isError,
    error: query.error ?? null,
    fetchNextPage: query.fetchNextPage,
    retry,
    cancelRequests,
  };
}
