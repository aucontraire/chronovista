/**
 * usePlaylistDetail hook for fetching a single playlist's details.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type { PlaylistDetail, PlaylistDetailResponse } from "../types/playlist";
import type { ApiError } from "../types/video";

/**
 * Fetches a playlist's details from the API.
 *
 * @param playlistId - The playlist ID to fetch
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns PlaylistDetailResponse with data field
 */
async function fetchPlaylistDetail(
  playlistId: string,
  signal?: AbortSignal
): Promise<PlaylistDetailResponse> {
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  return apiFetch<PlaylistDetailResponse>(`/playlists/${playlistId}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

/**
 * Return type for usePlaylistDetail hook.
 */
export interface UsePlaylistDetailReturn {
  /** Playlist detail data (null if not yet loaded) */
  playlist: PlaylistDetail | null;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
  /** Function to retry/refetch playlist details */
  retry: () => void;
}

/**
 * Hook for fetching a single playlist's details.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Configured with a 5 minute staleTime for playlist metadata.
 * Handles 404 errors separately from other errors for specialized UI treatment.
 *
 * @param playlistId - The playlist ID to fetch
 * @returns Object containing playlist data, loading state, error state, and retry function
 *
 * @example
 * ```tsx
 * const { playlist, isLoading, isError, error, retry } = usePlaylistDetail(playlistId);
 *
 * if (isLoading) return <LoadingSpinner />;
 * if (isError && error?.status === 404) {
 *   return <NotFound />;
 * }
 * if (isError) {
 *   return <ErrorMessage onRetry={retry} />;
 * }
 *
 * return <PlaylistDetailView playlist={playlist} />;
 * ```
 */
export function usePlaylistDetail(playlistId: string): UsePlaylistDetailReturn {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<PlaylistDetailResponse, ApiError>({
    queryKey: ["playlist", playlistId],
    queryFn: async ({ signal }) => {
      if (!playlistId) {
        throw new Error("Playlist ID is required");
      }
      // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
      return fetchPlaylistDetail(playlistId, signal);
    },
    enabled: Boolean(playlistId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime in v4)
  });

  return {
    playlist: data?.data ?? null,
    isLoading,
    isError,
    error,
    retry: () => void refetch(),
  };
}
