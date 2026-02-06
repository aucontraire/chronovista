/**
 * Transcript data types for the Chronovista frontend.
 * These types match the backend API response schemas for transcript functionality.
 */

import type { PaginationInfo } from "./video";

/**
 * Quality indicator for transcript source.
 * - "manual": Human-created captions (highest quality)
 * - "auto_synced": Auto-synced from uploaded transcript
 * - "auto_generated": YouTube's automatic speech recognition
 */
export type TranscriptType = "manual" | "auto_synced" | "auto_generated";

/**
 * Available transcript language with quality indicator.
 * Represents a single transcript option for a video.
 */
export interface TranscriptLanguage {
  /** BCP-47 language code (e.g., "en-US", "es") */
  language_code: string;
  /** Human-readable display name (e.g., "English (US)") */
  language_name: string;
  /** Quality indicator for the transcript source */
  transcript_type: TranscriptType;
  /** Whether this transcript can be auto-translated to other languages */
  is_translatable: boolean;
  /** ISO 8601 datetime when the transcript was downloaded */
  downloaded_at: string;
}

/**
 * Full transcript text for a video in a specific language.
 * Contains the complete transcript content and metadata.
 */
export interface Transcript {
  /** 11-character YouTube video ID */
  video_id: string;
  /** BCP-47 language code */
  language_code: string;
  /** Quality indicator for the transcript source */
  transcript_type: TranscriptType;
  /** Complete transcript text content */
  full_text: string;
  /** Number of segments in this transcript */
  segment_count: number;
  /** ISO 8601 datetime when the transcript was downloaded */
  downloaded_at: string;
}

/**
 * Individual transcript segment with timestamp.
 * Represents a single timed text segment within a transcript.
 */
export interface TranscriptSegment {
  /** Unique segment identifier */
  id: number;
  /** Segment text content */
  text: string;
  /** Start time in seconds */
  start_time: number;
  /** End time in seconds */
  end_time: number;
  /** Duration in seconds (end_time - start_time) */
  duration: number;
}

/**
 * API response wrapper for available transcript languages.
 */
export interface TranscriptLanguagesResponse {
  /** Array of available transcript languages */
  data: TranscriptLanguage[];
}

/**
 * API response wrapper for a full transcript.
 */
export interface TranscriptResponse {
  /** Full transcript data */
  data: Transcript;
}

/**
 * API response wrapper for transcript segments with pagination.
 * Used for infinite scroll loading of transcript segments.
 */
export interface SegmentListResponse {
  /** Array of transcript segments */
  data: TranscriptSegment[];
  /** Pagination metadata for infinite scroll */
  pagination: PaginationInfo;
}
