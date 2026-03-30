/**
 * API client functions for entity mention endpoints.
 *
 * Covers:
 * - GET /api/v1/videos/{video_id}/entities — video entity summary
 * - GET /api/v1/entities/{entity_id}/videos — entity-to-videos lookup
 */

import { apiFetch, SCAN_TIMEOUT } from "./config";
import type { PhoneticMatch } from "../types/corrections";

// ---------------------------------------------------------------------------
// Response types (match backend EntityMentions schemas)
// ---------------------------------------------------------------------------

/** Summary of a named entity's mentions within a single video. */
export interface VideoEntitySummary {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  mention_count: number;
  /** Timestamp of the first transcript mention; null for manual-only associations. */
  first_mention_time: number | null;
  /** Mention sources present for this entity, e.g. ["transcript", "manual"]. */
  sources: string[];
  /** Whether a manual association exists for this entity on this video. */
  has_manual: boolean;
}

/** Response envelope for GET /api/v1/videos/{video_id}/entities */
export interface VideoEntitiesResponse {
  data: VideoEntitySummary[];
}

/** Preview of a single mention occurrence in a transcript segment. */
export interface MentionPreview {
  segment_id: number;
  start_time: number;
  mention_text: string;
}

/** A single video result in the entity-to-videos lookup. */
export interface EntityVideoResult {
  video_id: string;
  video_title: string;
  channel_name: string;
  /** Number of transcript-derived mentions (excludes manual). */
  mention_count: number;
  mentions: MentionPreview[];
  /**
   * Detection method categories present for this video–entity association.
   *
   * Known values:
   * - `"transcript"` — entity was detected in a transcript segment via scan
   * - `"manual"` — user created a manual association via the UI
   * - `"tag"` — video is tagged with the entity's canonical tag (Feature 053)
   * - `"title"` — entity was detected in the video title (Feature 054)
   * - `"description"` — entity was detected in the video description (Feature 054)
   *
   * A single video may have multiple sources (e.g. `["transcript", "tag"]`).
   * Tag-only videos have `mention_count: 0`, `mentions: []`, and
   * `first_mention_time: null`.
   */
  sources: string[];
  /** Whether a manual association exists for this entity on this video. */
  has_manual: boolean;
  /** Earliest transcript mention timestamp; null for manual-only or tag-only videos. */
  first_mention_time: number | null;
  /** Video upload date (ISO 8601) for sort ordering. */
  upload_date: string | null;
  /**
   * Context snippet (~150 chars) surrounding the description match.
   * Only present when `"description"` is in `sources`; null otherwise.
   * The entity text within the snippet may be highlighted by the UI.
   * This field is optional for backward compatibility with pre-Feature-054 API responses.
   */
  description_context?: string | null;
}

/** Pagination metadata */
export interface EntityPaginationMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

/** Paginated response envelope for GET /api/v1/entities/{entity_id}/videos */
export interface EntityVideoResponse {
  data: EntityVideoResult[];
  pagination: EntityPaginationMeta;
}

// ---------------------------------------------------------------------------
// Entity list types (for GET /api/v1/entities)
// ---------------------------------------------------------------------------

/** Summary of a single alias for a named entity (genuine aliases only — asr_error excluded). */
export interface EntityAliasSummary {
  alias_name: string;
  /** name_variant | abbreviation | nickname | translated_name | former_name */
  alias_type: string;
  occurrence_count: number;
}

/** A single item in the entity list response. */
export interface EntityListItem {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  mention_count: number;
  video_count: number;
}

/** Full detail response for GET /api/v1/entities/{entity_id} */
export interface EntityDetail {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  mention_count: number;
  video_count: number;
  aliases: EntityAliasSummary[];
  /** Text phrases that should NOT trigger mention detection for this entity. */
  exclusion_patterns: string[];
}

/** Paginated response envelope for GET /api/v1/entities */
export interface EntityListResponse {
  data: EntityListItem[];
  pagination: EntityPaginationMeta;
}

