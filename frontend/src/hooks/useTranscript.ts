/**
 * useTranscript hook for fetching full transcript text.
 *
 * Fetches the complete transcript for a video in a specific language.
 * Used by the full-text view mode in the transcript panel.
 *
 * @module hooks/useTranscript
 */

import { useQuery, UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { ApiError } from "../types/video";
import type { Transcript, TranscriptResponse } from "../types/transcript";

/**
 * Fetches the full transcript for a video in a specific language.
 *
 * @param videoId - The YouTube video ID
 * @param languageCode - The BCP-47 language code
 * @returns Transcript data
 */
async function fetchTranscript(
  videoId: string,
  languageCode: string
): Promise<Transcript> {
  const response = await apiFetch<TranscriptResponse>(
    `/videos/${videoId}/transcript?language=${encodeURIComponent(languageCode)}`
  );
  return response.data;
}

/**
 * Hook for fetching the full transcript text for a video.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Configured with a 10 second timeout per NFR-P01 requirements.
 *
 * @param videoId - The YouTube video ID to fetch transcript for
 * @param languageCode - The BCP-47 language code for the transcript
 * @returns UseQueryResult with Transcript data or ApiError
 *
 * @example
 * ```tsx
 * const { data: transcript, isLoading, error } = useTranscript('dQw4w9WgXcQ', 'en');
 *
 * if (isLoading) return <LoadingSpinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return <TranscriptFullText transcript={transcript} />;
 * ```
 */
export function useTranscript(
  videoId: string,
  languageCode: string
): UseQueryResult<Transcript, ApiError> {
  return useQuery<Transcript, ApiError>({
    queryKey: ["transcript", videoId, languageCode],
    queryFn: () => fetchTranscript(videoId, languageCode),
    staleTime: 10 * 1000, // 10 seconds (NFR-P01)
    enabled: !!videoId && !!languageCode, // Only run if both parameters are truthy
  });
}
