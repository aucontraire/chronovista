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

// --- Features 114/118: discussion passages -----------------------------------
import type {
  GroupedPassage,
  LanguagePassage,
  MentionRef,
  PairPassages,
  PassageSegment,
  VideoPassages,
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

/** Two mention segments (one per name) followed by one dimmed context segment. */
export function fixtureSegments(): PassageSegment[] {
  return [
    { segment_id: 101, sequence_number: 20, start_time: 12.4, text: "Alpha came up first.", is_context: false },
    { segment_id: 102, sequence_number: 21, start_time: 16, text: "Then Beta was named.", is_context: false },
    { segment_id: 103, sequence_number: 22, start_time: 20, text: "Afterwards they moved on.", is_context: true },
  ];
}

/** One (video, language) passage: its closest co-mention as segments, plus other moments. */
export function fixtureLanguagePassage(
  overrides: Partial<LanguagePassage> = {},
): LanguagePassage {
  return {
    language_code: "en",
    start_time: 12.4,
    end_time: 80,
    co_mention_count: 1,
    closest_gap_seconds: 7.6,
    closest: {
      gap_seconds: 7.6,
      start_time: 12.4,
      segment_id: 101,
      mention_a: fixtureMention(),
      mention_b: fixtureMention({ segment_id: 102, mention_text: "Beta", start_time: 16 }),
      segments: fixtureSegments(),
    },
    other_moments: [],
    name_list: false,
    ...overrides,
  };
}

export function fixtureGroupedPassage(
  overrides: Partial<GroupedPassage> = {},
): GroupedPassage {
  return {
    start_time: 12.4,
    end_time: 80,
    closest_gap_seconds: 7.6,
    variants: [fixtureLanguagePassage()],
    ...overrides,
  };
}

export function fixtureVideoPassages(
  overrides: Partial<VideoPassages> = {},
): VideoPassages {
  return {
    video_id: "vid00000001",
    video_title: "Generic Video Title",
    channel_title: "Generic Channel",
    closest_gap_seconds: 7.6,
    passages: [fixtureGroupedPassage()],
    ...overrides,
  };
}

export function fixturePairPassages(
  overrides: Partial<PairPassages> = {},
): PairPassages {
  return {
    entity_a_id: A_ID,
    entity_b_id: B_ID,
    window_seconds: 30,
    passage_rule_version: "v1",
    items: [fixtureVideoPassages()],
    offset: 0,
    video_count: 1,
    passage_count: 1,
    channel_count: 1,
    closest_gap_seconds: 7.6,
    farther_video_count: 0,
    pending_scopes: 0,
    failed_scopes: [],
    state: "passages",
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
