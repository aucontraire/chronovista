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
}

export interface RelationshipCandidateListResponse {
  items: RelationshipCandidate[];
  total: number;
  limit: number;
  offset: number;
  /** ISO 8601 timestamp of the last generation, or null if never generated. */
  generated_at: string | null;
}

export interface RelationshipCandidateParams {
  limit: number;
  offset: number;
  eligible_only: boolean;
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
  });
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
    ],
    queryFn: ({ signal }) => fetchRelationshipCandidates(params, signal),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
  });
}
