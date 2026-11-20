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

// --- Transcript-evidence panel (Feature 114) --------------------------------
// Mirrors `src/chronovista/models/connection_evidence.py`. Keep field names identical.

/** Mirrors the backend `DetectionMethod` literal. */
export type DetectionMethod =
  | "rule_match"
  | "spacy_ner"
  | "llm_extraction"
  | "manual"
  | "user_correction"
  | "asr_match";

export interface MentionRef {
  segment_id: number;
  end_segment_id: number | null;
  language_code: string;
  sequence_number: number;
  start_time: number;
  mention_text: string;
  match_start: number | null;
  match_end: number | null;
  detection_method: DetectionMethod;
}

/** A bounded run of transcript segments rendered as prose. */
export interface Passage {
  text: string;
  start_time: number;
  /** Lead segment id — the deep-link `seg` / scroll anchor. */
  segment_id: number;
}

/** One (video, language) co-occurrence: the min-separation pair in a single transcript language. */
export interface EvidenceVariant {
  language_code: string;
  mention_a: MentionRef;
  mention_b: MentionRef;
  separation_segments: number;
  /** One window when the mentions are close, else one per mention (never empty). */
  passages: Passage[];
  /** Server-computed (computed_field); never recompute on the client. */
  separation_seconds: number;
}

/** One co-occurrence grained by VIDEO (the panel row + the audit/exclusion unit). */
export interface EvidenceItem {
  video_id: string;
  /** The video's strongest co-mention (min separation across its co-occurring languages). */
  representative: EvidenceVariant;
  /** The same pair in the video's OTHER co-occurring languages (the expander); [] if single-language. */
  other_language_variants: EvidenceVariant[];
  video_title: string | null;
  channel_title: string | null;
  /** Server-computed: 1 + other_language_variants.length. */
  cooccurring_language_count: number;
  // No `deep_link`: the client builds a per-passage in-app link via `utils/videoDeepLink.ts`.
}

export interface ConnectionEvidence {
  entity_a_id: string;
  entity_b_id: string;
  items: EvidenceItem[];
  /** Distinct co-occurring VIDEOS (one row each; paginate on this). Narrower than the any-source
   *  `/videos` intersection — the panel labels its denominator rather than implying they match. */
  total_available: number;
  /** (video, language) transcript count — "spoken together in N videos (M transcripts)". */
  raw_cooccurrence_count: number;
  /** Page offset these items start at (so `truncated` is offset-aware). */
  offset: number;
  /** Non-transcript basis when `items` is empty; else null. */
  basis_when_empty: "title" | "description" | "tag" | "manual" | null;
  /** Server-computed (computed_field). */
  returned: number;
  truncated: boolean;
}

export interface ConnectionEvidenceParams {
  a: string;
  b: string;
  limit?: number;
  offset?: number;
}

export async function fetchConnectionEvidence(
  { a, b, limit, offset }: ConnectionEvidenceParams,
  signal?: AbortSignal,
): Promise<ConnectionEvidence> {
  const params = new URLSearchParams({ a, b });
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  return apiFetch<ConnectionEvidence>(
    `/graph/connect/evidence?${params.toString()}`,
    {
      ...(signal !== undefined ? { externalSignal: signal } : {}),
    },
  );
}

// --- Explore mode neighborhood (Feature 115) --------------------------------
// Mirrors the `GET /graph/neighborhood` response. Keep field names identical.

/** Trust layer, assigned by the backend; never re-derive it from `edge_type` (FR-024). */
export type EdgeLayer = "verified" | "category" | "co_occurrence";

export interface GraphEdge {
  source_key: string;
  target_key: string;
  edge_type: string;
  layer: EdgeLayer;
  forward: boolean;
  specificity: number | null;
}

export interface SubgraphNode {
  /** Cytoscape wiring id (the element id). Use `node.entity_id` for navigation. */
  node_key: string;
  node: GraphNode;
}

export interface GraphSubgraph {
  nodes: SubgraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  total_available: number;
  seeds: string[];
  at_ceiling: boolean;
}

export interface NeighborhoodParams {
  seeds: string[];
  radius?: number | undefined;
  limit?: number | undefined;
  ceiling?: number | undefined;
  /** Edge-layer/type filter, sent as repeated `edge_types` params. */
  edgeTypes?: string[] | undefined;
  maxCategorySize?: number | undefined;
}

export async function fetchNeighborhood(
  { seeds, radius, limit, ceiling, edgeTypes, maxCategorySize }: NeighborhoodParams,
  signal?: AbortSignal,
): Promise<GraphSubgraph> {
  const params = new URLSearchParams();
  for (const seed of seeds) params.append("seed", seed);
  if (radius !== undefined) params.set("radius", String(radius));
  if (limit !== undefined) params.set("limit", String(limit));
  if (ceiling !== undefined) params.set("ceiling", String(ceiling));
  for (const t of edgeTypes ?? []) params.append("edge_types", t);
  if (maxCategorySize !== undefined) {
    params.set("max_category_size", String(maxCategorySize));
  }
  return apiFetch<GraphSubgraph>(`/graph/neighborhood?${params.toString()}`, {
    timeout: 30000,
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}
