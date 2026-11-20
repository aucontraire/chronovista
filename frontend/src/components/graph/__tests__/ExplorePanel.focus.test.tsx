/**
 * Focus filters in Explore: node-type toggles (legend), relationship-type toggles, and the
 * one-model-two-views guardrail — the table lists exactly what the graph leaves visible (SC-004).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { GraphEdge, GraphSubgraph, SubgraphNode } from "../../../api/graph";
import type { ConnectionModel } from "../connectionModel";
import { ExplorePanel } from "../ExplorePanel";
import { A_ID, B_ID, entityA, entityB, node } from "./fixtures";

const baseHook = vi.fn();
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => baseHook(...args),
  useExpansions: () => ({ results: [], pending: 0, failed: 0 }),
}));

const graphProps: { model: ConnectionModel; hiddenIds?: ReadonlySet<string> }[] = [];
vi.mock("../ConnectionGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../ConnectionGraph")>()),
  ConnectionGraph: (props: (typeof graphProps)[number]) => {
    graphProps.push(props);
    return <div data-testid="connection-graph" />;
  },
}));

function n(key: string, name: string, label: string, bridge = false): SubgraphNode {
  return { node_key: key, node: node({ entity_id: bridge ? null : key, name, label, is_bridge: bridge }) };
}
function e(source: string, target: string, type: string, layer: GraphEdge["layer"] = "verified"): GraphEdge {
  return { source_key: source, target_key: target, edge_type: type, layer, forward: true, specificity: null };
}

/** Endpoints A/B (the only people), two organizations, a place, a category and a bridge value. */
function subgraph(): GraphSubgraph {
  return {
    nodes: [
      { node_key: "key-a", node: entityA },
      { node_key: "key-b", node: entityB },
      n("org1", "Org One", "organization"),
      n("org2", "Org Two", "organization"),
      n("pl1", "Place One", "place"),
      n("cat1", "Category One", "Category", true),
      n("br1", "Office One", "WikidataItem", true),
    ],
    edges: [
      e("key-a", "org1", "EMPLOYER"),
      e("key-a", "org2", "EMPLOYER"),
      e("key-b", "pl1", "EDUCATED_AT"),
      e("key-b", "br1", "POSITION_HELD"),
      e("key-a", "cat1", "IN_CATEGORY", "category"),
      e("org1", "pl1", "LOCATED_IN"),
    ],
    truncated: false,
    total_available: 7,
    seeds: [A_ID, B_ID],
    at_ceiling: false,
  };
}

const latest = () => graphProps.at(-1)!;
const tableRows = () => within(screen.getByRole("table")).getAllByRole("row").length - 1;
const tableText = () => screen.getByRole("table").textContent ?? "";

function setSubgraph(sub: GraphSubgraph) {
  baseHook.mockReturnValue({ subgraph: sub, isLoading: false, failure: null, refetch: vi.fn() });
}

describe("node-type toggles (legend as filter)", () => {
  beforeEach(() => {
    graphProps.length = 0;
    baseHook.mockReset();
    setSubgraph(subgraph());
  });

  it("hides that type's nodes and incident edges in the graph AND the table; endpoints stay", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    expect(tableRows()).toBe(6);

    fireEvent.click(screen.getByRole("checkbox", { name: "Organization" }));
    const hidden = latest().hiddenIds!;
    // org1, org2 and every edge touching them (3 EMPLOYER/LOCATED_IN edges) are hidden.
    expect([...hidden].filter((id) => !id.includes("|")).sort()).toEqual(["org1", "org2"]); // nodes
    expect([...hidden].filter((id) => id.includes("|"))).toHaveLength(3); // their incident edges
    expect(hidden.has("key-a") || hidden.has("key-b")).toBe(false);
    expect(tableRows()).toBe(3);
    expect(tableText()).not.toContain("Org One");
    expect(tableText()).toContain("Entity A");
    expect(screen.getByTestId("explore-count")).toHaveTextContent("2 hidden by filters");

    fireEvent.click(screen.getByRole("checkbox", { name: "Organization" }));
    expect(latest().hiddenIds!.size).toBe(0);
    expect(tableRows()).toBe(6);
  });

  it("covers the structural kinds too (category, reference value)", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Shared category" }));
    expect(latest().hiddenIds!.has("cat1")).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: /Reference value/ }));
    expect(latest().hiddenIds!.has("br1")).toBe(true);
    expect(tableText()).not.toContain("Office One");
    expect(tableText()).not.toContain("Category One");
  });

  it("never hides an endpoint: a type present only as endpoints cannot be toggled", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    const person = screen.getByRole("checkbox", { name: /Person/ });
    expect(person).toBeDisabled();
    fireEvent.click(person);
    expect(latest().hiddenIds!.size).toBe(0);
  });

  it("an endpoint stays visible even if its type is hidden through other nodes of that type", () => {
    const sub = subgraph();
    sub.nodes.push(n("p9", "Another Person", "Person"));
    sub.edges.push(e("key-a", "p9", "FRIEND_OF"));
    setSubgraph(sub);
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    expect(latest().hiddenIds!.has("p9")).toBe(true);
    expect(latest().hiddenIds!.has("key-a")).toBe(false);
    expect(latest().hiddenIds!.has("key-b")).toBe(false);
    expect(tableText()).toContain("Entity A");
  });
});

