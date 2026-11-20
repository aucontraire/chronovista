/**
 * ExplorePanel expansion (Feature 115, US3): a canvas double-click or a table "Expand" merges the
 * node's neighborhood into the view via ONE handler (FR-020), keeps the enabled layers, stops at
 * the ceiling without dropping anything (FR-008), and the table action is keyboard-operable
 * (FR-021). ConnectionGraph and the hooks are stubbed; see expand.test.tsx for the canvas side.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { GraphSubgraph } from "../../../api/graph";
import type { ConnectionModel } from "../connectionModel";
import { ExplorePanel, NODE_CEILING } from "../ExplorePanel";
import { fixtureSubgraph } from "./fixtures";

const baseHook = vi.fn();
const expansionsHook = vi.fn();
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => baseHook(...args),
  useExpansions: (...args: unknown[]) => expansionsHook(...args),
}));

/** A neighborhood of `extra` new nodes around the expanded entity `n0`. */
function expansionOf(extra: number): GraphSubgraph {
  return {
    nodes: [
      { node_key: "key-n0", node: fixtureSubgraph(1).nodes[2]!.node },
      ...Array.from({ length: extra }, (_, i) => ({
        node_key: `key-x${i}`,
        node: { entity_id: `x${i}`, name: `Extra ${i}`, label: "Person", is_bridge: false, kb_degree: null, specificity: null },
      })),
    ],
    edges: Array.from({ length: extra }, (_, i) => ({
      source_key: "key-n0",
      target_key: `key-x${i}`,
      edge_type: "RELATED_TO",
      layer: "verified" as const,
      forward: true,
      specificity: null,
    })),
    truncated: false,
    total_available: extra + 1,
    seeds: ["n0"],
    at_ceiling: false,
  };
}

const graphProps: { model: ConnectionModel; updateMode?: string; onNodeExpand?: (id: string) => void }[] = [];
vi.mock("../ConnectionGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../ConnectionGraph")>()),
  ConnectionGraph: (props: (typeof graphProps)[number]) => {
    graphProps.push(props);
    return <div data-testid="connection-graph" />;
  },
}));

describe("ExplorePanel expansion", () => {
  let expansionByCount: number;

  beforeEach(() => {
    graphProps.length = 0;
    expansionByCount = 3;
    baseHook.mockReset();
    expansionsHook.mockReset();
    baseHook.mockReturnValue({
      subgraph: fixtureSubgraph(4),
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
    expansionsHook.mockImplementation((ids: string[]) => ({
      results: ids.map(() => expansionOf(expansionByCount)),
      pending: 0,
      failed: 0,
    }));
  });

  const expand = (id: string) => act(() => graphProps.at(-1)!.onNodeExpand!(id));
  const latestModel = () => graphProps.at(-1)!.model;

  it("merges a canvas expansion into the view: neighbors added, nothing dropped, deduped", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    const before = latestModel().nodes.map((n) => n.id);
    expect(before).toHaveLength(6);

    // Cytoscape's double-click callback.
    expand("n0");

    const after = latestModel();
    expect(after.nodes).toHaveLength(6 + expansionByCount); // key-n0 already present: deduped
    for (const id of before) expect(after.nodes.map((n) => n.id)).toContain(id);
    expect(after.edges.some((e) => e.id.includes("key-x2"))).toBe(true);
    expect(graphProps.at(-1)!.updateMode).toBe("incremental");
    expect(screen.getByTestId("explore-count")).toHaveTextContent(/9 nodes/);
  });

  it("expands with the layers currently enabled", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /co-occurrence hints/i }));
    expand("n0");
    const [ids, options] = expansionsHook.mock.calls.at(-1)!;
    expect(ids).toEqual(["n0"]);
    expect(options).toMatchObject({ edgeTypes: ["verified", "category", "co_occurrence"] });
  });

  it("table Expand and canvas double-click share one handler, and the button is keyboard-operable", async () => {
    const user = userEvent.setup();
    render(<ExplorePanel seeds={["a", "b"]} />);
    const button = screen.getAllByRole("button", { name: "Expand Neighbor 1" })[0]!;
    button.focus();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(expansionsHook.mock.calls.at(-1)![0]).toEqual(["n1"]);
    expect(latestModel().nodes.length).toBe(6 + expansionByCount);

    // The same entity from the canvas is a no-op (already expanded); no duplicate query.
    expand("n1");
    expect(expansionsHook.mock.calls.at(-1)![0]).toEqual(["n1"]);
    // Seeds are never offered an Expand button.
    expect(screen.queryByRole("button", { name: /Expand Entity A/ })).not.toBeInTheDocument();
  });

  it("refuses an expansion that would pass the ceiling, drops nothing, and says so (FR-008)", () => {
    expansionByCount = NODE_CEILING; // far more than fits
    render(<ExplorePanel seeds={["a", "b"]} />);
    const before = latestModel().nodes.map((n) => n.id);
    expand("n0");
    expect(latestModel().nodes.map((n) => n.id)).toEqual(before);
    expect(screen.getByTestId("explore-ceiling")).toHaveTextContent(/ceiling/i);
    expect(screen.getByTestId("explore-ceiling")).toHaveTextContent(/1 expansion was not added/);
  });

  it("counts only NEW nodes against the ceiling (overlap with the view is deduped)", () => {
    baseHook.mockReturnValue({
      subgraph: fixtureSubgraph(NODE_CEILING - 4), // 248 nodes
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
    expansionByCount = 2; // 2 new + key-n0, which is already shown: exactly fills the ceiling
    render(<ExplorePanel seeds={["a", "b"]} />);
    expand("n0");
    expect(latestModel().nodes).toHaveLength(NODE_CEILING);
    expect(screen.getByTestId("explore-ceiling")).not.toHaveTextContent(/not added/);
  });

  it("at the ceiling, expansion is unavailable: no request is made and Expand buttons are disabled", () => {
    baseHook.mockReturnValue({
      subgraph: fixtureSubgraph(NODE_CEILING - 2),
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
    render(<ExplorePanel seeds={["a", "b"]} />);
    expect(latestModel().nodes).toHaveLength(NODE_CEILING);
    expect(screen.getByTestId("explore-ceiling")).toBeInTheDocument();
    expand("n0");
    expect(expansionsHook.mock.calls.at(-1)![0]).toEqual([]);
    for (const b of screen.getAllByRole("button", { name: /^Expand / })) expect(b).toBeDisabled();
  });

  it("shows a non-blocking error when an expansion fails, keeping the view", () => {
    expansionsHook.mockReturnValue({ results: [undefined], pending: 0, failed: 1 });
    render(<ExplorePanel seeds={["a", "b"]} />);
    expect(screen.getByTestId("explore-expand-error")).toBeInTheDocument();
    expect(latestModel().nodes).toHaveLength(6);
  });
});
