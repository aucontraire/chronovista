/**
 * ConnectionGraph — Cytoscape rendering of a connection (Feature 113).
 *
 * Visual channels (FR-025: never colour alone):
 *  - relationship type: line colour AND an on-edge text label
 *  - connection kind: line style — solid (knowledge base), dotted (category),
 *    dashed + curved (co-occurrence overlay, FR-007)
 *  - node role: shape (endpoints = star-like large ellipses with a heavy border,
 *    categories = diamonds sized by the server log-specificity, bridges =
 *    round rectangles)
 *
 * The canvas is a single focusable `role="img"` stop (no key handling, so Tab
 * is never trapped — FR-026); the table is the interactive/accessible view.
 * Cytoscape is imported lazily so it never loads for tests or other pages.
 */

import { useEffect, useRef } from "react";
import type cytoscape from "cytoscape";
import type { ElementDefinition, Core, StylesheetJson } from "cytoscape";
import type { FcoseLayoutOptions } from "cytoscape-fcose";

import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { MAX_RENDERED_NODES, collapseParallelOverlays } from "./connectionModel";
import type { ConnectionModel } from "./connectionModel";

const PALETTE = ["#4338ca", "#0f766e", "#b45309", "#be123c", "#1d4ed8", "#6d28d9", "#15803d"];

/** Stable colour per relationship type (a secondary channel; labels carry the meaning). */
export function edgeColor(edgeType: string): string {
  let hash = 0;
  for (const ch of edgeType) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length] ?? "#475569";
}

export function toCytoscapeElements(model: ConnectionModel): ElementDefinition[] {
  const nodes: ElementDefinition[] = model.nodes.map((n) => ({
    group: "nodes",
    data: { id: n.id, label: n.name, size: n.size, role: n.role },
    classes: n.role,
  }));
  const edges: ElementDefinition[] = collapseParallelOverlays(model.edges).map((e) => ({
    group: "edges",
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.relationship,
      color: e.overlay ? "#475569" : edgeColor(e.edgeType),
    },
    classes: [e.overlay ? "overlay" : "kb", e.kind].join(" "),
  }));
  return [...nodes, ...edges];
}

const STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      width: "data(size)",
      height: "data(size)",
      "font-size": 11,
      "text-wrap": "ellipsis",
      "text-max-width": "90px",
      "text-valign": "bottom",
      "text-margin-y": 4,
      "background-color": "#e2e8f0",
      "border-width": 1,
      "border-color": "#475569",
      shape: "ellipse",
    },
  },
  { selector: "node.category", style: { shape: "diamond", "background-color": "#fef3c7" } },
  { selector: "node.bridge", style: { shape: "round-rectangle", "background-color": "#f1f5f9" } },
  {
    selector: "node.endpoint-a, node.endpoint-b",
    style: { "border-width": 4, "font-weight": "bold", "background-color": "#c7d2fe", "font-size": 12 },
  },
  { selector: "node.endpoint-b", style: { shape: "round-hexagon" } },
  {
    selector: "edge",
    style: {
      label: "data(label)",
      "font-size": 9,
      "line-color": "data(color)",
      "target-arrow-color": "data(color)",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      width: 2,
      "line-style": "solid",
      "text-rotation": "autorotate",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "text-background-padding": "2px",
    },
  },
  { selector: "edge.shared_category", style: { "line-style": "dotted" } },
  {
    selector: "edge.overlay",
    style: {
      "line-style": "dashed",
      "line-dash-pattern": [8, 5],
      "target-arrow-shape": "none",
      "curve-style": "unbundled-bezier",
      "control-point-distances": [40],
      "control-point-weights": [0.5],
      width: 2.5,
    },
  },
  { selector: ":focus, :selected", style: { "overlay-color": "#4338ca", "overlay-opacity": 0.2 } },
];

interface ConnectionGraphProps {
  model: ConnectionModel;
  /** DOM id of the table, referenced by the canvas for assistive tech. */
  tableId: string;
  summary: string;
}

let fcoseRegistered = false;

export function ConnectionGraph({ model, tableId, summary }: ConnectionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const tooLarge = model.nodes.length > MAX_RENDERED_NODES;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || tooLarge) return;
    let cy: Core | undefined;
    let cancelled = false;

    void (async () => {
      const [{ default: cytoscape }, { default: fcose }] = await Promise.all([
        import("cytoscape"),
        import("cytoscape-fcose"),
      ]);
      if (cancelled) return;
      if (!fcoseRegistered) {
        cytoscape.use(fcose);
        fcoseRegistered = true;
      }
      cy = cytoscape({
        container,
        elements: toCytoscapeElements(model),
        style: STYLE,
        // The page, not the canvas, owns keyboard focus; avoid canvas-level wheel hijack.
        userPanningEnabled: true,
        userZoomingEnabled: true,
        wheelSensitivity: 0.2,
      });
      // Co-occurrence overlay edges are drawn but excluded from layout, so they do not
      // pull the two poles together and imply a knowledge-base proximity.
      const layoutOptions: FcoseLayoutOptions = {
        name: "fcose",
        // Reduced motion: settle immediately, no animation (FR-027).
        animate: !reducedMotion,
        animationDuration: 400,
        randomize: true,
        fit: true,
        padding: 40,
        // Keep endpoints (and any pair with no KB edges between them) clearly apart.
        nodeRepulsion: () => 12000,
        idealEdgeLength: () => 140,
        nodeSeparation: 120,
        numIter: 3000,
      };
      // With no non-overlay edge the layout would see two unconnected nodes and stack them;
      // include overlays then (nothing KB-related is implied: there is no KB edge to mislead).
      const hasKbEdge = cy.edges().not(".overlay").length > 0;
      const layoutEles = hasKbEdge ? cy.elements().not(".overlay") : cy.elements();
      layoutEles.layout(
          // @types/cytoscape-fcose is incompatible with exactOptionalPropertyTypes.
          layoutOptions as unknown as cytoscape.LayoutOptions,
        ).run();
    })();

    return () => {
      cancelled = true;
      cy?.destroy();
    };
  }, [model, reducedMotion, tooLarge]);

  if (tooLarge) {
    return (
      <p
        role="status"
        className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        data-testid="graph-too-large"
      >
        Large result ({model.nodes.length} nodes) — the graph is hidden to stay readable.
        Tighten the controls (lower the reach or the category size) or use the table below.
      </p>
    );
  }

  return (
    <div
      ref={containerRef}
      role="img"
      tabIndex={0}
      aria-label={summary}
      aria-describedby={tableId}
      data-testid="connection-graph"
      className="h-[28rem] w-full rounded-lg border border-slate-200 bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
    />
  );
}