/** Query parameters for the entity list endpoint. */
export interface FetchEntitiesParams {
  /** Filter by entity type (e.g. "person", "organization", "place") */
  type?: string;
  /** Only include entities that have at least one mention */
  has_mentions?: boolean;
  /** Search term matched against canonical_name (and alias_name when search_aliases=true) */
  search?: string;
  /** Sort field: "name" or "mentions" */
  sort?: string;
  /** Max results per page */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
  /**
   * Filter by entity status (active, merged, deprecated).
   * Defaults to "active" on the backend when omitted.
   */
  status?: string;
  /**
   * When true, also search entity_aliases.alias_name (ILIKE) in addition to
   * canonical_name. Requires the T022 backend extension (Feature 043).
   */
  search_aliases?: boolean;
  /**
   * Comma-separated alias types to exclude from alias search.
   * E.g. "asr_error" prevents ASR-error aliases from matching.
   * Only relevant when search_aliases=true.
   */
  exclude_alias_types?: string;
}

// ---------------------------------------------------------------------------
// Query parameter types
// ---------------------------------------------------------------------------

export interface FetchEntityVideosParams {
  /** Optional BCP-47 language code to filter mentions by language */
  language_code?: string;
  /**
   * Optional source filter. When provided, only videos whose sources list
   * includes this value are returned. Valid values: transcript, title,
   * description, tag, manual.
   */
  source?: string;
  /** Max results per page (1-100, default 20) */
  limit?: number;
  /** Offset for pagination (>=0) */
  offset?: number;
}

// ---------------------------------------------------------------------------
// Fetcher functions
// ---------------------------------------------------------------------------

/**
 * Fetches a paginated list of named entities with optional filters.
 *
 * @param params - Optional filter/sort/pagination parameters
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns Paginated EntityListResponse
 */
