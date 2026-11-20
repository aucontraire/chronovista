/**
 * Trust layers in Explore mode (Feature 115, US2): distinct per-layer styling hooks, co-occurrence
 * off by default, independent toggles, and parallel edges kept distinct (FR-006/7/21/23).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { GraphSubgraph } from "../../../api/graph";
import { toCytoscapeElements } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { EdgeLayerControls, DEFAULT_ENABLED_LAYERS } from "../EdgeLayerControls";
import { ExplorePanel } from "../ExplorePanel";
import { fixtureSubgraph } from "./fixtures";

const hookMock = vi.fn();
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => hookMock(...args),
  useExpansions: () => ({ results: [], pending: 0, failed: 0 }),
}));
vi.mock("../ConnectionGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../ConnectionGraph")>()),
  ConnectionGraph: () => <div data-testid="connection-graph" />,
}));

/** A verified edge AND a co-occurrence edge between the same two nodes, plus a category edge. */
function parallelSubgraph(): GraphSubgraph {
  const base = fixtureSubgraph(2);
  return {
    ...base,
    edges: [
      { source_key: "key-a", target_key: "key-n0", edge_type: "LINKED", layer: "verified", forward: true, specificity: null },
      // Same edge_type in another layer, and two co-occurrence edges: none may merge.
      { source_key: "key-a", target_key: "key-n0", edge_type: "LINKED", layer: "co_occurrence", forward: true, specificity: null },
      { source_key: "key-a", target_key: "key-n0", edge_type: "CO_OCCURS_TAGS", layer: "co_occurrence", forward: true, specificity: null },
      { source_key: "key-b", target_key: "key-n1", edge_type: "IN_CATEGORY", layer: "category", forward: true, specificity: null },
    ],
  };
}

function lastEdgeTypes(): string[] {
  const call = hookMock.mock.calls.at(-1);
  return (call?.[1] as { edgeTypes: string[] }).edgeTypes;
}

describe("edge layer styling hooks", () => {
  it("gives each layer its own class and data.layer, from the backend layer", () => {
    const edges = toCytoscapeElements(buildSubgraphModel(parallelSubgraph())).filter(
      (e) => e.group === "edges",
    );
    const byLayer = new Map(edges.map((e) => [e.data["layer"], e.classes]));
    expect(byLayer.get("verified")).toContain("layer-verified");
    expect(byLayer.get("category")).toContain("layer-category");
    expect(byLayer.get("co_occurrence")).toContain("layer-co_occurrence");
    expect(new Set(byLayer.values()).size).toBe(3);
  });

  it("keeps parallel edges between the same pair as distinct edges (FR-023)", () => {
    const edges = toCytoscapeElements(buildSubgraphModel(parallelSubgraph())).filter(
      (e) => e.group === "edges" && e.data["source"] === "key-a" && e.data["target"] === "key-n0",
    );
    expect(edges).toHaveLength(3);
    expect(new Set(edges.map((e) => e.data["id"])).size).toBe(3);
    expect(edges.map((e) => e.data["layer"]).sort()).toEqual([
      "co_occurrence",
      "co_occurrence",
      "verified",
    ]);
  });
});

describe("EdgeLayerControls", () => {
  it("shows verified + category on and co-occurrence off by default, as real checkboxes", () => {
    render(<EdgeLayerControls enabled={DEFAULT_ENABLED_LAYERS} onToggle={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: /verified relationships/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /shared categories/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /co-occurrence hints/i })).not.toBeChecked();
  });

  it("states the line style in text so the legend does not rely on colour", () => {
    render(<EdgeLayerControls enabled={DEFAULT_ENABLED_LAYERS} onToggle={vi.fn()} />);
    expect(screen.getByText(/solid line/)).toBeInTheDocument();
    expect(screen.getByText(/dashed line/)).toBeInTheDocument();
    expect(screen.getByText(/dotted, faint line/)).toBeInTheDocument();
  });
});

describe("ExplorePanel layer toggles", () => {
  beforeEach(() => {
    hookMock.mockReset();
    hookMock.mockReturnValue({
      subgraph: parallelSubgraph(),
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
  });

  it("does not request co-occurrence until it is switched on", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    expect(lastEdgeTypes()).toEqual(["verified", "category"]);
  });

  it("toggling a layer adds or removes exactly that layer", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /co-occurrence hints/i }));
    expect(lastEdgeTypes()).toEqual(["verified", "category", "co_occurrence"]);
    fireEvent.click(screen.getByRole("checkbox", { name: /verified relationships/i }));
    expect(lastEdgeTypes()).toEqual(["category", "co_occurrence"]);
  });

  it("never sends an empty edge_types (the server would default it) when all layers are off", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /verified relationships/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /shared categories/i }));
    expect(hookMock.mock.calls.at(-1)?.[1]).toMatchObject({ enabled: false });
    expect(screen.getByTestId("explore-no-layers")).toBeInTheDocument();
    expect(screen.queryByTestId("connection-graph")).not.toBeInTheDocument();
  });

  it("labels each table row with its layer, not Connect's wording", () => {
    render(<ExplorePanel seeds={["a", "b"]} />);
    const table = screen.getByRole("table", { name: /trust layer/i });
    expect(within(table).queryByText(/knowledge-base path/i)).not.toBeInTheDocument();
    expect(within(table).getByText(/^Verified relationship/)).toBeInTheDocument();
    expect(within(table).getByText(/^Shared category$/)).toBeInTheDocument();
    expect(within(table).getAllByText(/^Co-occurrence hint/)).toHaveLength(2);
  });
});
