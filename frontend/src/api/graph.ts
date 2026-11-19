/**
 * Connection-graph API client (Feature 113).
 *
 * TODO: regenerate orval client — these types are hand-written to mirror
 * `src/chronovista/models/graph_connection.py` and `api/routers/graph.py`
 * until the generated client is refreshed. Keep field names identical to the
 * backend models.
 */

import { apiFetch } from "./config";

/** Mirrors the backend `ConnectionKind` enum (declaration order = presentation order). */
export type ConnectionKind =
  | "asserted"
  | "shared_referent"
  | "shared_category"
  | "co_occurrence_transcript"
  | "co_occurrence_titledesc"
  | "co_occurrence_tags"
  | "co_occurrence_manual";

export interface GraphNode {
  entity_id: string | null;
  name: string;
  label: string;
  is_bridge: boolean;
  /** Set only on the two queried endpoints. */
  kb_degree: number | null;
  /** Server-computed log-specificity for Category bridge nodes. Never recompute. */
  specificity: number | null;
}

export interface PathStep {
  edge_type: string;
  kind: ConnectionKind;
  to_node: GraphNode;
  specificity: number | null;
  /** False when the stored edge points from `to_node` back toward the previous node. */
  forward: boolean;
}

export interface ConnectionChain {
  kind: ConnectionKind;
  steps: PathStep[];
  truncated: boolean;
  score: number | null;
  length?: number;
}

export interface ReviewedVerdict {
  verdict: "relationship" | "coincidence";
  relation: "associated_with" | "covers" | "co_cast" | null;
  origin: "human" | "reaudited_c" | "suggested_agreed";
  settled: boolean;
  judged_over: ConnectionKind[];
  provenance: string;
  confidence?: "high" | "medium";
}

export interface GraphConnection {
  entity_a: GraphNode;
  entity_b: GraphNode;
  reviewed_verdict: ReviewedVerdict | null;
  chains: ConnectionChain[];
  searched_max_hops: number;
  any_truncated: boolean;
  has_connection: boolean;
}

export interface GraphHealth {
  status: "complete" | "loading" | null;
  loaded_at: string | null;
  declared_layers: string[];
  servable: boolean;
}

export interface ConnectParams {
  a: string;
  b: string;
  maxHops?: number | undefined;
  maxCategorySize?: number | undefined;
}

export async function fetchConnection(
  { a, b, maxHops, maxCategorySize }: ConnectParams,
  signal?: AbortSignal,
): Promise<GraphConnection> {
  const params = new URLSearchParams({ a, b });
  if (maxHops !== undefined) params.set("max_hops", String(maxHops));
  if (maxCategorySize !== undefined) {
    params.set("max_category_size", String(maxCategorySize));
  }
  return apiFetch<GraphConnection>(`/graph/connect?${params.toString()}`, {
    // Graph traversals can be slower than the default 10s budget.
    timeout: 30000,
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

export async function fetchGraphHealth(signal?: AbortSignal): Promise<GraphHealth> {
  return apiFetch<GraphHealth>(
    "/graph/health",
    signal !== undefined ? { externalSignal: signal } : {},
  );
}

/** Returns the subset of `entityIds` present in the current graph. */
export async function fetchGraphPresence(
  entityIds: string[],
  signal?: AbortSignal,
): Promise<string[]> {
  const res = await apiFetch<{ present: string[] }>("/graph/entities", {
    method: "POST",
    body: JSON.stringify({ entity_ids: entityIds }),
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return res.present;
}
