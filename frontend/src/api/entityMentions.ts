/**
 * API client functions for entity mention endpoints.
 *
 * Covers:
 * - GET /api/v1/videos/{video_id}/entities — video entity summary
 * - GET /api/v1/entities/{entity_id}/videos — entity-to-videos lookup
 */

import { apiFetch } from "./config";
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
  /** Alias identifier — needed to address a single alias for update. */
  id: string;
  alias_name: string;
  /** name_variant | abbreviation | nickname | translated_name | former_name */
  alias_type: string;
  occurrence_count: number;
  /**
   * When true this alias matches only its exact casing. False (the default)
   * matches any casing, which is how every alias has always behaved.
   */
  case_sensitive: boolean;
}

/** Per-source breakdown of an entity's distinct-video association count. */
export interface AssociationSourceBreakdown {
  manual: number;
  transcript: number;
  title: number;
  description: number;
  tag: number;
}

/** A single item in the entity list response. */
export interface EntityListItem {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  mention_count: number;
  /** Combined distinct-video association total across all five sources. */
  video_count: number;
  by_source: AssociationSourceBreakdown;
}

/** Full detail response for GET /api/v1/entities/{entity_id} */
export interface EntityDetail {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  mention_count: number;
  /** Combined distinct-video association total across all five sources. */
  video_count: number;
  by_source: AssociationSourceBreakdown;
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
   * Optional source filter. When one or more values are provided, only
   * videos whose sources list includes at least one of them are returned
   * (union). Omitted or empty returns all sources. Valid values: transcript,
   * title, description, tag, manual.
   */
  source?: string[];
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

/** Request body for PATCH /api/v1/entities/{entity_id}/aliases/{alias_id} */
export interface UpdateEntityAliasRequest {
  case_sensitive: boolean;
}

/** Response envelope for PATCH /api/v1/entities/{entity_id}/aliases/{alias_id} */
export interface UpdateEntityAliasResponse {
  data: EntityAliasSummary;
}

/**
 * Sets whether an alias matches case-sensitively.
 *
 * The change does not retroactively alter existing mentions — matching rules
 * are applied when a scan runs, so callers must follow this with a full
 * rescan of the entity for it to take effect.
 *
 * @param entityId - UUID of the named entity that owns the alias
 * @param aliasId - UUID of the alias to update
 * @param caseSensitive - New matching behaviour
 * @returns The updated EntityAliasSummary
 * @throws ApiError with status 404 if the entity or alias is not found, or if
 *   the alias does not belong to that entity
 */
export async function updateEntityAlias(
  entityId: string,
  aliasId: string,
  caseSensitive: boolean
): Promise<EntityAliasSummary> {
  const body: UpdateEntityAliasRequest = { case_sensitive: caseSensitive };
  const res = await apiFetch<UpdateEntityAliasResponse>(
    `/entities/${entityId}/aliases/${aliasId}`,
    {
      method: "PATCH",
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

// ---------------------------------------------------------------------------
// Entity update types (for PATCH /api/v1/entities/{entity_id})
// ---------------------------------------------------------------------------

/**
 * Request body for PATCH /api/v1/entities/{entity_id} (Feature 057).
 * PATCH semantics — at least one field is required. `canonical_name` is
 * stored verbatim (no re-casing); an empty `description` clears it (distinct
 * from omitting the field, which leaves it unchanged).
 */
export interface UpdateEntityRequest {
  canonical_name?: string;
  description?: string;
  /** Corrects an entity filed under the wrong type (e.g. a place saved as a person). */
  entity_type?: string;
}

/**
 * Updates a named entity's display name, description, and/or type.
 *
 * Never modifies the tag(s) the entity is linked to. On a name change, the
 * backend recomputes the normalized identity and re-checks
 * `(canonical_name_normalized, entity_type)` uniqueness.
 *
 * @param entityId - UUID of the named entity
 * @param data - Fields to update (at least one of canonical_name/description/entity_type)
 * @returns The updated EntityDetail
 * @throws ApiError with status 400 (invalid/empty name), 404 (not found), or
 *   409 (the resulting name+type pair collides with an existing entity)
 */
export async function updateEntity(
  entityId: string,
  data: UpdateEntityRequest
): Promise<EntityDetail> {
  const res = await apiFetch<{ data: EntityDetail }>(`/entities/${entityId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
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
  for (const s of params.source ?? []) {
    qs.append("source", s);
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
 * detection. For example, entity "Peru" might exclude "New Peru" so
 * references to "New Peru" don't get flagged as a "Peru" mention.
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

// ---------------------------------------------------------------------------
// Entity tags (Feature 064)
// ---------------------------------------------------------------------------

/** Outcome of attaching a canonical tag to an entity. */
export interface AddEntityTagResult {
  /** Which path the server took. It decides, not the client. */
  operation: "link" | "merge";
  operation_id: string;
  /**
   * The tag that now represents the entity. For a merge this is the
   * pre-existing tag, not the one just supplied — the entity's tag always wins.
   */
  target_normalized_form: string;
  /**
   * The target's display form. The normalized form is lower-cased, and a
   * message built from it reads as a different tag than the one shown
   * immediately above it on the page.
   */
  target_canonical_form: string;
  /** The entity's video count after the operation. */
  entity_video_count: number;
}

/**
 * Attaches a canonical tag to an entity.
 *
 * The server chooses between linking and merging from the entity's current
 * state, so the request carries only the tag. Sending an `entity_type` is not
 * possible by design: a value disagreeing with the target would be a conflict,
 * and this page has no guarantee the two agree.
 *
 * @param entityId - The entity to attach to
 * @param normalizedForm - Normalized form of the canonical tag
 * @returns Which operation ran, the surviving tag, and the resulting video count
 * @throws ApiError 404 if the entity or the tag does not exist
 * @throws ApiError 409 if the tag belongs to another entity, is already merged,
 *   or the entity holds more than one linked tag
 * @throws ApiError 422 if the tag is already the entity's own
 */
export async function addEntityTag(
  entityId: string,
  normalizedForm: string
): Promise<AddEntityTagResult> {
  const body = await apiFetch<{ data: AddEntityTagResult }>(
    `/entities/${entityId}/tags`,
    {
      method: "POST",
      body: JSON.stringify({ normalized_form: normalizedForm }),
    }
  );
  return body.data;
}

/**
 * Classifies a canonical tag, either creating a new named entity or linking
 * the tag to one that already exists.
 *
 * The two modes are mutually exclusive in their optional fields: `description`
 * and `display_name` describe an entity being created, so the backend rejects
 * either alongside `link_entity_id` rather than silently discarding it
 * (issue #183).
 *
 * @param data.normalized_form - The canonical name / normalized tag text
 * @param data.entity_type - Entity type (e.g. "person", "organization",
 *   "place"). Required when creating; optional when linking, where the target
 *   entity's own type is used. Sending a type that disagrees with the target
 *   is a 409 rather than an override — the entity owns its type.
 * @param data.description - Optional human-readable description (create only)
 * @param data.display_name - Optional entity display name, stored verbatim
 *   (no re-casing). When omitted, the backend falls back to its existing
 *   auto-derived (title-cased) name (Feature 057, FR-008/FR-009/FR-010).
 *   The tag is still matched/linked by `normalized_form` regardless of this
 *   value's casing (FR-011). Create only.
 * @param data.link_entity_id - Attach the tag to this existing entity instead
 *   of creating one (issue #183).
 * @returns ClassifyTagResponse with entity_id and operation metadata
 * @throws ApiError with status 409 if the tag is already classified, if
 *   `entity_type` disagrees with the link target, or if the target is inactive
 * @throws ApiError with status 404 if `link_entity_id` names no entity
 */
export async function classifyTag(data: {
  normalized_form: string;
  entity_type?: string;
  description?: string;
  display_name?: string;
  link_entity_id?: string;
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
// Scan job types (for the async fire-and-poll scan flow)
//
// Scan endpoints now launch a background job (202) instead of blocking for
// the scan's full duration (which can exceed the client request timeout on
// large corpora). Callers poll GET /scan-jobs/{job_id} until the job reaches
// a terminal status.
// ---------------------------------------------------------------------------

/** What a scan job targets. */
export type ScanJobKind = "entity" | "video";

/** Lifecycle status of an asynchronous scan job. */
export type ScanJobStatus = "running" | "succeeded" | "failed";

/**
 * State of an asynchronous entity-mention scan job, as returned both when a
 * scan is launched (202) and when polled via GET /scan-jobs/{job_id}.
 *
 * Jobs are tracked in an in-memory registry on the backend — ephemeral, does
 * not survive a server restart.
 */
export interface ScanJob {
  job_id: string;
  kind: ScanJobKind;
  /** Entity UUID or video ID being scanned. */
  target_id: string;
  status: ScanJobStatus;
  /** Scan metrics, populated once the job has succeeded. */
  result: ScanResultData | null;
  /** Error message if the job failed. */
  error: string | null;
  started_at: string;
  /** When the job reached a terminal state, if it has. */
  finished_at: string | null;
}

/** Response envelope for scan-job launch (202) and status endpoints. */
export interface ScanJobResponse {
  data: ScanJob;
}

// ---------------------------------------------------------------------------
// Entity scan fetchers
// ---------------------------------------------------------------------------

/**
 * Launches an asynchronous transcript scan for a single named entity across
 * all videos.
 *
 * The backend runs the scan as a background job and returns immediately
 * (202) with the job's initial "running" state. Poll `getScanJob(job_id)`
 * for progress and the final result.
 *
 * @param entityId - UUID of the named entity to scan for
 * @param options - Optional scan parameters (language filter, dry_run, full_rescan)
 * @returns The newly created ScanJob (status "running")
 * @throws ApiError with status 404 if the entity is not found, 409 if a scan
 *   is already in progress for this entity
 */
export async function scanEntity(
  entityId: string,
  options?: ScanRequest
): Promise<ScanJob> {
  const res = await apiFetch<ScanJobResponse>(`/entities/${entityId}/scan`, {
    method: "POST",
    body: JSON.stringify(options ?? {}),
  });
  return res.data;
}

/**
 * Launches an asynchronous entity scan across all known entities for a
 * single video's transcripts.
 *
 * The backend runs the scan as a background job and returns immediately
 * (202) with the job's initial "running" state. Poll `getScanJob(job_id)`
 * for progress and the final result.
 *
 * @param videoId - YouTube video ID whose transcripts should be scanned
 * @param options - Optional scan parameters (language filter, dry_run, full_rescan)
 * @returns The newly created ScanJob (status "running")
 * @throws ApiError with status 404 if the video is not found, 409 if a scan
 *   is already in progress for this video
 */
export async function scanVideoEntities(
  videoId: string,
  options?: ScanRequest
): Promise<ScanJob> {
  const res = await apiFetch<ScanJobResponse>(
    `/videos/${videoId}/scan-entities`,
    {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    }
  );
  return res.data;
}

/**
 * Fetches the current state of an asynchronous scan job.
 *
 * While the job is running, `status` is "running" and `result` is null. On
 * completion it becomes "succeeded" (with `result` metrics) or "failed"
 * (with `error`).
 *
 * @param jobId - Scan job identifier returned by scanEntity/scanVideoEntities
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns The current ScanJob state
 * @throws ApiError with status 404 if the job is unknown (including after a
 *   server restart, since jobs are in-memory only)
 */
export async function getScanJob(
  jobId: string,
  signal?: AbortSignal
): Promise<ScanJob> {
  const res = await apiFetch<ScanJobResponse>(`/scan-jobs/${jobId}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Appears-with panel (Feature 062, US3)
// ---------------------------------------------------------------------------

/** An entity sharing videos with the subject entity. */
export interface CooccurringEntity {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  /**
   * Distinct videos in which both entities have a qualifying mention.
   *
   * Equals the videos list's `pagination.total` for the same pair under the
   * same evidence scope (FR-024b) — so the number shown here and the number
   * landed on after clicking are the same number.
   */
  shared_video_count: number;
}

/**
 * Fetch the entities co-occurring with a subject entity.
 *
 * @param entityId - UUID of the subject entity
 * @param limit - Maximum partners to return (server-bounded)
 * @param minEvidence - Evidence scope; must match the surrounding view's
 * @param signal - Abort signal, so a scope change discards an in-flight result
 */
export async function fetchCooccurringEntities(
  entityId: string,
  limit: number,
  minEvidence?: "transcript",
  signal?: AbortSignal
): Promise<CooccurringEntity[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (minEvidence) params.set("min_evidence", minEvidence);
  const res = await apiFetch<{ data: CooccurringEntity[] }>(
    `/entities/${entityId}/co-occurring?${params.toString()}`,
    signal ? { externalSignal: signal } : {}
  );
  return res.data;
}

/** A canonical tag folded into the entity's tag by a curator's merge. */
export interface MergedTagSummary {
  canonical_form: string;
  normalized_form: string;
  /**
   * Videos this tag held **when it was merged** — frozen, not live, and not
   * additive with the parent's count since the sets may overlap.
   */
  contributed_video_count: number;
  /** null means it cannot be un-merged from the interface. */
  operation_id: string | null;
  /** >1 means reversing that merge restores other tags too. */
  operation_source_count: number;
}

/** A canonical tag that represents the entity. */
export interface LinkedTagSummary {
  canonical_form: string;
  normalized_form: string;
  video_count: number;
  alias_count: number;
  merged_tags: MergedTagSummary[];
}

/** The tags representing an entity. */
export interface EntityTagsResult {
  /**
   * Normally exactly one. Empty means no tag is linked — itself the signal
   * that the entity's video count omits every tag-associated video.
   */
  linked_tags: LinkedTagSummary[];
  /** True when more than one tag is linked: a legacy state needing repair. */
  needs_attention: boolean;
}

/**
 * Fetches the tags representing an entity, each with what it has absorbed.
 *
 * @param entityId - The entity to inspect
 * @returns Linked tags and whether the entity needs attention
 * @throws ApiError 404 if the entity does not exist
 */
export async function fetchEntityTags(
  entityId: string
): Promise<EntityTagsResult> {
  const body = await apiFetch<{ data: EntityTagsResult }>(
    `/entities/${entityId}/tags`
  );
  return body.data;
}

/** Tags restored by reversing a merge. */
export interface UnMergeResult {
  restored: string[];
  operation_id: string;
}

/**
 * Reverses the merge that folded a tag into the entity's tag.
 *
 * Reverses the whole operation, so a merge that folded several tags restores
 * all of them — which is why `confirmMultiSource` exists. The server refuses
 * with 409 and names every tag that would return until it is set.
 *
 * @param entityId - The entity whose tag absorbed this one
 * @param normalizedForm - The merged tag to restore
 * @param confirmMultiSource - Acknowledge a multi-tag reversal
 * @throws ApiError 409 when confirmation is required, or already reversed
 * @throws ApiError 404 if no live merge for that tag exists on this entity
 */
export async function unMergeEntityTag(
  entityId: string,
  normalizedForm: string,
  confirmMultiSource = false
): Promise<UnMergeResult> {
  const body = await apiFetch<{ data: UnMergeResult }>(
    `/entities/${entityId}/tags/${encodeURIComponent(normalizedForm)}/un-merge`,
    {
      method: "POST",
      body: JSON.stringify({ confirm_multi_source: confirmMultiSource }),
    }
  );
  return body.data;
}

/**
 * Stops a tag representing an entity. The tag itself is untouched.
 *
 * @param entityId - The entity to detach from
 * @param normalizedForm - The linked tag
 * @throws ApiError 409 if tags are merged into it and must be un-merged first
 */
export async function unlinkEntityTag(
  entityId: string,
  normalizedForm: string
): Promise<{ unlinked: string }> {
  const body = await apiFetch<{ data: { unlinked: string } }>(
    `/entities/${entityId}/tags/${encodeURIComponent(normalizedForm)}`,
    { method: "DELETE" }
  );
  return body.data;
}
