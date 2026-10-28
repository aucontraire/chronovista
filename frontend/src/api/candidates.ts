/**
 * API client functions for the read-only candidate suggestion queue (Feature 096/097).
 *
 * Covers:
 * - GET /api/v1/candidates — ranked pending candidates (paginated)
 * - GET /api/v1/candidates/summary — queue counts by status and triage
 * - GET /api/v1/candidates/{id} — one candidate (any status)
 */

import { apiFetch } from "./config";
import type { PaginationMeta } from "../types/search";

// ---------------------------------------------------------------------------
// Response types (match backend api/schemas/candidates.py)
// ---------------------------------------------------------------------------

/** One candidate suggestion with its signals, provenance, and review state. */
export interface CandidateDetail {
  id: string;
  source_channel: string;
  wikidata_qid: string;
  label: string;
  label_normalized: string;
  type_hint: string;
  token_count: number;
  corroboration_count: number;
  dangling_edge_count: number;
  salience: number;
  score: number;
  triage: string;
  provenance: Record<string, unknown>;
  possible_duplicate_of_id: string | null;
  review_status: string;
  reviewed_by: string | null;
  /** ISO 8601 timestamp. */
  reviewed_at: string | null;
  created_entity_id: string | null;
  /** ISO 8601 timestamp. */
  last_generated_at: string;
  /** ISO 8601 timestamp. */
  created_at: string;
  /** ISO 8601 timestamp. */
  updated_at: string;
}

/** A single candidate row; the list endpoint returns the full detail shape. */
export type Candidate = CandidateDetail;

/** Response envelope for GET /api/v1/candidates */
export interface CandidateListResponse {
  data: CandidateDetail[];
  pagination: PaginationMeta;
}

/** Queue counts by review status, plus the pending triage distribution. */
export interface CandidateSummary {
  source_channel: string;
  pending: number;
  approved: number;
  rejected: number;
  superseded: number;
  worth_review: number;
  likely_eliminable: number;
  grounds_nowhere: number;
}

/** Response envelope for GET /api/v1/candidates/summary */
export interface CandidateSummaryResponse {
  data: CandidateSummary;
}

/** Query parameters accepted by GET /api/v1/candidates. */
export interface FetchCandidatesParams {
  triage?: string;
  type_hint?: string;
  min_token_count?: number;
  possible_duplicate?: boolean;
  source_channel?: string;
  /** "score" | "corroboration" | "salience" */
  sort?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Fetch functions
// ---------------------------------------------------------------------------

/** Fetches a page of pending candidates with optional filters. */
export async function fetchCandidates(
  params: FetchCandidatesParams = {},
  signal?: AbortSignal
): Promise<CandidateListResponse> {
  const qs = new URLSearchParams();
  if (params.triage) qs.set("triage", params.triage);
  if (params.type_hint) qs.set("type_hint", params.type_hint);
  if (params.min_token_count !== undefined)
    qs.set("min_token_count", String(params.min_token_count));
  if (params.possible_duplicate !== undefined)
    qs.set("possible_duplicate", String(params.possible_duplicate));
  if (params.source_channel) qs.set("source_channel", params.source_channel);
  if (params.sort) qs.set("sort", params.sort);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  if (params.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return apiFetch<CandidateListResponse>(
    `/candidates${query ? `?${query}` : ""}`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) }
  );
}

