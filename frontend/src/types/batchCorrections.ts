/**
 * Batch corrections domain types for the batch correction tools CLI/API (Feature 036).
 * These types match the backend API response schemas for the batch correction endpoints:
 *   POST /api/v1/corrections/batch/preview
 *   POST /api/v1/corrections/batch/apply
 *   POST /api/v1/corrections/batch/rebuild-text
 */

// ---------------------------------------------------------------------------
// Preview endpoint — POST /api/v1/corrections/batch/preview
// ---------------------------------------------------------------------------

/** Request body for the batch preview endpoint. */
export interface BatchPreviewRequest {
  /** Literal string or regex pattern to search for. */
  pattern: string;
  /** Replacement string (may use backreferences when is_regex is true). */
  replacement: string;
  /** Treat pattern as a regular expression. Defaults to false on the backend. */
  is_regex?: boolean;
  /** Perform a case-insensitive match. Defaults to false on the backend. */
  case_insensitive?: boolean;
  /** Allow matches that span adjacent segments. Defaults to false on the backend. */
  cross_segment?: boolean;
  /** Restrict matches to segments in this BCP-47 language code. */
  language?: string | null;
  /** Restrict matches to segments belonging to this channel. */
  channel_id?: string | null;
  /** Restrict matches to segments belonging to these video IDs. */
  video_ids?: string[] | null;
}

/** A single match returned by the preview endpoint. */
export interface BatchPreviewMatch {
  /** Database primary key of the transcript segment. */
  segment_id: number;
  /** YouTube video ID the segment belongs to. */
  video_id: string;
  /** Human-readable title of the video. */
  video_title: string;
  /** Human-readable title of the channel. */
  channel_title: string;
  /** BCP-47 language code of the segment. */
  language_code: string;
  /** Start time of the segment in seconds. */
  start_time: number;
  /** Current (pre-correction) text of the segment. */
  current_text: string;
  /** Text after the proposed replacement is applied. */
  proposed_text: string;
  /** Character offset where the match starts within current_text. */
  match_start: number;
  /** Character offset where the match ends (exclusive) within current_text. */
  match_end: number;
  /** Text immediately before the match for display context. */
  context_before: string | null;
  /** Text immediately after the match for display context. */
  context_after: string | null;
  /** True when the segment already has a pending correction record. */
  has_existing_correction: boolean;
  /** True when this match spans two adjacent segments. */
  is_cross_segment: boolean;
  /** Opaque identifier linking the two halves of a cross-segment match pair. */
  pair_id: string | null;
  /** Frontend deep-link URL to the video at the correct timestamp. */
  deep_link_url: string;
}

/** Response envelope returned by the preview endpoint. */
export interface BatchPreviewResponse {
  /** All matches found for the given pattern/filters. */
  matches: BatchPreviewMatch[];
  /** Total number of matches (equals matches.length — no server-side pagination). */
  total_count: number;
  /** Echo of the pattern from the request. */
  pattern: string;
  /** Echo of the replacement from the request. */
  replacement: string;
  /** Whether regex mode was active. */
  is_regex: boolean;
  /** Whether case-insensitive mode was active. */
  case_insensitive: boolean;
  /** Whether cross-segment mode was active. */
  cross_segment: boolean;
}

// ---------------------------------------------------------------------------
// Apply endpoint — POST /api/v1/corrections/batch/apply
// ---------------------------------------------------------------------------

/** Request body for the batch apply endpoint. */
export interface BatchApplyRequest {
  /** Literal string or regex pattern to apply. */
  pattern: string;
  /** Replacement string. */
  replacement: string;
  /** Treat pattern as a regular expression. Defaults to false on the backend. */
  is_regex?: boolean;
  /** Perform a case-insensitive match. Defaults to false on the backend. */
  case_insensitive?: boolean;
  /** Allow corrections that span adjacent segments. Defaults to false on the backend. */
  cross_segment?: boolean;
  /** Segment IDs (from a prior preview) to apply the correction to. */
  segment_ids: number[];
  /** Correction type label to attach to each audit record. */
  correction_type?: string;
  /** Optional human-readable note to attach to each audit record. */
  correction_note?: string | null;
  /** Trigger a full-text rebuild for affected videos after applying. Defaults to true on the backend. */
  auto_rebuild?: boolean;
  /** Optional entity UUID to associate the correction with a named entity (Feature 043). */
  entity_id?: string;
}

/** Response returned by the batch apply endpoint. */
export interface BatchApplyResult {
  /** Number of segments successfully corrected. */
  total_applied: number;
  /** Number of segments skipped (e.g. already corrected, no match). */
  total_skipped: number;
  /** Number of segments that encountered an error during apply. */
  total_failed: number;
  /** Segment IDs that could not be corrected. */
  failed_segment_ids: number[];
  /** Distinct video IDs whose segments were modified. */
  affected_video_ids: string[];
  /** Whether a full-text rebuild was triggered for affected videos. */
  rebuild_triggered: boolean;
}

// ---------------------------------------------------------------------------
// Rebuild endpoint — POST /api/v1/corrections/batch/rebuild-text
// ---------------------------------------------------------------------------

/** Request body for the batch rebuild-text endpoint. */
export interface BatchRebuildRequest {
  /** Video IDs whose full-text fields should be rebuilt from their segments. */
  video_ids: string[];
}

/** Response returned by the batch rebuild-text endpoint. */
export interface BatchRebuildResult {
  /** Number of videos successfully rebuilt. */
  videos_rebuilt: number;
  /** Video IDs that were successfully rebuilt. */
  video_ids: string[];
  /** Video IDs that failed to rebuild. */
  failed_video_ids: string[];
}
