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
 * @returns VideoDetail data
 */
async function fetchVideoDetail(videoId: string): Promise<VideoDetail> {
  const response = await apiFetch<VideoDetailResponse>(`/videos/${videoId}`);
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
    queryFn: () => fetchVideoDetail(videoId),
    staleTime: 10 * 1000, // 10 seconds (NFR-P01)
    enabled: !!videoId, // Only run if videoId is truthy
  });
}
