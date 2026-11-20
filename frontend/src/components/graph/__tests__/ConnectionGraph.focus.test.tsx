/**
 * Focus filters and hover name on the real ConnectionGraph over the fake Cytoscape:
 * hidden ids are hidden IN PLACE (class only — nothing removed, no re-layout), and hovering a node
 * shows its full name.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

import { ConnectionGraph } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { fake } from "./fakeCytoscape";
import { fixtureSubgraph } from "./fixtures";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

describe("ConnectionGraph focus filters", () => {
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

  it("hides elements in place by class, restores them, and never re-lays-out or removes", async () => {
    const model = buildSubgraphModel(fixtureSubgraph(4));
    const { rerender } = render(<ConnectionGraph model={model} tableId="t" summary="s" updateMode="incremental" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const cy = fake.instances[0]!;
    const addedBefore = cy.added.length;
    const edge = model.edges[0]!.id;

    rerender(
      <ConnectionGraph model={model} tableId="t" summary="s" updateMode="incremental" hiddenIds={new Set(["key-n0", edge])} />,
    );
    await waitFor(() => expect(cy.withClass("filtered").sort()).toEqual(["key-n0", edge].sort()));
    expect(cy.added).toHaveLength(addedBefore);
    expect(fake.layoutCalls).toHaveLength(1);
    expect(cy.destroy).not.toHaveBeenCalled();

    rerender(<ConnectionGraph model={model} tableId="t" summary="s" updateMode="incremental" hiddenIds={new Set()} />);
    await waitFor(() => expect(cy.withClass("filtered")).toEqual([]));
    expect(fake.layoutCalls).toHaveLength(1);
  });

  it("hides new elements that arrive already filtered (an expansion of a hidden type)", async () => {
    const small = buildSubgraphModel(fixtureSubgraph(2));
    const big = buildSubgraphModel(fixtureSubgraph(5));
    const hidden = new Set(["key-n4"]);
    const { rerender } = render(
      <ConnectionGraph model={small} tableId="t" summary="s" updateMode="incremental" hiddenIds={hidden} />,
    );
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    rerender(<ConnectionGraph model={big} tableId="t" summary="s" updateMode="incremental" hiddenIds={hidden} />);
    await waitFor(() => expect(fake.instances[0]!.withClass("filtered")).toEqual(["key-n4"]));
  });
});

describe("ConnectionGraph hover name", () => {
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

  async function setup() {
    const sub = fixtureSubgraph(2);
    sub.nodes[2]!.node.name = "A very long entity name that the canvas label truncates with an ellipsis";
    const view = render(<ConnectionGraph model={buildSubgraphModel(sub)} tableId="t" summary="s" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    return { cy: fake.instances[0]!, ...view };
  }

  it("shows the full untruncated name on mouseover and clears on mouseout", async () => {
    const { cy } = await setup();
    act(() => cy.emit("mouseover", "key-n0"));
    expect(screen.getByTestId("node-hover-name")).toHaveTextContent(
      "A very long entity name that the canvas label truncates with an ellipsis",
    );
    act(() => cy.emit("mouseout", "key-n0"));
    expect(screen.queryByTestId("node-hover-name")).not.toBeInTheDocument();
  });

  it("clears on pan/zoom (the node moved under it), is mouse-only (aria-hidden), and leaves no focus stop", async () => {
    const { cy } = await setup();
    act(() => cy.emit("mouseover", "key-n0"));
    const tip = screen.getByTestId("node-hover-name");
    expect(tip).toHaveAttribute("aria-hidden", "true");
    expect(tip).not.toHaveAttribute("tabindex");
    act(() => cy.emit("pan"));
    expect(screen.queryByTestId("node-hover-name")).not.toBeInTheDocument();
  });

  it("removes the tooltip when the graph is torn down", async () => {
    const { cy, unmount } = await setup();
    act(() => cy.emit("mouseover", "key-n0"));
    unmount();
    expect(screen.queryByTestId("node-hover-name")).not.toBeInTheDocument();
    expect(cy.destroy).toHaveBeenCalled();
  });
});
