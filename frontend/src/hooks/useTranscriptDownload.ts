/**
 * useTranscriptDownload mutation hook for triggering transcript downloads.
 *
 * Implements:
 * - FR-005: Cache invalidation for video detail, transcript segments, and
 *   transcript languages after a successful download
 * - NFR-002: 2-minute timeout for download operations (preference-aware
 *   downloads iterate over multiple languages — see issue #109)
 *
 * @module hooks/useTranscriptDownload
 */

import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";

import { apiFetch, TRANSCRIPT_DOWNLOAD_TIMEOUT } from "../api/config";
import type { ApiError } from "../types/video";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * Response returned by the transcript download endpoint.
 * Mirrors the backend TranscriptDownloadResponse schema.
 */
export interface TranscriptDownloadResponse {
  /** 11-character YouTube video ID */
  video_id: string;
  /** BCP-47 language code of the downloaded transcript */
  language_code: string;
  /** Human-readable language name (e.g., "English (United States)") */
  language_name: string;
  /**
   * Quality indicator for the downloaded transcript.
   * - "manual"        — human-created captions
   * - "auto_synced"   — auto-synced from uploaded transcript
   * - "auto_generated" — YouTube ASR captions
   */
  transcript_type: string;
  /** Number of segments in the downloaded transcript */
  segment_count: number;
  /** ISO 8601 datetime when the transcript was stored */
  downloaded_at: string;
}

/**
 * Variables passed to the mutation function.
 *
 * Keeping the language code inside the variables object (rather than
 * closing over it from the hook options) allows callers to trigger
 * downloads for different languages from a single hook instance without
 * re-mounting — useful when a language selector drives the mutation.
 */
export interface TranscriptDownloadVariables {
  /** Optional BCP-47 language code to request a specific transcript */
  language?: string;
}

/**
 * Options for the useTranscriptDownload hook.
 */
export interface UseTranscriptDownloadOptions {
  /** 11-character YouTube video ID — used to build the endpoint path */
  videoId: string;
}

// ---------------------------------------------------------------------------
// Timeout constant (NFR-002)
// ---------------------------------------------------------------------------

// TRANSCRIPT_DOWNLOAD_TIMEOUT imported from api/config.ts

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

/**
 * Calls the transcript download endpoint.
 *
 * @param videoId - The YouTube video ID
 * @param language - Optional BCP-47 language code
 * @returns TranscriptDownloadResponse on success
 * @throws ApiError on failure (status is preserved for HTTP error differentiation)
 */
async function downloadTranscript(
  videoId: string,
  language?: string
): Promise<TranscriptDownloadResponse> {
  const params = language ? `?language=${encodeURIComponent(language)}` : "";
  const endpoint = `/videos/${videoId}/transcript/download${params}`;

  // NFR-002: Use the apiFetch timeout option to enforce a 30s ceiling.
  // apiFetch creates its own AbortController internally and will throw an
  // ApiError with type "timeout" if the request exceeds this limit.
  return apiFetch<TranscriptDownloadResponse>(endpoint, {
    method: "POST",
    timeout: TRANSCRIPT_DOWNLOAD_TIMEOUT,
  });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Mutation hook for triggering a transcript download for a video.
 *
 * On success, invalidates three query caches so consuming components
 * automatically reflect the newly downloaded transcript:
 * - `["video", videoId]`                 — refreshes transcript_summary on detail page
 * - `["transcriptSegments", videoId, …]` — prefix-invalidated (all language variants)
 * - `["transcriptLanguages", videoId]`   — refreshes the language selector options
 *
 * Error HTTP status codes (via `error.status`) allow callers to distinguish:
 * - **503** — YouTube is temporarily rate-limiting the backend (IP block)
 * - **404** — No transcript is available for this video/language
 * - **429** — A download is already in progress for this video
 * - Other   — Generic server or network error
 *
 * @param options - Hook configuration ({ videoId })
 * @returns UseMutationResult exposing `download`, `isPending`, `isError`,
 *   `isSuccess`, `error`, `data`, and `reset`
 *
 * @example
 * ```tsx
 * const {
 *   download,
 *   isPending,
 *   isError,
 *   error,
 *   isSuccess,
 *   data,
 *   reset,
 * } = useTranscriptDownload({ videoId: 'dQw4w9WgXcQ' });
 *
 * const handleDownload = () => {
 *   download({ language: 'en' });
 * };
 *
 * if (error?.status === 503) {
 *   return <p>YouTube is temporarily blocking downloads. Try again later.</p>;
 * }
 * if (error?.status === 404) {
 *   return <p>No transcript is available for this video.</p>;
 * }
 * ```
 */
export function useTranscriptDownload(
  options: UseTranscriptDownloadOptions
): UseMutationResult<TranscriptDownloadResponse, ApiError, TranscriptDownloadVariables> {
  const { videoId } = options;
  const queryClient = useQueryClient();

  return useMutation<TranscriptDownloadResponse, ApiError, TranscriptDownloadVariables>({
    mutationFn: ({ language }: TranscriptDownloadVariables) =>
      downloadTranscript(videoId, language),

    onSuccess: async () => {
      // FR-005: Invalidate all affected caches after a successful download.
      // Run all three invalidations concurrently — they are independent.
      await Promise.all([
        // Refresh video detail (transcript_summary.count / languages list)
        queryClient.invalidateQueries({
          queryKey: ["video", videoId],
        }),
        // Invalidate ALL language variants of transcript segments by prefix
        // (exact: false is the TanStack Query v5 default for prefix matching)
        queryClient.invalidateQueries({
          queryKey: ["transcriptSegments", videoId],
          exact: false,
        }),
        // Refresh the language selector (new language becomes available)
        queryClient.invalidateQueries({
          queryKey: ["transcriptLanguages", videoId],
        }),
      ]);
    },
  });
}
