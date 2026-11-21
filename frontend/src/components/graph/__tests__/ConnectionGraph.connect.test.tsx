/**
 * FR-026 guard: ConnectionGraph still renders Connect chains correctly after the
 * long-lived-instance refactor (Feature 115). Cytoscape is replaced by a recording fake.
 */

import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildConnectionModel } from "../connectionModel";
import { fixtureConnection, noPathConnection } from "./fixtures";

import { fake as h } from "./fakeCytoscape";
import type { FakeCy } from "./fakeCytoscape";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

import { ConnectionGraph } from "../ConnectionGraph";

describe("ConnectionGraph (Connect no-regression, FR-026)", () => {
  beforeEach(() => {
    h.reset();
    // The global test setup's ResizeObserver stub is not constructible.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("adds Connect's chain nodes and edges with their roles and kinds", async () => {
    const model = buildConnectionModel(fixtureConnection());
    render(<ConnectionGraph model={model} tableId="t" summary="s" />);
    await waitFor(() => expect(h.instances).toHaveLength(1));
    const cy = h.instances[0] as FakeCy;
    await waitFor(() => expect(cy.added.length).toBeGreaterThan(0));

    const nodes = cy.added.filter((e) => e.group === "nodes");
    expect(nodes).toHaveLength(model.nodes.length);
    expect(nodes.map((n) => n.classes).sort()).toEqual(model.nodes.map((n) => n.role).sort());
    const edges = cy.added.filter((e) => e.group === "edges");
    expect(edges.some((e) => e.classes?.includes("shared_category"))).toBe(true);
    expect(edges.some((e) => e.classes?.includes("overlay"))).toBe(true);
  });

  it("runs a full randomized, fitted layout excluding overlay edges", async () => {
    render(<ConnectionGraph model={buildConnectionModel(fixtureConnection())} tableId="t" summary="s" />);
    await waitFor(() => expect(h.layoutCalls).toHaveLength(1));
    expect(h.layoutCalls[0]).toMatchObject({ name: "fcose", randomize: true, fit: true });
  });

  it("applies a new model in place: never destroys the instance, replaces elements, re-lays out", async () => {
    const { rerender } = render(
      <ConnectionGraph model={buildConnectionModel(fixtureConnection())} tableId="t" summary="s" />,
    );
    await waitFor(() => expect(h.layoutCalls).toHaveLength(1));
    const cy = h.instances[0] as FakeCy;

    rerender(<ConnectionGraph model={buildConnectionModel(noPathConnection())} tableId="t" summary="s" />);
    await waitFor(() => expect(h.layoutCalls.length).toBeGreaterThanOrEqual(2));
    expect(h.instances).toHaveLength(1);
    expect(cy.destroy).not.toHaveBeenCalled();
    // Connect semantics preserved: "replace" mode re-randomizes and fits.
    expect(h.layoutCalls[1]).toMatchObject({ randomize: true, fit: true });
  });

  it("destroys the instance only on unmount", async () => {
    const { unmount } = render(
      <ConnectionGraph model={buildConnectionModel(fixtureConnection())} tableId="t" summary="s" />,
    );
    await waitFor(() => expect(h.layoutCalls).toHaveLength(1));
    const cy = h.instances[0] as FakeCy;
    unmount();
    expect(cy.destroy).toHaveBeenCalledTimes(1);
  });

  it("keeps positions in incremental mode: no randomize/fit, existing nodes pinned", async () => {
    const model = buildConnectionModel(fixtureConnection());
    const { rerender } = render(
      <ConnectionGraph model={{ ...model, nodes: model.nodes.slice(0, 2), edges: [] }} tableId="t" summary="s" updateMode="incremental" />,
    );
    await waitFor(() => expect(h.layoutCalls).toHaveLength(1));
    rerender(<ConnectionGraph model={model} tableId="t" summary="s" updateMode="incremental" />);
    await waitFor(() => expect(h.layoutCalls).toHaveLength(2));
    expect(h.layoutCalls[1]).toMatchObject({ randomize: false, fit: false });
    expect((h.layoutCalls[1] as { fixedNodeConstraint: unknown[] }).fixedNodeConstraint).toHaveLength(2);
  });

  it("resizes the canvas (without re-laying out) when the container resizes", async () => {
    let trigger: () => void = () => undefined;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          trigger = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("requestAnimationFrame", (cb: () => void) => {
      cb();
      return 1;
    });
    render(<ConnectionGraph model={buildConnectionModel(fixtureConnection())} tableId="t" summary="s" />);
    await waitFor(() => expect(h.layoutCalls).toHaveLength(1));
    const cy = h.instances[0] as FakeCy;
    const resizesBefore = cy.resize.mock.calls.length;
    trigger();
    expect(cy.resize).toHaveBeenCalledTimes(resizesBefore + 1);
    expect(h.layoutCalls).toHaveLength(1);
  });
});
