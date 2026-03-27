/**
 * API client functions for batch correction analysis endpoints.
 *
 * Covers:
 * - GET /api/v1/corrections/batch/diff-analysis — recurring ASR error patterns
 * - GET /api/v1/corrections/batch/cross-segment/candidates — cross-segment candidates
 */

import { apiFetch } from "./config";
import type { DiffErrorPattern, CrossSegmentCandidate } from "../types/corrections";

// ---------------------------------------------------------------------------
// Query parameter types
// ---------------------------------------------------------------------------

export interface FetchDiffAnalysisParams {
  /** Minimum number of occurrences for a pattern to be included */
  minOccurrences?: number;
  /** Maximum number of results to return */
  limit?: number;
  /** Whether to include already-completed corrections */
  showCompleted?: boolean;
  /** Filter patterns associated with a specific entity name */
  entityName?: string;
}

export interface FetchCrossSegmentParams {
  /** Minimum correction count threshold for cross-segment candidates */
  minCorrections?: number;
  /** Filter candidates associated with a specific entity name */
  entityName?: string;
}

// ---------------------------------------------------------------------------
// Fetcher functions
// ---------------------------------------------------------------------------

/**
 * Fetches recurring ASR error patterns identified by word-level diff analysis.
 *
 * @param params - Optional filter parameters
 * @param signal - Optional AbortSignal for cancellation
 * @returns Array of DiffErrorPattern objects
 */
export async function fetchDiffAnalysis(
  params?: FetchDiffAnalysisParams,
  signal?: AbortSignal
): Promise<DiffErrorPattern[]> {
  const searchParams = new URLSearchParams();
  if (params?.minOccurrences != null)
    searchParams.set("min_occurrences", String(params.minOccurrences));
  if (params?.limit != null)
    searchParams.set("limit", String(params.limit));
  if (params?.showCompleted != null)
    searchParams.set("show_completed", String(params.showCompleted));
  if (params?.entityName)
    searchParams.set("entity_name", params.entityName);
  const qs = searchParams.toString();
  const url = `/corrections/batch/diff-analysis${qs ? `?${qs}` : ""}`;
  const response = await apiFetch<{ data: DiffErrorPattern[] }>(url, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return response.data;
}

/**
 * Fetches adjacent segment pairs where an ASR error spans the segment boundary.
 *
 * @param params - Optional filter parameters
 * @param signal - Optional AbortSignal for cancellation
 * @returns Array of CrossSegmentCandidate objects
 */
export async function fetchCrossSegmentCandidates(
  params?: FetchCrossSegmentParams,
  signal?: AbortSignal
): Promise<CrossSegmentCandidate[]> {
  const searchParams = new URLSearchParams();
  if (params?.minCorrections != null)
    searchParams.set("min_corrections", String(params.minCorrections));
  if (params?.entityName)
    searchParams.set("entity_name", params.entityName);
  const qs = searchParams.toString();
  const url = `/corrections/batch/cross-segment/candidates${qs ? `?${qs}` : ""}`;
  const response = await apiFetch<{ data: CrossSegmentCandidate[] }>(url, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return response.data;
}
