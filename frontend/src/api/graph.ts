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

// --- Transcript-evidence shared types (Feature 114) -------------------------
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

// --- Discussion passages (Feature 118) --------------------------------------
// Mirrors the Feature 118 models in `src/chronovista/models/connection_evidence.py`.
// Keep field names identical.

/** The four proximity windows, in seconds (spec FR-006). */
export const PROXIMITY_WINDOWS = [15, 30, 60, 120] as const;
export type ProximityWindow = (typeof PROXIMITY_WINDOWS)[number];
export const DEFAULT_PROXIMITY_WINDOW: ProximityWindow = 30;

/** One co-mention of a passage, by time only (a passage's "other moments"). */
export interface CoMoment {
  start_time: number;
  gap_seconds: number;
}

export interface PassageSegment {
  segment_id: number;
  /** Position in the transcript; `closest.segments` is sorted by it. Gaps mean omitted text. */
  sequence_number: number;
  start_time: number;
  /** Effective (corrected-or-raw) text. */
  text: string;
  /** The segment after a mention: reading context, rendered dimmed. */
  is_context: boolean;
}

/** A passage's closest co-mention, with its text. `mention_a`/`mention_b` follow the request's a/b. */
export interface PassageMoment {
  gap_seconds: number;
  /** Deep-link `t`. */
  start_time: number;
  /** Deep-link `seg`. */
  segment_id: number;
  mention_a: MentionRef;
  mention_b: MentionRef;
  segments: PassageSegment[];
}

/** Co-mentions in one video and language, merged by the chaining rule. */
export interface LanguagePassage {
  language_code: string;
  start_time: number;
  end_time: number;
  co_mention_count: number;
  closest_gap_seconds: number;
  closest: PassageMoment;
  other_moments: CoMoment[];
  name_list: boolean;
}

/** Overlapping language passages of one video; `variants[0]` leads. Counts once. */
export interface GroupedPassage {
  start_time: number;
  end_time: number;
  closest_gap_seconds: number;
  variants: LanguagePassage[];
}

export interface VideoPassages {
  video_id: string;
  video_title: string | null;
  channel_title: string | null;
  /** Over ALL its passages, folded or not. */
  closest_gap_seconds: number;
  /** All of them, in time order; the panel folds after 3. */
  passages: GroupedPassage[];
}

export interface FailedScope {
  video_id: string;
  language_code: string;
  video_title: string | null;
  channel_title: string | null;
}

export type PairPassagesState =
  | "passages"
  | "not_computed"
  | "no_transcript"
  | "no_passage_in_window";

export interface PairPassages {
  entity_a_id: string;
  entity_b_id: string;
  window_seconds: ProximityWindow;
  passage_rule_version: string;
  items: VideoPassages[];
  offset: number;
  /** Totals over every video in the window, never just this page. */
  video_count: number;
  passage_count: number;
  channel_count: number;
  closest_gap_seconds: number | null;
  /** Videos where both are spoken but never within the window; not in the totals above. */
  farther_video_count: number;
  pending_scopes: number;
  failed_scopes: FailedScope[];
  state: PairPassagesState;
  basis_when_empty: "title" | "description" | "tag" | "manual" | null;
  /** Server-computed (computed_field). */
  returned: number;
  truncated: boolean;
}

export interface FartherVideo {
  video_id: string;
  video_title: string | null;
  channel_title: string | null;
  language_code: string;
  nearest_gap_seconds: number;
  nearest_start_time: number;
}

export interface FartherVideos {
  items: FartherVideo[];
  offset: number;
  total: number;
  returned: number;
  truncated: boolean;
}

export interface PairPassagesParams {
  a: string;
  b: string;
  window: ProximityWindow;
  limit?: number;
  offset?: number;
}

function pairPassagesQuery({ a, b, window, limit, offset }: PairPassagesParams): string {
  const params = new URLSearchParams({ a, b, window: String(window) });
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  return params.toString();
}

export async function fetchPairPassages(
  params: PairPassagesParams,
  signal?: AbortSignal,
): Promise<PairPassages> {
  return apiFetch<PairPassages>(
    `/graph/connect/passages?${pairPassagesQuery(params)}`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) },
  );
}

export async function fetchFartherVideos(
  params: PairPassagesParams,
  signal?: AbortSignal,
): Promise<FartherVideos> {
  return apiFetch<FartherVideos>(
    `/graph/connect/passages/farther?${pairPassagesQuery(params)}`,
    { ...(signal !== undefined ? { externalSignal: signal } : {}) },
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
