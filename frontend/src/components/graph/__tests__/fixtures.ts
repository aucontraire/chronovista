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
