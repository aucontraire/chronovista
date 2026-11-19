import { describe, it, expect } from "vitest";

import { buildConnectionModel, categorySize, collapseParallelOverlays, hasKnowledgeBaseConnection } from "../connectionModel";
import { fixtureConnection, noPathConnection, A_ID, B_ID } from "./fixtures";

describe("buildConnectionModel", () => {
  it("marks endpoints and dedupes shared nodes", () => {
    const model = buildConnectionModel(fixtureConnection());
    const roles = Object.fromEntries(model.nodes.map((n) => [n.id, n.role]));
    expect(roles[A_ID]).toBe("endpoint-a");
    expect(roles[B_ID]).toBe("endpoint-b");
    expect(model.nodes).toHaveLength(3); // A, B, one category
  });

  it("flags co-occurrence chains as overlay and keeps KB edges distinct", () => {
    const model = buildConnectionModel(fixtureConnection());
    expect(model.edges.filter((e) => e.overlay).map((e) => e.edgeType)).toEqual([
      "CO_OCCURS_TRANSCRIPT",
    ]);
    expect(model.edges.filter((e) => !e.overlay)).toHaveLength(2);
  });

  it("honours step direction (forward=false reverses the edge)", () => {
    const model = buildConnectionModel(fixtureConnection());
    const reversed = model.edges.find((e) => e.target === A_ID);
    expect(reversed).toBeUndefined();
    const conn = fixtureConnection();
    conn.chains[0]!.steps[0]!.forward = false;
    const m2 = buildConnectionModel(conn);
    expect(m2.edges.some((e) => e.target === A_ID)).toBe(true);
  });

  it("sizes categories from server specificity without recomputing it", () => {
    expect(categorySize(null)).toBe(24);
    expect(categorySize(5)).toBeGreaterThan(categorySize(1));
    expect(categorySize(1000)).toBe(64);
    const model = buildConnectionModel(fixtureConnection());
    expect(model.nodes.find((n) => n.role === "category")?.specificity).toBe(6.5);
  });

  it("synthesizes a direct A->B edge for a reviewed relationship verdict with no chains (US1 HIGH)", () => {
    // A human-confirmed relationship the KB lacks: verdict present, chains empty. It MUST read as
    // CONNECTED (an edge exists, so the page renders the graph, not 'no path') and appear in the
    // table — not a self-contradicting "confirmed relationship" banner + "no path found".
    const conn = noPathConnection();
    conn.reviewed_verdict = {
      verdict: "relationship",
      relation: "associated_with",
      origin: "human",
      settled: true,
      judged_over: [],
      provenance: "test",
    };
    const model = buildConnectionModel(conn);
    const edge = model.edges.find((e) => e.reviewed);
    expect(edge).toBeDefined();
    expect(edge?.source).toBe(A_ID);
    expect(edge?.target).toBe(B_ID);
    expect(model.edges).toHaveLength(1);
  });
});

describe("collapseParallelOverlays", () => {
  it("collapses parallel co-occurrence edges to one 'co-occurs' edge, leaving the model intact", () => {
    const conn = fixtureConnection();
    const co = conn.chains[1]!;
    conn.chains.push(
      { ...co, kind: "co_occurrence_tags", steps: [{ ...co.steps[0]!, kind: "co_occurrence_tags", edge_type: "CO_OCCURS_TAGS" }] },
      { ...co, kind: "co_occurrence_manual", steps: [{ ...co.steps[0]!, kind: "co_occurrence_manual", edge_type: "CO_OCCURS_MANUAL" }] },
    );
    const model = buildConnectionModel(conn);
    expect(model.edges.filter((e) => e.overlay)).toHaveLength(3);
    const collapsed = collapseParallelOverlays(model.edges);
    const overlays = collapsed.filter((e) => e.overlay);
    expect(overlays).toHaveLength(1);
    expect(overlays[0]!.relationship).toBe("co-occurs");
    expect(collapsed.filter((e) => !e.overlay)).toEqual(model.edges.filter((e) => !e.overlay));
    expect(model.edges.filter((e) => e.overlay)).toHaveLength(3);
  });
});

describe("hasKnowledgeBaseConnection", () => {
  it("is false for category + co-occurrence only, and for no edges", () => {
    expect(hasKnowledgeBaseConnection(buildConnectionModel(fixtureConnection()))).toBe(false);
    expect(hasKnowledgeBaseConnection(buildConnectionModel(noPathConnection()))).toBe(false);
  });

  it("is true for a reviewed relationship (synthesized asserted edge)", () => {
    const conn = noPathConnection();
    conn.reviewed_verdict = { verdict: "relationship", relation: "related_to" } as never;
    expect(hasKnowledgeBaseConnection(buildConnectionModel(conn))).toBe(true);
  });
});
