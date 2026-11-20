import type { GraphConnection, GraphNode } from "../../../api/graph";

export const A_ID = "11111111-1111-4111-8111-111111111111";
export const B_ID = "22222222-2222-4222-8222-222222222222";

export function node(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    entity_id: null,
    name: "Node",
    label: "",
    is_bridge: false,
    kb_degree: null,
    specificity: null,
    ...overrides,
  };
}

export const entityA = node({ entity_id: A_ID, name: "Entity A", label: "Person", kb_degree: 7 });
export const entityB = node({ entity_id: B_ID, name: "Entity B", label: "Person", kb_degree: 0 });

/** A -> shared category -> B, plus a transcript co-occurrence overlay. */
export function fixtureConnection(): GraphConnection {
  const category = node({
    name: "Shared Category",
    label: "Category",
    is_bridge: true,
    specificity: 6.5,
  });
  return {
    entity_a: entityA,
    entity_b: entityB,
    reviewed_verdict: null,
    searched_max_hops: 3,
    any_truncated: false,
    has_connection: true,
    chains: [
      {
        kind: "shared_category",
        truncated: false,
        score: 6.5,
        steps: [
          { edge_type: "IN_CATEGORY", kind: "shared_category", to_node: category, specificity: 6.5, forward: true },
          { edge_type: "IN_CATEGORY", kind: "shared_category", to_node: entityB, specificity: 6.5, forward: false },
        ],
      },
      {
        kind: "co_occurrence_transcript",
        truncated: false,
        score: null,
        steps: [
          { edge_type: "CO_OCCURS_TRANSCRIPT", kind: "co_occurrence_transcript", to_node: entityB, specificity: null, forward: true },
        ],
      },
    ],
  };
}

export function noPathConnection(): GraphConnection {
  return { ...fixtureConnection(), chains: [], has_connection: false };
}

// --- Feature 114: transcript evidence ----------------------------------------
import type {
  ConnectionEvidence,
  EvidenceItem,
  EvidenceVariant,
  MentionRef,
} from "../../../api/graph";

export function fixtureMention(
  overrides: Partial<MentionRef> = {},
): MentionRef {
  return {
    segment_id: 101,
    end_segment_id: null,
    language_code: "en",
    sequence_number: 1,
    start_time: 12.4,
    mention_text: "Alpha",
    match_start: 0,
    match_end: 5,
    detection_method: "rule_match",
    ...overrides,
  };
}

/** One (video, language) variant (the representative, or an expander row). */
export function fixtureVariant(
  overrides: Partial<EvidenceVariant> = {},
): EvidenceVariant {
  return {
    language_code: "en",
    mention_a: fixtureMention(),
    mention_b: fixtureMention({
      segment_id: 103,
      mention_text: "Beta",
      start_time: 20,
    }),
    separation_segments: 2,
    passages: [
      {
        text: "Alpha was discussed alongside Beta here.",
        start_time: 12.4,
        segment_id: 101,
      },
    ],
    separation_seconds: 7.6,
    ...overrides,
  };
}

export function fixtureEvidenceItem(
  overrides: Partial<EvidenceItem> = {},
): EvidenceItem {
  return {
    video_id: "vid00000001",
    representative: fixtureVariant(),
    other_language_variants: [],
    video_title: "Generic Video Title",
    channel_title: "Generic Channel",
    cooccurring_language_count: 1,
    ...overrides,
  };
}

export function fixtureEvidence(
  overrides: Partial<ConnectionEvidence> = {},
): ConnectionEvidence {
  return {
    entity_a_id: A_ID,
    entity_b_id: B_ID,
    items: [fixtureEvidenceItem()],
    total_available: 1,
    raw_cooccurrence_count: 3,
    offset: 0,
    basis_when_empty: null,
    returned: 1,
    truncated: false,
    ...overrides,
  };
}

// --- Feature 115: Explore subgraph -------------------------------------------
import type { EdgeLayer, GraphEdge, GraphSubgraph } from "../../../api/graph";

/** Synthetic neighborhood: 2 seeds + `neighbors` others, edges alternating verified/category. */
export function fixtureSubgraph(neighbors = 10, totalAvailable = neighbors): GraphSubgraph {
  const nodes = [
    { node_key: "key-a", node: entityA },
    { node_key: "key-b", node: entityB },
    ...Array.from({ length: neighbors }, (_, i) => ({
      node_key: `key-n${i}`,
      node: node({ entity_id: `n${i}`, name: `Neighbor ${i}`, label: "Person" }),
    })),
  ];
  const layers: EdgeLayer[] = ["verified", "category", "co_occurrence"];
  const edges: GraphEdge[] = Array.from({ length: neighbors }, (_, i) => ({
    source_key: i % 2 === 0 ? "key-a" : "key-b",
    target_key: `key-n${i}`,
    edge_type: "RELATED_TO",
    layer: layers[i % layers.length] ?? "verified",
    forward: true,
    specificity: null,
  }));
  return {
    nodes,
    edges,
    truncated: totalAvailable > neighbors,
    total_available: totalAvailable,
    seeds: [A_ID, B_ID],
    at_ceiling: false,
  };
}
