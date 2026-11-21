/**
 * Coming back to the same graph restores its arrangement instead of re-laying it out.
 * Real ConnectionGraph over the fake Cytoscape; the unmount/remount is a real React unmount.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

import { ConnectionGraph } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { clearSavedLayouts } from "../graphLayoutCache";
import { fake } from "./fakeCytoscape";
import { fixtureSubgraph } from "./fixtures";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

const fcoseRuns = () => fake.layoutCalls.filter((c) => c["name"] === "fcose");
const presetRuns = () => fake.layoutCalls.filter((c) => c["name"] === "preset");

describe("graph arrangement survives unmount/remount", () => {
  beforeEach(() => {
    fake.reset();
    clearSavedLayouts();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  const base = { tableId: "t", summary: "s", updateMode: "incremental" as const };
  const model4 = () => buildSubgraphModel(fixtureSubgraph(4));

  /** Lay a graph out, "arrange" it, let it settle, then leave the page. */
  async function visitAndLeave(
    layoutKey: string | undefined,
    opts: { maximized?: boolean; neighbors?: number } = {},
  ) {
    const model = opts.neighbors ? buildSubgraphModel(fixtureSubgraph(opts.neighbors)) : model4();
    const view = render(<ConnectionGraph model={model} {...base} {...(layoutKey ? { layoutKey } : {})} {...(opts.maximized ? { maximized: true } : {})} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const cy = fake.instances.at(-1)!;
    cy.setPosition("key-a", { x: 11, y: 22 });
    cy.setPosition("key-n0", { x: -33, y: 44 });
    cy.setViewport({ pan: { x: 7, y: 8 }, zoom: 0.75 });
    cy.emit("layoutstop");
    view.unmount();
  }

  it("first load, nothing remembered: a normal randomized fcose layout", async () => {
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(fake.layoutCalls[0]).toMatchObject({ name: "fcose", randomize: true, fit: true });
  });

  it("same graph back: preset with the saved positions and viewport, and no fcose run", async () => {
    await visitAndLeave("explore|p");
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(fcoseRuns()).toHaveLength(0);
    const preset = presetRuns()[0]!;
    const positions = preset["positions"] as Record<string, { x: number; y: number }>;
    expect(positions["key-a"]).toEqual({ x: 11, y: 22 });
    expect(positions["key-n0"]).toEqual({ x: -33, y: 44 });
    expect(preset).toMatchObject({ animate: false, fit: false, pan: { x: 7, y: 8 }, zoom: 0.75 });
  });

  it("a different graph key never restores another graph's arrangement", async () => {
    await visitAndLeave("explore|p");
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|other" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(presetRuns()).toHaveLength(0);
    expect(fake.layoutCalls[0]).toMatchObject({ name: "fcose", randomize: true });
  });

  it("a node the memory does not cover falls back to a real layout", async () => {
    await visitAndLeave("explore|p");
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(7))} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(presetRuns()).toHaveLength(0);
    expect(fake.layoutCalls[0]).toMatchObject({ name: "fcose", randomize: true });
  });

  it("without a layoutKey (Connect) nothing is remembered or restored", async () => {
    await visitAndLeave(undefined);
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(fake.layoutCalls[0]).toMatchObject({ name: "fcose", randomize: true });
  });

  it("leaving mid-layout remembers nothing (those positions are intermediate)", async () => {
    const view = render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    fake.instances.at(-1)!.emit("layoutstart");
    view.unmount();
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    expect(fake.layoutCalls[0]).toMatchObject({ name: "fcose" });
  });

  it("left while maximized: positions restored, view re-fitted (a maximized viewport is meaningless)", async () => {
    await visitAndLeave("explore|p", { maximized: true });
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const preset = presetRuns()[0]!;
    expect(preset).toMatchObject({ fit: true });
    expect(preset).not.toHaveProperty("pan");
  });

  it("rearrangement after the last layout is remembered too (saved on unmount)", async () => {
    const view = render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const cy = fake.instances.at(-1)!;
    cy.emit("layoutstop"); // settled with the default positions…
    cy.setPosition("key-a", { x: 500, y: 600 }); // …then the user drags a node and pans
    cy.setViewport({ pan: { x: 1, y: 2 }, zoom: 2 });
    view.unmount();
    fake.layoutCalls.length = 0;
    render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    const preset = presetRuns()[0]!;
    expect((preset["positions"] as Record<string, unknown>)["key-a"]).toEqual({ x: 500, y: 600 });
    expect(preset).toMatchObject({ pan: { x: 1, y: 2 }, zoom: 2 });
  });

  it("after a restore, expansion is still incremental: existing nodes pinned, only new ones laid out", async () => {
    // The memory covers the bigger graph too, so only the incremental path (not a restore) may handle growth.
    await visitAndLeave("explore|p", { neighbors: 8 });
    fake.layoutCalls.length = 0;
    const { rerender } = render(<ConnectionGraph model={model4()} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(presetRuns()).toHaveLength(1));
    rerender(<ConnectionGraph model={buildSubgraphModel(fixtureSubgraph(8))} {...base} layoutKey="explore|p" />);
    await waitFor(() => expect(fcoseRuns()).toHaveLength(1));
    expect(fcoseRuns()[0]).toMatchObject({ randomize: false, fit: false });
    expect((fcoseRuns()[0]!["fixedNodeConstraint"] as unknown[]).length).toBe(model4().nodes.length);
  });
});