describe("relationship-type toggles", () => {
  beforeEach(() => {
    graphProps.length = 0;
    baseHook.mockReset();
    setSubgraph(subgraph());
  });

  const filter = () => screen.getByTestId("relationship-filter");

  it("lists each relationship type present, with counts, as labelled checkboxes", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    expect(within(filter()).getByRole("checkbox", { name: /employer \(2\)/ })).toBeChecked();
    expect(within(filter()).getByRole("checkbox", { name: /educated at \(1\)/ })).toBeChecked();
    expect(within(filter()).getByRole("checkbox", { name: /in category \(1\)/ })).toBeChecked();
  });

  it("hiding a type hides every edge of it in the graph and the table, and keeps the nodes", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    fireEvent.click(within(filter()).getByRole("checkbox", { name: /employer/ }));
    const hidden = latest().hiddenIds!;
    const employerEdges = latest().model.edges.filter((e) => e.edgeType === "EMPLOYER").map((e) => e.id);
    expect(employerEdges).toHaveLength(2);
    for (const id of employerEdges) expect(hidden.has(id)).toBe(true);
    expect(hidden.has("org1")).toBe(false); // nodes are untouched by a relationship toggle
    expect(tableRows()).toBe(4);
    expect(within(screen.getByRole("table")).queryByText("employer")).not.toBeInTheDocument();
  });

  it("Hide all / Show all", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    fireEvent.click(within(filter()).getByRole("button", { name: "Hide all" }));
    expect(latest().hiddenIds!.size).toBe(latest().model.edges.length);
    expect(tableRows()).toBe(0);
    fireEvent.click(within(filter()).getByRole("button", { name: "Show all" }));
    expect(latest().hiddenIds!.size).toBe(0);
    expect(tableRows()).toBe(6);
  });

  it("composes with the edge layers: a hidden relationship stays hidden when new data arrives", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    fireEvent.click(within(filter()).getByRole("checkbox", { name: /employer/ }));
    // Switching a layer on refetches; the new result carries another EMPLOYER edge.
    const next = subgraph();
    next.nodes.push(n("org3", "Org Three", "organization"));
    next.edges.push(e("key-b", "org3", "EMPLOYER", "co_occurrence"));
    setSubgraph(next);
    fireEvent.click(screen.getByRole("checkbox", { name: /co-occurrence hints/i }));
    const employer = latest().model.edges.filter((e) => e.edgeType === "EMPLOYER");
    expect(employer).toHaveLength(3);
    for (const edge of employer) expect(latest().hiddenIds!.has(edge.id)).toBe(true);
  });
});

describe("keyboard operation", () => {
  it("node-type and relationship toggles are reachable and operable with the keyboard", async () => {
    graphProps.length = 0;
    baseHook.mockReset();
    setSubgraph(subgraph());
    const user = userEvent.setup();
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);

    const org = screen.getByRole("checkbox", { name: "Organization" });
    org.focus();
    await user.keyboard(" ");
    expect(org).not.toBeChecked();
    expect(latest().hiddenIds!.has("org1")).toBe(true);

    const hideAll = within(screen.getByTestId("relationship-filter")).getByRole("button", { name: "Hide all" });
    hideAll.focus();
    await user.keyboard("{Enter}");
    expect(tableRows()).toBe(0);
  });
});

describe("one model, two views (SC-004)", () => {
  beforeEach(() => {
    graphProps.length = 0;
    baseHook.mockReset();
    setSubgraph(subgraph());
  });

  it("the table lists exactly the edges the graph leaves visible, for any combination", () => {
    render(<ExplorePanel seeds={[A_ID, B_ID]} />);
    const steps: (() => void)[] = [
      () => fireEvent.click(screen.getByRole("checkbox", { name: "Organization" })),
      () => fireEvent.click(screen.getByRole("checkbox", { name: /educated at/ })),
      () => fireEvent.click(screen.getByRole("checkbox", { name: "Shared category" })),
      () => fireEvent.click(screen.getByRole("checkbox", { name: /Reference value/ })),
      () => fireEvent.click(screen.getByRole("checkbox", { name: "Place" })),
    ];
    for (const step of [() => undefined, ...steps]) {
      step();
      const { model, hiddenIds } = latest();
      const visibleEdges = model.edges.filter((e) => !hiddenIds!.has(e.id));
      const visibleNodes = model.nodes.filter((nn) => !hiddenIds!.has(nn.id));
      expect(tableRows()).toBe(visibleEdges.length);
      for (const nn of model.nodes) {
        const inTable = tableText().includes(nn.name);
        // A node appears in the table only if it is visible AND has a visible edge.
        if (hiddenIds!.has(nn.id)) expect(inTable).toBe(false);
      }
      // No visible edge touches a hidden node.
      for (const ed of visibleEdges) {
        expect(visibleNodes.some((nn) => nn.id === ed.source)).toBe(true);
        expect(visibleNodes.some((nn) => nn.id === ed.target)).toBe(true);
      }
    }
  });
});
