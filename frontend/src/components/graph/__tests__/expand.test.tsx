/**
 * Expanding a node grows the graph IN PLACE (Feature 115, US3: FR-020 / SC-010): the real
 * ConnectionGraph over a fake Cytoscape — no rebuild, positions/pan/zoom preserved, and the
 * double-click wiring. Merge, ceiling and the table action are in ExplorePanel.expand.test.tsx.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

import { ConnectionGraph } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { fake } from "./fakeCytoscape";
import { fixtureSubgraph } from "./fixtures";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

describe("ConnectionGraph in-place growth (FR-020 / SC-010)", () => {
  beforeEach(() => {
    fake.reset();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("adds neighbors without rebuilding, pinning placed nodes and leaving pan/zoom alone", async () => {
    const small = buildSubgraphModel(fixtureSubgraph(2));
    const big = buildSubgraphModel(fixtureSubgraph(6));
    const { rerender } = render(
      <ConnectionGraph model={small} tableId="t" summary="s" updateMode="incremental" />,
    );
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const cy = fake.instances[0]!;
    cy.setPosition("key-a", { x: 10, y: 20 });
    cy.setPosition("key-n0", { x: -30, y: 5 });

    rerender(<ConnectionGraph model={big} tableId="t" summary="s" updateMode="incremental" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(2));

    expect(fake.instances).toHaveLength(1);
    expect(cy.destroy).not.toHaveBeenCalled();
    expect(cy.fit).not.toHaveBeenCalled();
    expect(cy.zoom).not.toHaveBeenCalled();
    expect(cy.pan).not.toHaveBeenCalled();
    expect(fake.layoutCalls[1]).toMatchObject({ randomize: false, fit: false });
    const pinned = fake.layoutCalls[1]!["fixedNodeConstraint"] as {
      nodeId: string;
      position: { x: number; y: number };
    }[];
    expect(pinned).toHaveLength(small.nodes.length);
    expect(pinned.find((p) => p.nodeId === "key-a")?.position).toEqual({ x: 10, y: 20 });
    expect(pinned.find((p) => p.nodeId === "key-n0")?.position).toEqual({ x: -30, y: 5 });
    // Only the new elements were added to the live instance.
    const addedNodes = cy.added.filter((d) => d.group === "nodes").map((d) => d.data["id"]);
    expect(addedNodes).toHaveLength(big.nodes.length);
    expect(new Set(addedNodes).size).toBe(big.nodes.length);
  });

  it("double-click asks to expand a node that has an entity id, and ignores one that does not", async () => {
    const onNodeExpand = vi.fn();
    const sub = fixtureSubgraph(2);
    sub.nodes.push({
      node_key: "key-cat",
      node: { entity_id: null, name: "Cat", label: "Category", is_bridge: true, kb_degree: null, specificity: 3 },
    });
    render(
      <ConnectionGraph
        model={buildSubgraphModel(sub)}
        tableId="t"
        summary="s"
        updateMode="incremental"
        onNodeExpand={onNodeExpand}
      />,
    );
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    fake.instances[0]!.emit("dbltap", "key-cat");
    expect(onNodeExpand).not.toHaveBeenCalled();
    fake.instances[0]!.emit("dbltap", "key-n1");
    expect(onNodeExpand).toHaveBeenCalledExactlyOnceWith("n1");
  });
});
