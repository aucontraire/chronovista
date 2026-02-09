/**
 * useVideoPlaylists hook for fetching playlists that contain a specific video.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import type {
  VideoPlaylistMembership,
  VideoPlaylistsResponse,
} from "../types/playlist";

/**
 * Fetches the playlists that contain a specific video.
 *
 * @param videoId - The YouTube video ID to fetch playlists for
 * @returns Array of VideoPlaylistMembership objects
 */
async function fetchVideoPlaylists(
  videoId: string
): Promise<VideoPlaylistMembership[]> {
  const response = await apiFetch<VideoPlaylistsResponse>(
    `/videos/${videoId}/playlists`
  );
  return response.data;
}

/**
 * Options for the useVideoPlaylists hook.
 */
export interface UseVideoPlaylistsOptions {
  /** Whether to enable the query (default: true) */
  enabled?: boolean;
}

/**
 * Return type for the useVideoPlaylists hook.
 */
export interface UseVideoPlaylistsReturn {
  /** Array of playlists containing the video */
  playlists: VideoPlaylistMembership[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error if any occurred */
  error: unknown;
  /** Function to retry after an error */
  retry: () => void;
}

/**
 * Hook for fetching playlists that contain a specific video.
 *
 * Uses TanStack Query's useQuery for data fetching and caching.
 * Configured with 5min staleTime and 10min gcTime matching other hooks.
 *
 * @param videoId - The YouTube video ID to fetch playlists for
 * @param options - Hook configuration options
 * @returns UseVideoPlaylistsReturn with playlists array and loading states
 *
 * @example
 * ```tsx
 * const { playlists, isLoading, error, retry } = useVideoPlaylists('dQw4w9WgXcQ');
 *
 * if (isLoading) return <LoadingSpinner />;
 * if (error) return <ErrorMessage error={error} onRetry={retry} />;
 *
 * return (
 *   <div>
 *     <h2>This video appears in {playlists.length} playlists:</h2>
 *     {playlists.map(membership => (
 *       <PlaylistLink
 *         key={membership.playlist_id}
 *         playlistId={membership.playlist_id}
 *         title={membership.title}
 *         position={membership.position}
 *       />
 *     ))}
 *   </div>
 * );
 * ```
 */
export function useVideoPlaylists(
  videoId: string,
  options: UseVideoPlaylistsOptions = {}
): UseVideoPlaylistsReturn {
  const { enabled = true } = options;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["videoPlaylists", videoId],
    queryFn: () => fetchVideoPlaylists(videoId),
    enabled: enabled && !!videoId, // Only run if enabled and videoId is truthy
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });

  return {
    playlists: data ?? [],
    isLoading,
    isError,
    error,
    retry: () => void refetch(),
  };
}
