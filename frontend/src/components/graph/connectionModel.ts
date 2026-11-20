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

import type {
  ConnectionKind,
  EdgeLayer,
  GraphConnection,
  GraphEdge,
  GraphNode,
  GraphSubgraph,
} from "../../api/graph";

export type NodeRole = "endpoint-a" | "endpoint-b" | "category" | "bridge" | "entity";

export interface ModelNode {
  id: string;
  name: string;
  label: string;
  role: NodeRole;
  /** Explore only: the entity to navigate/expand by (the id above is the graph wiring key). */
  entityId?: string | null;
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
  /** Explore only: the backend-assigned trust layer, carried through untouched (FR-024). */
  layer?: EdgeLayer;
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

/** Layer-accurate wording for Explore (FR-006); the table and legend both read this. */
export const LAYER_LABELS: Record<EdgeLayer, string> = {
  verified: "Verified relationship (knowledge base)",
  category: "Shared category",
  co_occurrence: "Co-occurrence hint (appear together; not a knowledge-base fact)",
};

/**
 * Explore mode: GraphSubgraph -> the same ConnectionModel Connect uses, so the graph and the
 * table render it through the unchanged Connect code path. Element ids are the server's
 * `node_key` and a content-derived edge key that includes the layer (stable across refetches,
 * and distinct for parallel edges in different layers — FR-023). The backend `layer` is carried
 * through as-is; it is never derived from `edge_type` (FR-024). Styling and wording read
 * `layer`; `kind` below only satisfies the Connect-shaped `ModelEdge` type.
 */
/** Composite edge identity: dedupes merged expansions and keeps parallel layers distinct. */
export function edgeKey(e: GraphEdge): string {
  return `${e.source_key}|${e.target_key}|${e.edge_type}|${e.layer}`;
}

const LAYER_KIND: Record<EdgeLayer, ConnectionKind> = {
  verified: "asserted",
  category: "shared_category",
  co_occurrence: "co_occurrence_transcript",
};

export function buildSubgraphModel(subgraph: GraphSubgraph): ConnectionModel {
  const [seedA, seedB] = subgraph.seeds;
  const isSeed = (seed: string | undefined, key: string, entityId: string | null) =>
    seed !== undefined && (seed === key || seed === entityId);

  const nodes: ModelNode[] = subgraph.nodes.map(({ node_key, node }) => {
    let role: NodeRole = "entity";
    let size = DEFAULT_SIZE;
    if (isSeed(seedA, node_key, node.entity_id)) {
      role = "endpoint-a";
      size = ENDPOINT_SIZE;
    } else if (isSeed(seedB, node_key, node.entity_id)) {
      role = "endpoint-b";
      size = ENDPOINT_SIZE;
    } else if (node.label === "Category") {
      role = "category";
      size = categorySize(node.specificity);
    } else if (node.is_bridge) {
      role = "bridge";
    }
    return {
      id: node_key,
      name: node.name,
      label: node.label,
      role,
      specificity: node.specificity,
      size,
      entityId: node.entity_id,
    };
  });

  const edges: ModelEdge[] = subgraph.edges.map((e) => {
    const source = e.forward ? e.source_key : e.target_key;
    const target = e.forward ? e.target_key : e.source_key;
    return {
      id: edgeKey(e),
      source,
      target,
      edgeType: e.edge_type,
      relationship: relationshipLabel(e.edge_type),
      kind: LAYER_KIND[e.layer],
      overlay: e.layer === "co_occurrence",
      layer: e.layer,
    };
  });

  const idOf = (role: NodeRole) => nodes.find((n) => n.role === role)?.id ?? "";
  return {
    nodes,
    edges,
    endpointAId: idOf("endpoint-a"),
    endpointBId: idOf("endpoint-b"),
  };
}

export interface MergedNeighborhood {
  subgraph: GraphSubgraph;
  /** Expansions refused because merging them would pass the ceiling (FR-008). */
  refused: number;
  /** True when the ceiling is reached or an expansion was refused. */
  atCeiling: boolean;
}

/**
 * Client-side accumulation of expansions into the base neighborhood (FR-020/FR-008). Nodes are
 * deduped by `node_key`, edges by {@link edgeKey}. An expansion that would take the node count
 * past `ceiling` is refused whole: nothing already shown is ever dropped. `total_available`
 * grows by the nodes added plus each expansion's own unseen remainder.
 */
export function mergeExpansions(
  base: GraphSubgraph,
  expansions: readonly (GraphSubgraph | undefined)[],
  ceiling: number,
): MergedNeighborhood {
  const nodes = new Map(base.nodes.map((n) => [n.node_key, n]));
  const edges = new Map(base.edges.map((e) => [edgeKey(e), e]));
  let total = base.total_available;
  let truncated = base.truncated;
  let refused = 0;

  for (const exp of expansions) {
    if (!exp) continue;
    const incoming = exp.nodes.filter((n) => !nodes.has(n.node_key));
    if (nodes.size + incoming.length > ceiling) {
      refused += 1;
      continue;
    }
    for (const n of incoming) nodes.set(n.node_key, n);
    for (const e of exp.edges) edges.set(edgeKey(e), e);
    total += incoming.length + Math.max(0, exp.total_available - exp.nodes.length);
    truncated = truncated || exp.truncated;
  }

  return {
    subgraph: {
      ...base,
      nodes: [...nodes.values()],
      edges: [...edges.values()],
      truncated,
      total_available: Math.max(total, nodes.size),
    },
    refused,
    atCeiling: refused > 0 || nodes.size >= ceiling,
  };
}

// --- Focus filters (node kinds + relationship types) --------------------------------------
// One computation decides what is hidden; the canvas (display:none, positions untouched) and the
// accessible table (a filtered copy of the model) both consume its result, so they cannot
// disagree about what is visible (SC-004).

export interface ModelFilter {
  /** Node kinds to hide: an entity type (lower-case label) or "category" / "bridge". */
  hiddenNodeKinds: ReadonlySet<string>;
  /** Relationship types (`ModelEdge.edgeType`) to hide. */
  hiddenRelationships: ReadonlySet<string>;
}

export const NO_FILTER: ModelFilter = {
  hiddenNodeKinds: new Set(),
  hiddenRelationships: new Set(),
};

/** The legend/filter key of a node: its structural kind, else its entity type. */
export function nodeKind(node: ModelNode): string {
  if (node.role === "category") return "category";
  if (node.role === "bridge") return "bridge";
  return node.label.toLowerCase();
}

export function isEndpoint(node: ModelNode): boolean {
  return node.role === "endpoint-a" || node.role === "endpoint-b";
}

/**
 * Ids of the nodes and edges to hide. Endpoints are never hidden; an edge is hidden when its
 * relationship type is hidden or either end is hidden (it cannot be drawn without its node).
 */
export function computeHiddenIds(model: ConnectionModel, filter: ModelFilter): ReadonlySet<string> {
  const hidden = new Set<string>();
  for (const n of model.nodes) {
    if (!isEndpoint(n) && filter.hiddenNodeKinds.has(nodeKind(n))) hidden.add(n.id);
  }
  for (const e of model.edges) {
    if (
      filter.hiddenRelationships.has(e.edgeType) ||
      hidden.has(e.source) ||
      hidden.has(e.target)
    ) {
      hidden.add(e.id);
    }
  }
  return hidden;
}

/** The model as the table must show it: the same elements the canvas leaves visible. */
export function withoutHidden(model: ConnectionModel, hidden: ReadonlySet<string>): ConnectionModel {
  if (hidden.size === 0) return model;
  return {
    ...model,
    nodes: model.nodes.filter((n) => !hidden.has(n.id)),
    edges: model.edges.filter((e) => !hidden.has(e.id)),
  };
}
