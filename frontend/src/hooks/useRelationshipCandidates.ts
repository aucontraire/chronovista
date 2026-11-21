/**
 * Read-only TanStack Query hook for the novel-relationship candidate queue
 * (Feature 107). Rows arrive lift-ranked from the API; there are no mutations.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/config";

export interface RelationshipEntitySummary {
  id: string;
  canonical_name: string;
  entity_type: string;
}

export interface RelationshipCandidate {
  id: string;
  entity_a: RelationshipEntitySummary;
  entity_b: RelationshipEntitySummary;
  shared_video_count: number;
  lift: number;
  both_typed_eligible: boolean;
  kb_corroboration_count: number;
  kb_corroboration_detail: string[];
  channel: string;
  channel_video_universe: number;
  status: "candidate";
  /** Human verdict (e.g. `associated_with`, `co_cast`, `covers`, `coincidence`, `artifact`); null = unreviewed. */
  review_status: string | null;
  /** ISO 8601 timestamp of the verdict, or null when unreviewed. */
  reviewed_at: string | null;
}

export type ReviewFilter = "all" | "reviewed" | "unreviewed";
export type SortBy =
  | "rank"
  | "lift"
  | "shared_video_count"
  | "kb_corroboration_count"
  | "reviewed_at";
export type VerdictCategory =
  | "associated_with"
  | "co_cast"
  | "covers"
  | "coincidence"
  | "artifact";
export type SortDir = "asc" | "desc";

export interface RelationshipCandidateListResponse {
  items: RelationshipCandidate[];
  total: number;
  /** Candidates matching the active filters across the whole queue (same population as `total`, before the head cutoff). */
  total_before_scoping: number;
  /** Active cutoff: the queue is scoped to this many top rows. */
  head_cutoff: number;
  limit: number;
  offset: number;
  /** ISO 8601 timestamp of the last generation, or null if never generated. */
  generated_at: string | null;
}

export interface RelationshipCandidateParams {
  limit: number;
  offset: number;
  eligible_only: boolean;
  review: ReviewFilter;
  /** Repeatable `verdict` filter; empty = no category filter. */
  verdict: readonly VerdictCategory[];
  sort_by: SortBy;
  sort_dir: SortDir;
}

export const RELATIONSHIP_CANDIDATES_KEY = ["relationship-candidates"] as const;

export async function fetchRelationshipCandidates(
  params: RelationshipCandidateParams,
  signal?: AbortSignal
): Promise<RelationshipCandidateListResponse> {
  const qs = new URLSearchParams({
    limit: String(params.limit),
    offset: String(params.offset),
    eligible_only: String(params.eligible_only),
    review: params.review,
    sort_by: params.sort_by,
    sort_dir: params.sort_dir,
  });
  params.verdict.forEach((v) => qs.append("verdict", v));
  return apiFetch<RelationshipCandidateListResponse>(
    `/relationship-candidates?${qs.toString()}`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) }
  );
}

export function useRelationshipCandidates(params: RelationshipCandidateParams) {
  return useQuery({
    queryKey: [
      ...RELATIONSHIP_CANDIDATES_KEY,
      params.limit,
      params.offset,
      params.eligible_only,
      params.review,
      [...params.verdict],
      params.sort_by,
      params.sort_dir,
    ],
    queryFn: ({ signal }) => fetchRelationshipCandidates(params, signal),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
  });
}
