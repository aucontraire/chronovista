/**
 * Pure GraphConnection -> renderable model transform (Feature 113).
 *
 * The graph (Cytoscape) and the accessible table are BOTH built from the one
 * model returned here, so they cannot disagree about which nodes and edges
 * exist (FR-005). No DOM or Cytoscape dependency, so it is unit-testable.
 *
 * Co-occurrence chains (`kind` starts with `co_occurrence_`) are marked
 * `overlay: true`: they are a separate evidence class (two entities appearing
 * together) from knowledge-base edges and must stay visually distinct (FR-007).
 */

import type { ConnectionKind, GraphConnection, GraphNode } from "../../api/graph";

export type NodeRole = "endpoint-a" | "endpoint-b" | "category" | "bridge" | "entity";

export interface ModelNode {
  id: string;
  name: string;
  label: string;
  role: NodeRole;
  /** Server specificity, passed through untouched (FR-008). */
  specificity: number | null;
  /** Pixel diameter; category nodes scale with the server's log-specificity. */
  size: number;
}

export interface ModelEdge {
  id: string;
  source: string;
  target: string;
  edgeType: string;
  /** Human-readable relationship label. */
  relationship: string;
  kind: ConnectionKind;
  overlay: boolean;
  /** A human-confirmed reviewed relationship (not an inferred chain) — rendered distinctly. */
  reviewed?: boolean;
}

export interface ConnectionModel {
  nodes: ModelNode[];
  edges: ModelEdge[];
  endpointAId: string;
  endpointBId: string;
}

/** Above this many nodes the graph is not rendered (FR-024); the table still is. */
export const MAX_RENDERED_NODES = 150;

const ENDPOINT_SIZE = 56;
const DEFAULT_SIZE = 32;
const CATEGORY_MIN = 24;
const CATEGORY_MAX = 64;

/**
 * Category node diameter from the server's log-specificity. The log is already
 * applied server-side, so this is a linear map of that value — never recompute
 * the log client-side.
 */
export function categorySize(specificity: number | null): number {
  if (specificity === null || !Number.isFinite(specificity)) return CATEGORY_MIN;
  return Math.min(CATEGORY_MAX, Math.max(CATEGORY_MIN, CATEGORY_MIN + specificity * 4));
}

export function isOverlayKind(kind: ConnectionKind): boolean {
  return kind.startsWith("co_occurrence_");
}

export function nodeId(node: GraphNode): string {
  return node.entity_id ?? `bridge:${node.label}:${node.name}`;
}

/** "IN_CATEGORY" -> "in category". */
export function relationshipLabel(edgeType: string): string {
  return edgeType.replace(/_/g, " ").toLowerCase();
}

export const KIND_LABELS: Record<ConnectionKind, string> = {
  asserted: "Knowledge-base path",
  shared_referent: "Shared referent",
  shared_category: "Shared category",
  co_occurrence_transcript: "Co-occurrence (transcripts)",
  co_occurrence_titledesc: "Co-occurrence (titles/descriptions)",
  co_occurrence_tags: "Co-occurrence (tags)",
  co_occurrence_manual: "Co-occurrence (manual)",
};

export function buildConnectionModel(connection: GraphConnection): ConnectionModel {
  const endpointAId = nodeId(connection.entity_a);
  const endpointBId = nodeId(connection.entity_b);
  const nodes = new Map<string, ModelNode>();
  const edges = new Map<string, ModelEdge>();

  const addNode = (node: GraphNode): string => {
    const id = nodeId(node);
    const existing = nodes.get(id);
    // Keep the first sighting, but upgrade a missing specificity if a later one has it.
    if (existing) {
      if (existing.specificity === null && node.specificity !== null) {
        existing.specificity = node.specificity;
        if (existing.role === "category") existing.size = categorySize(node.specificity);
      }
      return id;
    }
    let role: NodeRole;
    let size = DEFAULT_SIZE;
    if (id === endpointAId) {
      role = "endpoint-a";
      size = ENDPOINT_SIZE;
    } else if (id === endpointBId) {
      role = "endpoint-b";
      size = ENDPOINT_SIZE;
    } else if (node.label === "Category") {
      role = "category";
      size = categorySize(node.specificity);
    } else if (node.is_bridge) {
      role = "bridge";
    } else {
      role = "entity";
    }
    nodes.set(id, {
      id,
      name: node.name,
      label: node.label,
      role,
      specificity: node.specificity,
      size,
    });
    return id;
  };

  addNode(connection.entity_a);
  addNode(connection.entity_b);

  for (const chain of connection.chains) {
    let previous = endpointAId;
    for (const step of chain.steps) {
      const to = addNode(step.to_node);
      const source = step.forward ? previous : to;
      const target = step.forward ? to : previous;
      const key = `${source}|${target}|${step.edge_type}|${step.kind}`;
      if (!edges.has(key)) {
        edges.set(key, {
          id: `e${edges.size}`,
          source,
          target,
          edgeType: step.edge_type,
          relationship: relationshipLabel(step.edge_type),
          kind: step.kind,
          overlay: isOverlayKind(step.kind),
        });
      }
      previous = to;
    }
  }

  // A reviewed "relationship" verdict is a human-confirmed tie the knowledge base may lack.
  // Synthesize a direct A->B edge so it appears in BOTH the graph and the table (FR-005), and the
  // result reads as CONNECTED rather than "no path" (FR-009) — the human knows what the KB does
  // not. (A "coincidence" verdict is a negative and adds no edge.)
  const verdict = connection.reviewed_verdict;
  if (verdict && verdict.verdict === "relationship") {
    const edgeType = verdict.relation ?? "reviewed_relationship";
    const key = `${endpointAId}|${endpointBId}|${edgeType}|reviewed`;
    if (!edges.has(key)) {
      edges.set(key, {
        id: `e${edges.size}`,
        source: endpointAId,
        target: endpointBId,
        edgeType,
        relationship: `reviewed: ${relationshipLabel(edgeType)}`,
        kind: "asserted",
        overlay: false,
        reviewed: true,
      });
    }
  }

  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    endpointAId,
    endpointBId,
  };
}

/**
 * True when a knowledge-base connection exists: an asserted chain (including a reviewed
 * relationship) or a shared referent. Shared-category and co-occurrence do NOT count — this
 * mirrors the CLI's coverage-gap rule so the coverage view shows alongside such overlays.
 */
export function hasKnowledgeBaseConnection(model: ConnectionModel): boolean {
  return model.edges.some((e) => e.kind === "asserted" || e.kind === "shared_referent");
}

/**
 * Graph-only: collapse parallel co-occurrence edges between the same node pair into one
 * overlay edge labelled "co-occurs" (no channel count — multiplicity must not read as
 * strength). The table keeps every channel; non-co-occurrence edges pass through untouched.
 */
export function collapseParallelOverlays(edges: ModelEdge[]): ModelEdge[] {
  const out: ModelEdge[] = [];
  const seen = new Set<string>();
  for (const e of edges) {
    if (!e.overlay) {
      out.push(e);
      continue;
    }
    const key = [e.source, e.target].sort().join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...e, relationship: "co-occurs" });
  }
  return out;
}
