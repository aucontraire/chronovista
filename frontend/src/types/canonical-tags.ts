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
