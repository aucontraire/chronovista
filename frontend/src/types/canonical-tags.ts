export interface CanonicalTagListItem {
  canonical_form: string;
  normalized_form: string;
  alias_count: number;
  video_count: number;
}

export interface CanonicalTagSuggestion {
  canonical_form: string;
  normalized_form: string;
}

export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface CanonicalTagListResponse {
  data: CanonicalTagListItem[];
  pagination: PaginationMeta;
  suggestions?: CanonicalTagSuggestion[];
}

export interface TagAliasItem {
  raw_form: string;
  occurrence_count: number;
}

export interface CanonicalTagDetail {
  canonical_form: string;
  normalized_form: string;
  alias_count: number;
  video_count: number;
  top_aliases: TagAliasItem[];
  created_at: string;
  updated_at: string;
}

export interface CanonicalTagDetailResponse {
  data: CanonicalTagDetail;
}

export interface SelectedCanonicalTag {
  canonical_form: string;
  normalized_form: string;
  alias_count: number;
}

/**
 * Search match mode for the canonical tag list endpoint (Feature 056).
 *
 * `prefix` (default) matches from the start of tag names — used by the video
 * filter (TagAutocomplete). `contains` matches at any position — used by the
 * tag merge search (TagMergeSelector) for variant discovery.
 */
export type MatchMode = "prefix" | "contains";

/** A canonical tag candidate for merge source/target selection. */
export interface SelectedMergeTag {
  canonical_form: string;
  normalized_form: string;
  alias_count: number;
  video_count: number;
}

export interface MergePreviewRequest {
  source_normalized_forms: string[];
  target_normalized_form: string;
}

/** Exact, read-only preview of a merge's resulting counts (no mutation). */
export interface MergePreview {
  source_tags: string[];
  target_tag: string;
  resulting_alias_count: number;
  resulting_video_count: number;
  source_alias_count: number;
  source_video_count: number;
}

export interface MergePreviewResponse {
  data: MergePreview;
}

export interface MergeRequest {
  source_normalized_forms: string[];
  target_normalized_form: string;
  reason?: string;
}

/** Result of a successfully executed merge. */
export interface MergeResult {
  source_tags: string[];
  target_tag: string;
  aliases_moved: number;
  new_alias_count: number;
  new_video_count: number;
  operation_id: string;
  entity_hint: string | null;
}

export interface MergeResponse {
  data: MergeResult;
}

/** Result of undoing a previously logged tag operation (e.g. a merge). */
export interface UndoResult {
  operation_type: string;
  operation_id: string;
  details: string;
}

export interface UndoResponse {
  data: UndoResult;
}
