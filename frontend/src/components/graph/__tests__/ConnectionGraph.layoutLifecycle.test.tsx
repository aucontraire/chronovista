/**
 * Initial-layout robustness on the real ConnectionGraph over the fake Cytoscape:
 *  - a from-scratch layout runs only after the canvas was resized to its real size;
 *  - a re-render that hands over an identical model never interrupts a layout in flight;
 *  - incremental updates and maximize stay resize-only (no new layout, no pre-layout resize).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

import { ConnectionGraph } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { fake } from "./fakeCytoscape";
import { fixtureSubgraph } from "./fixtures";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

describe("ConnectionGraph initial layout", () => {
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

  const props = { tableId: "t", summary: "s", updateMode: "incremental" as const };

  it("resizes the canvas to its real size immediately before the from-scratch layout", async () => {
    render(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(4))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const at = fake.events.indexOf("layout");
    expect(fake.events[at - 1]).toBe("resize");
    expect(fake.layoutCalls[0]).toMatchObject({ randomize: true, fit: true });
  });

  it("does not resize before, or re-lay-out on, an incremental update", async () => {
    const { rerender } = render(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(2))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const resizes = fake.events.filter((e) => e === "resize").length;
    rerender(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(6))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(2));
    expect(fake.events.filter((e) => e === "resize")).toHaveLength(resizes);
    expect(fake.layoutCalls[1]).toMatchObject({ randomize: false, fit: false });
  });

  it("leaves a layout in flight alone when re-rendered with an identical model", async () => {
    const { rerender } = render(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(4))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    for (let i = 0; i < 3; i++) {
      // Same content, new object identity (what a parent re-render produces).
      rerender(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(4))} {...props} />);
    }
    expect(fake.layoutStops).toBe(0);
    expect(fake.layoutCalls).toHaveLength(1);
  });

  it("still stops and replaces the layout when the content really changes", async () => {
    const { rerender } = render(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(4))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    rerender(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(8))} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(2));
    expect(fake.layoutStops).toBeGreaterThan(0);
  });

  it("maximize stays resize + fit only: no layout", async () => {
    const model = buildSubgraphModel(fixtureSubgraph(4));
    const { rerender } = render(<ConnectionGraph model={model} {...props} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    rerender(<ConnectionGraph model={model} {...props} maximized />);
    await waitFor(() => expect(fake.instances[0]!.fit).toHaveBeenCalledTimes(1));
    expect(fake.layoutCalls).toHaveLength(1);
  });
});