/** Fetches queue counts by status and pending triage. */
export async function fetchCandidateSummary(
  signal?: AbortSignal
): Promise<CandidateSummaryResponse> {
  return apiFetch<CandidateSummaryResponse>("/candidates/summary", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

/** Fetches one candidate by id (any review status). */
export async function fetchCandidateDetail(
  id: string,
  signal?: AbortSignal
): Promise<CandidateDetail> {
  return apiFetch<CandidateDetail>(`/candidates/${encodeURIComponent(id)}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

// ---------------------------------------------------------------------------
// Verdict (approve / reject) — Feature 097
// ---------------------------------------------------------------------------

/** Result of an approve or reject verdict. */
export interface CandidateVerdictResponse {
  /** "approved" | "rejected" | "superseded" | "failed" */
  outcome: string;
  candidate_id: string;
  created_entity_id: string | null;
  detail: string | null;
}

/** Approves a candidate, creating an entity (or linking an existing one). */
export async function approveCandidate(
  id: string
): Promise<CandidateVerdictResponse> {
  return apiFetch<CandidateVerdictResponse>(
    `/candidates/${encodeURIComponent(id)}/approve`,
    { method: "POST" }
  );
}

/** Rejects a candidate. */
export async function rejectCandidate(
  id: string
): Promise<CandidateVerdictResponse> {
  return apiFetch<CandidateVerdictResponse>(
    `/candidates/${encodeURIComponent(id)}/reject`,
    { method: "POST" }
  );
}

// ---------------------------------------------------------------------------
// UI-triggered generation — Feature 097 US2
// ---------------------------------------------------------------------------

/** One candidate generation run; `progress_percent` stays <= 99 until terminal. */
export interface GenerationRunResponse {
  id: string;
  source_channel: string;
  status: "running" | "completed" | "failed";
  /** 0-100; 100 means completed. */
  progress_percent: number;
  seeds_grounded: number;
  candidates_discovered: number;
  candidates_upserted: number;
  superseded: number;
  pending_total: number;
  by_triage: Record<string, number>;
  empty_reason: string | null;
  error: string | null;
  /** ISO 8601 timestamp. */
  started_at: string;
  /** ISO 8601 timestamp. */
  updated_at: string;
  /** ISO 8601 timestamp. */
  completed_at: string | null;
}

/** Response of GET /api/v1/candidates/generation/status. */
export interface GenerationStatusResponse {
  run: GenerationRunResponse | null;
}

/** Starts a generation run (202); a 409 means one is already active. */
export async function startGeneration(): Promise<GenerationRunResponse> {
  return apiFetch<GenerationRunResponse>("/candidates/generation", {
    method: "POST",
  });
}

/** Fetches the latest (or active) generation run, or `{ run: null }`. */
export async function fetchGenerationStatus(
  signal?: AbortSignal
): Promise<GenerationStatusResponse> {
  return apiFetch<GenerationStatusResponse>("/candidates/generation/status", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

// ---------------------------------------------------------------------------
// Tag footprint — Feature 097 US4
// ---------------------------------------------------------------------------

/** One tag whose linking would newly associate videos with an entity. */
export interface TagFootprintMatch {
  normalized_form: string;
  would_newly_associate: number;
  /** Entity that currently owns the tag, or null when unowned. */
  owned_by_entity_id: string | null;
}

/** Response of both tag-footprint endpoints; `matches` is [] when nothing to claim. */
export interface TagFootprintResponse {
  matches: TagFootprintMatch[];
}

/** Result of linking a tag to an entity. */
export interface TagLinkResponse {
  normalized_form: string;
  linked_entity_id: string;
}

/** Pre-approval preview of the tag footprint of a candidate. */
export async function fetchCandidateTagFootprint(
  candidateId: string,
  signal?: AbortSignal
): Promise<TagFootprintResponse> {
  return apiFetch<TagFootprintResponse>(
    `/candidates/${encodeURIComponent(candidateId)}/tag-footprint`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) }
  );
}

/** Post-approval tag footprint of an entity. */
export async function fetchEntityTagFootprint(
  entityId: string,
  signal?: AbortSignal
): Promise<TagFootprintResponse> {
  return apiFetch<TagFootprintResponse>(
    `/entities/${encodeURIComponent(entityId)}/tag-footprint`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) }
  );
}

/** Links a tag to an entity (re-assigns it if another entity owned it). */
export async function linkEntityTag(
  entityId: string,
  body: { normalized_form: string; entity_type: string }
): Promise<TagLinkResponse> {
  return apiFetch<TagLinkResponse>(
    `/entities/${encodeURIComponent(entityId)}/tag-link`,
    { method: "POST", body: JSON.stringify(body) }
  );
}
