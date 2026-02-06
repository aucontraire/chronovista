/**
 * Video data types for the Chronovista frontend.
 * These types match the backend API response schemas.
 */

/**
 * Summary of transcript availability for a video.
 */
export interface TranscriptSummary {
  /** Number of available transcripts */
  count: number;
  /** List of available language codes */
  languages: string[];
  /** Whether any transcript is manually created (not auto-generated) */
  has_manual: boolean;
}

/**
 * Video item as returned by the list API endpoint.
 */
export interface VideoListItem {
  /** 11-character YouTube video ID */
  video_id: string;
  /** Video title */
  title: string;
  /** Channel ID (may be null for deleted channels) */
  channel_id: string | null;
  /** Channel display name (may be null for deleted channels) */
  channel_title: string | null;
  /** ISO 8601 datetime string of upload date */
  upload_date: string;
  /** Video duration in seconds */
  duration: number;
  /** View count (may be null if not available) */
  view_count: number | null;
  /** Transcript availability summary */
  transcript_summary: TranscriptSummary;
}

/**
 * Extended video information for the detail page.
 */
export interface VideoDetail {
  /** 11-character YouTube video ID */
  video_id: string;
  /** Video title */
  title: string;
  /** Full description text */
  description: string;
  /** YouTube channel ID (24 chars, may be null for deleted channels) */
  channel_id: string | null;
  /** Channel display name (may be null for deleted channels) */
  channel_title: string | null;
  /** ISO 8601 datetime string of upload date */
  upload_date: string;
  /** Video duration in seconds */
  duration: number;
  /** View count (may be null if hidden) */
  view_count: number | null;
  /** Like count (may be null if hidden) */
  like_count: number | null;
  /** Comment count (may be null if disabled) */
  comment_count: number | null;
  /** Video tags */
  tags: string[];
  /** YouTube category ID */
  category_id: string | null;
  /** BCP-47 language code for default language */
  default_language: string | null;
  /** COPPA compliance flag */
  made_for_kids: boolean;
  /** Transcript availability summary */
  transcript_summary: TranscriptSummary;
}

/**
 * Pagination metadata for list responses.
 */
export interface PaginationInfo {
  /** Total number of items available */
  total: number;
  /** Number of items per page */
  limit: number;
  /** Current offset in the result set */
  offset: number;
  /** Whether more items are available */
  has_more: boolean;
}

/**
 * Response from the videos list API endpoint.
 */
export interface VideoListResponse {
  /** Array of video items */
  data: VideoListItem[];
  /** Pagination metadata (null if pagination not supported) */
  pagination: PaginationInfo | null;
}

/**
 * Response from the video detail API endpoint.
 */
export interface VideoDetailResponse {
  /** Video detail data */
  data: VideoDetail;
}

/**
 * Error types for categorizing API failures.
 */
export type ApiErrorType = "network" | "timeout" | "server" | "unknown";

/**
 * Structured API error with type classification.
 */
export interface ApiError {
  type: ApiErrorType;
  message: string;
  status?: number | undefined;
}
