/**
 * useVideoDetail hook for fetching a single video's details.
 */

import { useQuery, UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { ApiError, VideoDetail, VideoDetailResponse } from "../types/video";

/**
 * Fetches video details from the API.
 *
 * @param videoId - The YouTube video ID to fetch
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns VideoDetail data
 */
async function fetchVideoDetail(videoId: string, signal?: AbortSignal): Promise<VideoDetail> {
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  const response = await apiFetch<VideoDetailResponse>(`/videos/${videoId}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return response.data;
}

/**
 * Hook for fetching a single video's detailed information.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Configured with a 10 second staleTime per NFR-P01 requirements.
 *
 * @param videoId - The YouTube video ID to fetch
 * @returns UseQueryResult with VideoDetail data or ApiError
 *
 * @example
 * ```tsx
 * const { data: video, isLoading, error } = useVideoDetail('dQw4w9WgXcQ');
 *
 * if (isLoading) return <LoadingSpinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return <VideoDetailView video={video} />;
 * ```
 */
export function useVideoDetail(videoId: string): UseQueryResult<VideoDetail, ApiError> {
  return useQuery<VideoDetail, ApiError>({
    queryKey: ["video", videoId],
    queryFn: ({ signal }) => fetchVideoDetail(videoId, signal),
    staleTime: 10 * 1000, // 10 seconds (NFR-P01)
    enabled: !!videoId, // Only run if videoId is truthy
  });
}
