/**
 * useTranscriptLanguages hook for fetching available transcript languages for a video.
 */

import { useQuery, UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { ApiError } from "../types/video";
import type {
  TranscriptLanguage,
  TranscriptLanguagesResponse,
} from "../types/transcript";

/**
 * Fetches available transcript languages for a video from the API.
 *
 * @param videoId - The YouTube video ID to fetch languages for
 * @returns Array of TranscriptLanguage data
 */
async function fetchTranscriptLanguages(
  videoId: string
): Promise<TranscriptLanguage[]> {
  const response = await apiFetch<TranscriptLanguagesResponse>(
    `/videos/${videoId}/transcript/languages`
  );
  return response.data;
}

/**
 * Hook for fetching available transcript languages for a video.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Configured with a 5 minute staleTime for efficient caching.
 *
 * @param videoId - The YouTube video ID to fetch languages for
 * @returns UseQueryResult with TranscriptLanguage array or ApiError
 *
 * @example
 * ```tsx
 * const { data: languages, isLoading, error } = useTranscriptLanguages('dQw4w9WgXcQ');
 *
 * if (isLoading) return <LoadingSpinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return (
 *   <div>
 *     {languages.map(lang => (
 *       <span key={lang.language_code}>{lang.language_name}</span>
 *     ))}
 *   </div>
 * );
 * ```
 */
export function useTranscriptLanguages(
  videoId: string
): UseQueryResult<TranscriptLanguage[], ApiError> {
  return useQuery<TranscriptLanguage[], ApiError>({
    queryKey: ["transcriptLanguages", videoId],
    queryFn: () => fetchTranscriptLanguages(videoId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: !!videoId, // Only run if videoId is truthy
  });
}