export async function fetchEntities(
  params: FetchEntitiesParams = {},
  signal?: AbortSignal
): Promise<EntityListResponse> {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.has_mentions !== undefined)
    qs.set("has_mentions", String(params.has_mentions));
  if (params.search) qs.set("search", params.search);
  if (params.sort) qs.set("sort", params.sort);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  if (params.offset !== undefined) qs.set("offset", String(params.offset));
  if (params.status !== undefined) qs.set("status", params.status);
  if (params.search_aliases !== undefined)
    qs.set("search_aliases", String(params.search_aliases));
  if (params.exclude_alias_types !== undefined)
    qs.set("exclude_alias_types", params.exclude_alias_types);
  const query = qs.toString();
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  return apiFetch<EntityListResponse>(`/entities${query ? `?${query}` : ""}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

/**
 * Fetches the list of entities mentioned in a video, sorted by mention count
 * descending.
 *
 * @param videoId - YouTube video ID
 * @param languageCode - Optional BCP-47 language code filter
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns VideoEntitiesResponse with entity summaries
 */
export async function fetchVideoEntities(
  videoId: string,
  languageCode?: string,
  signal?: AbortSignal
): Promise<VideoEntitiesResponse> {
  const params = new URLSearchParams();
  if (languageCode) {
    params.set("language_code", languageCode);
  }
  const qs = params.toString();
  const endpoint = `/videos/${videoId}/entities${qs ? `?${qs}` : ""}`;
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  return apiFetch<VideoEntitiesResponse>(endpoint, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

// ---------------------------------------------------------------------------
// Alias creation types
// ---------------------------------------------------------------------------

/** Request body for POST /api/v1/entities/{entity_id}/aliases */
export interface CreateEntityAliasRequest {
  alias_name: string;
  alias_type: string;
}

/** Response envelope for POST /api/v1/entities/{entity_id}/aliases */
export interface CreateEntityAliasResponse {
  data: EntityAliasSummary;
}

// ---------------------------------------------------------------------------
// Alias creation fetcher
// ---------------------------------------------------------------------------

/**
 * Creates a new alias for a named entity.
 *
 * @param entityId - UUID of the named entity
 * @param aliasName - The alias text to register
 * @param aliasType - Alias category (default: "name_variant")
 * @returns The newly created EntityAliasSummary
 * @throws ApiError with status 404 if entity not found, 409 if alias already exists
 */
export async function createEntityAlias(
  entityId: string,
  aliasName: string,
  aliasType: string = "name_variant"
): Promise<EntityAliasSummary> {
  const body: CreateEntityAliasRequest = {
    alias_name: aliasName,
    alias_type: aliasType,
  };
  const res = await apiFetch<CreateEntityAliasResponse>(
    `/entities/${entityId}/aliases`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
  return res.data;
}

/**
 * Fetches entity detail including aliases (asr_error excluded by backend).
 *
 * @param entityId - UUID of the named entity
 * @returns EntityDetail with canonical name, type, description, and aliases
 */
export async function fetchEntityDetail(
  entityId: string
): Promise<EntityDetail> {
  const res = await apiFetch<{ data: EntityDetail }>(
    `/entities/${entityId}`
  );
  return res.data;
}

/**
 * Fetches a paginated list of videos in which a given entity is mentioned,
 * including up to 5 mention previews per video.
 *
 * @param entityId - UUID of the named entity
 * @param params - Optional query parameters (language_code, limit, offset)
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns Paginated EntityVideoResponse with mention previews
 */
export async function fetchEntityVideos(
  entityId: string,
  params: FetchEntityVideosParams = {},
  signal?: AbortSignal
): Promise<EntityVideoResponse> {
  const qs = new URLSearchParams();
  if (params.language_code) {
    qs.set("language_code", params.language_code);
  }
  if (params.source) {
    qs.set("source", params.source);
  }
  if (params.limit !== undefined) {
    qs.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    qs.set("offset", String(params.offset));
  }
  const query = qs.toString();
  const endpoint = `/entities/${entityId}/videos${query ? `?${query}` : ""}`;
  // FR-004/FR-005: externalSignal combines with the internal timeout guard.
  return apiFetch<EntityVideoResponse>(endpoint, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

// ---------------------------------------------------------------------------
// Exclusion pattern types
// ---------------------------------------------------------------------------

/** Request body for POST/DELETE /api/v1/entities/{entity_id}/exclusion-patterns */
export interface ExclusionPatternRequest {
  pattern: string;
}

/** Response envelope for POST/DELETE /api/v1/entities/{entity_id}/exclusion-patterns */
export interface ExclusionPatternResponse {
  data: string[];
}

// ---------------------------------------------------------------------------
// Exclusion pattern fetchers
// ---------------------------------------------------------------------------

/**
 * Adds an exclusion pattern to a named entity.
 *
 * Exclusion patterns are phrases that should NOT trigger entity mention
 * detection. For example, entity "Mexico" might exclude "New Mexico" so
 * references to "New Mexico" don't get flagged as a "Mexico" mention.
 *
 * @param entityId - UUID of the named entity
 * @param pattern - The phrase to exclude from mention detection
 * @returns Updated array of all exclusion patterns for the entity
 * @throws ApiError with status 404 if entity not found, 409 if pattern already exists
 */
export async function addExclusionPattern(
  entityId: string,
  pattern: string
): Promise<string[]> {
  const body: ExclusionPatternRequest = { pattern };
  const res = await apiFetch<ExclusionPatternResponse>(
    `/entities/${entityId}/exclusion-patterns`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
  return res.data;
}

/**
 * Removes an exclusion pattern from a named entity.
 *
 * @param entityId - UUID of the named entity
 * @param pattern - The phrase to remove from the exclusion list
 * @returns Updated array of all exclusion patterns for the entity
 * @throws ApiError with status 404 if entity or pattern not found
 */
export async function removeExclusionPattern(
  entityId: string,
  pattern: string
): Promise<string[]> {
  const body: ExclusionPatternRequest = { pattern };
  const res = await apiFetch<ExclusionPatternResponse>(
    `/entities/${entityId}/exclusion-patterns`,
    {
      method: "DELETE",
      body: JSON.stringify(body),
    }
  );
  return res.data;
}

/**
 * Fetches suspected phonetic ASR variants of a named entity's name.
 *
 * @param entityId - UUID of the named entity
 * @param threshold - Optional confidence threshold (0.0–1.0)
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns Array of PhoneticMatch objects
 */
export async function fetchPhoneticMatches(
  entityId: string,
  threshold?: number,
  signal?: AbortSignal
): Promise<PhoneticMatch[]> {
  const searchParams = new URLSearchParams();
  if (threshold != null) searchParams.set("threshold", String(threshold));
  const qs = searchParams.toString();
  const url = `/entities/${entityId}/phonetic-matches${qs ? `?${qs}` : ""}`;
  const response = await apiFetch<{ data: PhoneticMatch[] }>(url, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Entity search types (for GET /api/v1/entities/search)
// ---------------------------------------------------------------------------

/** Result from entity autocomplete search. */
export interface EntitySearchResult {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  matched_alias: string | null;
  is_linked: boolean | null;
  link_sources: string[] | null;
}

/** Response envelope for GET /api/v1/entities/search */
export interface EntitySearchResponse {
  data: EntitySearchResult[];
}

// ---------------------------------------------------------------------------
// Manual association types (for POST /api/v1/videos/{video_id}/entities/{entity_id}/manual)
// ---------------------------------------------------------------------------

/** Response for POST /api/v1/videos/{video_id}/entities/{entity_id}/manual */
export interface ManualAssociationResponse {
  id: string;
  entity_id: string;
  video_id: string;
  detection_method: string;
  mention_text: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Entity search fetcher
// ---------------------------------------------------------------------------

/**
 * Searches entities by name/alias for autocomplete.
 *
 * @param query - Search query (min 2 chars)
 * @param videoId - Optional video ID for is_linked context
 * @param limit - Max results (default 10, max 20)
 * @param signal - Optional AbortSignal
 * @returns Array of matching entities
 */
export async function searchEntities(
  query: string,
  videoId?: string,
  limit?: number,
  signal?: AbortSignal
): Promise<EntitySearchResult[]> {
  const params = new URLSearchParams();
  params.set("q", query);
  if (videoId) params.set("video_id", videoId);
  if (limit !== undefined) params.set("limit", String(limit));
  const qs = params.toString();
  const res = await apiFetch<EntitySearchResponse>(`/entities/search?${qs}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Manual association fetcher
// ---------------------------------------------------------------------------

/**
 * Creates a manual entity-video association.
 *
 * @param videoId - YouTube video ID
 * @param entityId - Named entity UUID
 * @returns The created manual association
 */
export async function createManualAssociation(
  videoId: string,
  entityId: string
): Promise<ManualAssociationResponse> {
  return apiFetch<ManualAssociationResponse>(
    `/videos/${videoId}/entities/${entityId}/manual`,
    { method: "POST" }
  );
}

/**
 * Deletes a manual entity-video association.
 *
 * @param videoId - YouTube video ID
 * @param entityId - Named entity UUID
 */
export async function deleteManualAssociation(
  videoId: string,
  entityId: string
): Promise<void> {
  await apiFetch(`/videos/${videoId}/entities/${entityId}/manual`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Duplicate check types (for GET /api/v1/entities/check-duplicate)
// ---------------------------------------------------------------------------

/** Response from GET /api/v1/entities/check-duplicate */
export interface DuplicateCheckResult {
  is_duplicate: boolean;
  existing_entity: {
    entity_id: string;
    canonical_name: string;
    entity_type: string;
    description: string | null;
  } | null;
}

// ---------------------------------------------------------------------------
// Duplicate check fetcher
// ---------------------------------------------------------------------------

/**
 * Checks whether an entity with the given name and type already exists.
 *
 * @param name - Candidate canonical name to check
 * @param type - Entity type (e.g. "person", "organization", "place")
 * @param signal - Optional AbortSignal for cancellation
 * @returns DuplicateCheckResult indicating whether a duplicate exists
 */
export async function checkEntityDuplicate(
  name: string,
  type: string,
  signal?: AbortSignal
): Promise<DuplicateCheckResult> {
  const params = new URLSearchParams({ name, type });
  return apiFetch<DuplicateCheckResult>(
    `/entities/check-duplicate?${params.toString()}`,
    {
      ...(signal !== undefined ? { externalSignal: signal } : {}),
    }
  );
}

// ---------------------------------------------------------------------------
// Classify tag types (for POST /api/v1/entities/classify)
// ---------------------------------------------------------------------------

/** Response from POST /api/v1/entities/classify */
export interface ClassifyTagResponse {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  alias_count: number;
  entity_created: boolean;
  operation_id: string;
}

// ---------------------------------------------------------------------------
// Classify tag fetcher
// ---------------------------------------------------------------------------

/**
 * Classifies a raw tag as a named entity, creating or updating it as needed.
 *
 * @param data.normalized_form - The canonical name / normalized tag text
 * @param data.entity_type - Entity type (e.g. "person", "organization", "place")
 * @param data.description - Optional human-readable description
 * @returns ClassifyTagResponse with entity_id and operation metadata
 * @throws ApiError with status 409 if the tag is already classified as a different type
 */
export async function classifyTag(data: {
  normalized_form: string;
  entity_type: string;
  description?: string;
}): Promise<ClassifyTagResponse> {
  return apiFetch<ClassifyTagResponse>("/entities/classify", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Standalone entity creation types (for POST /api/v1/entities)
// ---------------------------------------------------------------------------

/** Request body for POST /api/v1/entities */
export interface CreateEntityRequest {
  /** Canonical name for the new entity */
  name: string;
  /** Entity type (e.g. "person", "organization", "place") */
  entity_type: string;
  /** Optional human-readable description */
  description?: string;
  /** Optional initial alias names to register alongside the entity */
  aliases?: string[];
}

/** Response from POST /api/v1/entities */
export interface CreateEntityResponse {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  alias_count: number;
}

// ---------------------------------------------------------------------------
// Standalone entity creation fetcher
// ---------------------------------------------------------------------------

/**
 * Creates a new standalone named entity.
 *
 * Unlike `classifyTag`, this endpoint creates an entity that is not linked to
 * any canonical tag — it is for entities that exist independently of the tag
 * taxonomy (e.g. people, places, organisations mentioned in transcripts).
 *
 * @param data - Entity creation payload (name, entity_type, optional description/aliases)
 * @returns CreateEntityResponse with the new entity_id and summary
 * @throws ApiError with status 409 if an entity with the same name and type already exists
 */
export async function createEntity(
  data: CreateEntityRequest
): Promise<CreateEntityResponse> {
  return apiFetch<CreateEntityResponse>("/entities", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Entity scan types (for POST /api/v1/entities/{entity_id}/scan
//                    and POST /api/v1/videos/{video_id}/scan-entities)
// ---------------------------------------------------------------------------

/** Optional parameters shared by both entity-scan endpoints. */
export interface ScanRequest {
  /** BCP-47 language code to restrict scan to a single transcript language. */
  language_code?: string;
  /** Restrict scan to mentions of a specific entity type (e.g. "person"). */
  entity_type?: string;
  /** When true, report what would be found without persisting any mentions. */
  dry_run?: boolean;
  /** When true, re-scan segments that already have recorded mentions. */
  full_rescan?: boolean;
  /**
   * Scan source types to include. Valid values: "transcript", "title",
   * "description". Defaults to ["transcript"] when omitted.
   * "tag" is not a valid scan source (tag associations are query-time only).
   */
  sources?: string[];
}

/** Aggregate statistics returned by a completed entity scan. */
export interface ScanResultData {
  segments_scanned: number;
  mentions_found: number;
  mentions_skipped: number;
  unique_entities: number;
  unique_videos: number;
  duration_seconds: number;
  dry_run: boolean;
}

/** Response envelope for entity scan endpoints. */
export interface ScanResultResponse {
  data: ScanResultData;
}

// ---------------------------------------------------------------------------
// Entity scan fetchers
// ---------------------------------------------------------------------------

/**
 * Triggers a transcript scan for a single named entity across all videos.
 *
 * @param entityId - UUID of the named entity to scan for
 * @param options - Optional scan parameters (language filter, dry_run, full_rescan)
 * @returns ScanResultResponse with aggregate mention statistics
 * @throws ApiError with status 404 if the entity is not found
 */
export async function scanEntity(
  entityId: string,
  options?: ScanRequest
): Promise<ScanResultResponse> {
  return apiFetch<ScanResultResponse>(`/entities/${entityId}/scan`, {
    method: "POST",
    body: JSON.stringify(options ?? {}),
    timeout: SCAN_TIMEOUT,
  });
}

/**
 * Triggers an entity scan across all known entities for a single video's
 * transcripts.
 *
 * @param videoId - YouTube video ID whose transcripts should be scanned
 * @param options - Optional scan parameters (language filter, dry_run, full_rescan)
 * @returns ScanResultResponse with aggregate mention statistics
 * @throws ApiError with status 404 if the video is not found
 */
export async function scanVideoEntities(
  videoId: string,
  options?: ScanRequest
): Promise<ScanResultResponse> {
  return apiFetch<ScanResultResponse>(`/videos/${videoId}/scan-entities`, {
    method: "POST",
    body: JSON.stringify(options ?? {}),
    timeout: SCAN_TIMEOUT,
  });
}
