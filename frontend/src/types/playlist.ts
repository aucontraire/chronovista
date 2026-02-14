/**
 * Playlist data types for the Chronovista frontend.
 * These types match the backend API response schemas.
 */

import type { TranscriptSummary } from "./video";

/**
 * Pagination metadata for list responses.
 */
export interface PaginationMeta {
  /** Total number of items matching query */
  total: number;
  /** Items per page */
  limit: number;
  /** Current offset */
  offset: number;
  /** More items available (offset + limit < total) */
  has_more: boolean;
}

/**
 * Privacy status for playlists.
 */
export type PlaylistPrivacyStatus = "public" | "private" | "unlisted";

/**
 * Filter type for playlist list view.
 */
export type PlaylistFilterType = "all" | "linked" | "local";

/**
 * Sort field for playlist list view.
 */
export type PlaylistSortField = "title" | "created_at" | "video_count";

/**
 * Sort order direction.
 */
export type SortOrder = "asc" | "desc";

/**
 * Combined sort option for UI display.
 */
export interface PlaylistSortOption {
  /** Sort field */
  field: PlaylistSortField;
  /** Sort order */
  order: SortOrder;
  /** Display label */
  label: string;
}

/**
 * Playlist summary for list responses.
 *
 * The is_linked field is derived at runtime from the playlist_id prefix:
 * - true if ID starts with PL, LL, WL, or HL (YouTube-linked)
 * - false if ID starts with int_ (internal/unlinked)
 */
export interface PlaylistListItem {
  /** Playlist ID (YouTube, system, or internal) */
  playlist_id: string;
  /** Playlist title */
  title: string;
  /** Playlist description */
  description: string | null;
  /** Number of videos in playlist */
  video_count: number;
  /** Privacy status: public, private, or unlisted */
  privacy_status: PlaylistPrivacyStatus;
  /** Whether playlist is linked to YouTube */
  is_linked: boolean;
}

/**
 * Full playlist details for single resource response.
 *
 * Extends PlaylistListItem with additional fields including
 * channel ownership, timestamps, and playlist type.
 */
export interface PlaylistDetail extends PlaylistListItem {
  /** Default language code */
  default_language: string | null;
  /** Owner channel ID */
  channel_id: string | null;
  /** Playlist creation date (ISO 8601) */
  published_at: string | null;
  /** Whether playlist is marked deleted */
  deleted_flag: boolean;
  /** Playlist type (e.g., "regular", "watch_later") */
  playlist_type: string;
  /** Record creation timestamp (ISO 8601) */
  created_at: string;
  /** Last update timestamp (ISO 8601) */
  updated_at: string;
}

/**
 * Video item in playlist context with position.
 *
 * Extends video information with playlist-specific position
 * and includes deleted_flag to preserve position integrity.
 */
export interface PlaylistVideoItem {
  /** YouTube video ID (11 chars) */
  video_id: string;
  /** Video title */
  title: string;
  /** Channel ID (24 chars) */
  channel_id: string | null;
  /** Channel name */
  channel_title: string | null;
  /** Video upload date (ISO 8601) */
  upload_date: string;
  /** Duration in seconds */
  duration: number;
  /** View count */
  view_count: number | null;
  /** Transcript availability summary */
  transcript_summary: TranscriptSummary;
  /** Position in playlist (0-indexed) */
  position: number;
  /** Content availability status */
  availability_status: string;
}

/**
 * Video playlist membership information.
 *
 * Used for showing which playlists contain a specific video.
 */
export interface VideoPlaylistMembership {
  /** Playlist ID */
  playlist_id: string;
  /** Playlist title */
  title: string;
  /** Position in playlist (0-indexed) */
  position: number;
  /** Whether playlist is linked to YouTube */
  is_linked: boolean;
  /** Playlist privacy status */
  privacy_status: string;
}

/**
 * Response from the playlists list API endpoint.
 */
export interface PlaylistListResponse {
  /** Array of playlist items */
  data: PlaylistListItem[];
  /** Pagination metadata */
  pagination: PaginationMeta;
}

/**
 * Response from the playlist detail API endpoint.
 */
export interface PlaylistDetailResponse {
  /** Playlist detail data */
  data: PlaylistDetail;
}

/**
 * Response from the playlist videos list API endpoint.
 */
export interface PlaylistVideoListResponse {
  /** Array of video items with playlist positions */
  data: PlaylistVideoItem[];
  /** Pagination metadata */
  pagination: PaginationMeta;
}

/**
 * Response from the video playlists API endpoint.
 *
 * Returns all playlists that contain a specific video.
 */
export interface VideoPlaylistsResponse {
  /** Array of playlist membership items */
  data: VideoPlaylistMembership[];
  /** Pagination metadata */
  pagination: PaginationMeta;
}
