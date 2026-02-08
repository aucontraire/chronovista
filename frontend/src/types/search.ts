/**
 * TypeScript types for Search Page - Transcript Search
 *
 * These interfaces mirror the backend Pydantic schemas from:
 * src/chronovista/api/schemas/search.py
 */

/**
 * A single transcript segment matching the search query.
 */
export interface SearchResultSegment {
  /** Unique identifier for the segment */
  segment_id: number;

  /** YouTube video ID (11 characters) */
  video_id: string;

  /** Title of the video */
  video_title: string;

  /** Channel name (null if unknown) */
  channel_title: string | null;

  /** BCP-47 language code (e.g., "en", "es-MX") */
  language_code: string;

  /** The transcript segment text containing the match */
  text: string;

  /** Segment start time in seconds */
  start_time: number;

  /** Segment end time in seconds */
  end_time: number;

  /** Previous segment text (up to 200 chars, null if first segment) */
  context_before: string | null;

  /** Next segment text (up to 200 chars, null if last segment) */
  context_after: string | null;

  /** Number of query terms matched in this segment */
  match_count: number;

  /** ISO 8601 datetime string of video upload date */
  video_upload_date: string;
}

/**
 * Pagination metadata for infinite scroll.
 */
export interface PaginationMeta {
  /** Total number of matching results */
  total: number;

  /** Results per page */
  limit: number;

  /** Current offset in result set */
  offset: number;

  /** Whether more results are available */
  has_more: boolean;
}

/**
 * API response wrapper for search results.
 */
export interface SearchResponse {
  /** Array of matching segments */
  data: SearchResultSegment[];

  /** Pagination metadata */
  pagination: PaginationMeta;

  /** All unique languages in full result set (not just current page) */
  available_languages: string[];
}

/**
 * Available search types.
 * Phase 1: Only "transcripts" is functional.
 * Future phases will enable additional types.
 */
export type SearchType =
  | 'transcripts'
  | 'video_titles'
  | 'video_descriptions'
  | 'channels'
  | 'tags'
  | 'topics';

/**
 * Search type metadata for filter panel display.
 */
export interface SearchTypeOption {
  /** Search type identifier */
  type: SearchType;

  /** Display label */
  label: string;

  /** Whether this type is currently available */
  enabled: boolean;

  /** Result count (updated after search) */
  count?: number;
}

/**
 * Default search type options for filter panel.
 */
export const SEARCH_TYPE_OPTIONS: SearchTypeOption[] = [
  { type: 'transcripts', label: 'Transcripts', enabled: true },
  { type: 'video_titles', label: 'Video Titles', enabled: false },
  { type: 'video_descriptions', label: 'Descriptions', enabled: false },
  { type: 'channels', label: 'Channels', enabled: false },
  { type: 'tags', label: 'Tags', enabled: false },
  { type: 'topics', label: 'Topics', enabled: false },
];

/**
 * Search filter state.
 */
export interface SearchFilters {
  /** User's search query */
  query: string;

  /** Selected language filter (null for all languages) */
  language: string | null;

  /** Enabled search types */
  enabledTypes: SearchType[];
}

/**
 * Default search filters.
 */
export const DEFAULT_SEARCH_FILTERS: SearchFilters = {
  query: '',
  language: null,
  enabledTypes: ['transcripts'],
};

/**
 * Search query parameters for API calls.
 */
export interface SearchParams {
  /** Search query (2-500 characters) */
  q: string;

  /** Optional: limit to specific video */
  video_id?: string;

  /** Optional: limit to language code */
  language?: string;

  /** Results per page (1-100, default 20) */
  limit?: number;

  /** Pagination offset (default 0) */
  offset?: number;
}
