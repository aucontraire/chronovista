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

import { useEffect, useRef, useState } from "react";
import type cytoscape from "cytoscape";
import type { ElementDefinition, Core, Layouts, StylesheetJson } from "cytoscape";
import type { FcoseLayoutOptions } from "cytoscape-fcose";

import { GRAPH_STRUCTURAL_COLORS, entityTypeGraphColor } from "../../constants/entityTypes";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { MAX_RENDERED_NODES, collapseParallelOverlays } from "./connectionModel";
import type { ConnectionModel } from "./connectionModel";

const PALETTE = ["#0369a1", "#0f766e", "#b45309", "#be123c", "#1d4ed8", "#6d28d9", "#15803d"];

/** Stable colour per relationship type (a secondary channel; labels carry the meaning). */
export function edgeColor(edgeType: string): string {
  let hash = 0;
  for (const ch of edgeType) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length] ?? "#475569";
}

export function toCytoscapeElements(model: ConnectionModel): ElementDefinition[] {
  const nodes: ElementDefinition[] = model.nodes.map((n) => ({
    group: "nodes",
    data: {
      id: n.id,
      label: n.name,
      size: n.size,
      role: n.role,
      ...(n.entityId ? { entityId: n.entityId } : {}),
      // Entities and endpoints are filled by entity type; categories/bridges keep their own look.
      ...(n.role === "entity" || n.role.startsWith("endpoint")
        ? { fill: entityTypeGraphColor(n.label) }
        : {}),
    },
    classes: n.role,
  }));
  // Connect collapses parallel co-occurrence edges; Explore edges (which carry a backend layer)
  // are never merged, so each layer stays an independent edge (FR-023).
  const edgeModels = [
    ...collapseParallelOverlays(model.edges.filter((e) => e.layer === undefined)),
    ...model.edges.filter((e) => e.layer !== undefined),
  ];
  const edges: ElementDefinition[] = edgeModels.map((e) => ({
    group: "edges",
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.relationship,
      color: e.overlay ? "#475569" : edgeColor(e.edgeType),
      ...(e.layer !== undefined ? { layer: e.layer } : {}),
    },
    // Layered (Explore) edges are styled by `layer-*` only; Connect edges by their kind.
    classes: [
      e.overlay ? "overlay" : "kb",
      e.layer !== undefined ? `layer-${e.layer}` : e.kind,
    ].join(" "),
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
      "border-width": 1.5,
      "border-color": "#1e293b",
      shape: "ellipse",
    },
  },
  { selector: "node[fill]", style: { "background-color": "data(fill)" } },
  { selector: "node.category", style: { shape: "diamond", "background-color": GRAPH_STRUCTURAL_COLORS.category } },
  {
    selector: "node.bridge",
    // Dashed outline: "a reference value, not an entity in your library".
    style: {
      shape: "round-rectangle",
      "background-color": GRAPH_STRUCTURAL_COLORS.bridge,
      "border-style": "dashed",
    },
  },
  {
    selector: "node.endpoint-a, node.endpoint-b",
    style: { "border-width": 4, "font-weight": "bold", "font-size": 12 },
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
  // Explore trust layers (FR-006): shape of the line, weight and opacity differ, not just colour.
  { selector: "edge.layer-verified", style: { "line-style": "solid", width: 3.5, opacity: 1 } },
  {
    selector: "edge.layer-category",
    style: { "line-style": "dashed", "line-dash-pattern": [6, 4], width: 1.5, opacity: 0.7 },
  },
  {
    selector: "edge.layer-co_occurrence",
    style: {
      "line-style": "dotted",
      "line-color": "#c026d3",
      "target-arrow-color": "#c026d3",
      width: 1,
      opacity: 0.45,
    },
  },
  // Selection/hover halo: neutral and thin, so it marks without washing the graph in one colour.
  { selector: ".filtered", style: { display: "none" } },
  {
    selector: ":focus, :selected, :active",
    style: { "overlay-color": "#334155", "overlay-opacity": 0.1, "overlay-padding": 3 },
  },
];

interface ConnectionGraphProps {
  model: ConnectionModel;
  /** DOM id of the table, referenced by the canvas for assistive tech. */
  tableId: string;
  summary: string;
  /**
   * How a model change is applied to the long-lived instance.
   *  - "replace" (default, Connect): the previous elements are swapped for the new model and the
   *    whole layout is recomputed and fitted — the same visual result as before the refactor.
   *  - "incremental" (Explore, FR-020): elements already present keep their positions, only new
   *    elements are added and laid out, and pan/zoom are untouched.
   */
  updateMode?: "replace" | "incremental";
  /** Explore: double-clicking a node that has an entity id asks to expand it in place. */
  onNodeExpand?: (entityId: string) => void;
  /** Explore maximize (FR-017): fills its (fixed) parent instead of a fixed height. */
  maximized?: boolean;
  /** Bumping this re-fits the view (the "Fit to view" control). */
  fitToken?: number;
  /** Above this many nodes the graph is hidden (default suits Connect; Explore passes its ceiling). */
  maxRenderedNodes?: number;
  /**
   * Ids of nodes/edges hidden by the focus filters. They are hidden in place (display:none), never
   * removed, so positions survive. The table is given the same set (see `withoutHidden`).
   */
  hiddenIds?: ReadonlySet<string>;
}

let fcoseRegistered = false;

// Co-occurrence overlay edges are drawn but excluded from layout, so they do not
// pull the two poles together and imply a knowledge-base proximity.
function layoutOptionsFor(
  animate: boolean,
  initial: boolean,
  pinned: { nodeId: string; position: { x: number; y: number } }[],
): cytoscape.LayoutOptions {
  const options: FcoseLayoutOptions = {
    name: "fcose",
    // Reduced motion: settle immediately, no animation (FR-027).
    animate,
    animationDuration: 400,
    // Only a from-scratch layout may randomize; an incremental one must not move what is placed.
    randomize: initial,
    fit: initial,
    padding: 40,
    // Keep endpoints (and any pair with no KB edges between them) clearly apart.
    nodeRepulsion: () => 12000,
    idealEdgeLength: () => 140,
    nodeSeparation: 120,
    numIter: 3000,
    ...(initial ? {} : { fixedNodeConstraint: pinned }),
  };
  // @types/cytoscape-fcose is incompatible with exactOptionalPropertyTypes.
  return options as unknown as cytoscape.LayoutOptions;
}

export function ConnectionGraph({
  model,
  tableId,
  summary,
  updateMode = "replace",
  onNodeExpand,
  maximized = false,
  fitToken = 0,
  maxRenderedNodes = MAX_RENDERED_NODES,
  hiddenIds,
}: ConnectionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const layoutRef = useRef<Layouts | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const reducedMotionRef = useRef(reducedMotion);
  reducedMotionRef.current = reducedMotion;
  // Read through a ref so a new callback identity never rebuilds the instance or its handlers.
  const onNodeExpandRef = useRef(onNodeExpand);
  onNodeExpandRef.current = onNodeExpand;
  const [cyReady, setCyReady] = useState(false);
  // Mouse-only affordance (the table carries every full name for assistive tech).
  const [hoverName, setHoverName] = useState<{ name: string; x: number; y: number } | null>(null);
  const tooLarge = model.nodes.length > maxRenderedNodes;

  // Create the single long-lived instance. It is destroyed only on unmount (or when the graph
  // is hidden as too large), never on a data change.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || tooLarge) return;
    let cancelled = false;
    let observer: ResizeObserver | undefined;
    let frame = 0;

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
      const cy = cytoscape({
        container,
        elements: [],
        style: STYLE,
        // The page, not the canvas, owns keyboard focus; avoid canvas-level wheel hijack.
        userPanningEnabled: true,
        userZoomingEnabled: true,
        wheelSensitivity: 0.2,
      });
      cyRef.current = cy;
      cy.on("mouseover", "node", (evt) => {
        const rect = container.getBoundingClientRect();
        const pos = evt.target.renderedPosition() as { x: number; y: number };
        setHoverName({
          name: String(evt.target.data("label")),
          x: rect.left + pos.x,
          y: rect.top + pos.y,
        });
      });
      cy.on("mouseout", "node", () => setHoverName(null));
      // A pan/zoom/drag moves nodes under a stale tooltip.
      cy.on("pan zoom drag", () => setHoverName(null));
      cy.on("dbltap", "node", (evt) => {
        const entityId: unknown = evt.target.data("entityId");
        if (typeof entityId === "string") onNodeExpandRef.current?.(entityId);
      });
      // The canvas caches its pixel size, so a CSS-only resize (maximize, sidebar) leaves it
      // stale. Resize only; never re-run the layout here (FR-020).
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => {
          cancelAnimationFrame(frame);
          frame = requestAnimationFrame(() => cy.resize());
        });
        observer.observe(container);
      }
      setCyReady(true);
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      layoutRef.current?.stop();
      layoutRef.current = null;
      cyRef.current?.destroy();
      cyRef.current = null;
      setHoverName(null);
      setCyReady(false);
    };
  }, [tooLarge]);

  // Maximize/exit and "Fit to view": the canvas caches its pixel size, so resize explicitly (the
  // ResizeObserver also fires, but a fit before it would use the stale size), then fit. The same
  // instance is reused; nothing is rebuilt. Skips the mount run (the first layout fits itself).
  const sizeKey = `${String(maximized)}|${fitToken}`;
  const lastSizeKey = useRef(sizeKey);
  useEffect(() => {
    if (lastSizeKey.current === sizeKey) return;
    lastSizeKey.current = sizeKey;
    const frame = requestAnimationFrame(() => {
      const cy = cyRef.current;
      if (!cy) return;
      cy.resize();
      cy.fit(undefined, 40);
    });
    return () => cancelAnimationFrame(frame);
  }, [sizeKey]);

  // Apply the model to the existing instance.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !cyReady) return;
    const next = toCytoscapeElements(model);
    const nextIds = new Set(next.map((e) => String(e.data["id"])));
    layoutRef.current?.stop();

    const incremental = updateMode === "incremental" && cy.elements().length > 0;
    const existingIds = new Set<string>();
    if (incremental) {
      cy.elements().forEach((el) => {
        if (nextIds.has(el.id())) existingIds.add(el.id());
      });
      cy.elements().filter((el) => !nextIds.has(el.id())).remove();
    } else {
      cy.elements().remove();
    }

    const added = next.filter((e) => !existingIds.has(String(e.data["id"])));
    if (added.length === 0) return;
    cy.add(added);

    const hasKbEdge = cy.edges().not(".overlay").length > 0;
    const layoutEles = hasKbEdge ? cy.elements().not(".overlay") : cy.elements();
    const pinned = cy
      .nodes()
      .toArray()
      .filter((n) => existingIds.has(n.id()))
      .map((n) => ({ nodeId: n.id(), position: { ...n.position() } }));
    const layout = layoutEles.layout(
      layoutOptionsFor(!reducedMotionRef.current, !incremental, pinned),
    );
    layoutRef.current = layout;
    layout.run();
  }, [model, cyReady, updateMode]);

  // Focus filters: toggle a class, never add/remove, so the arranged layout is untouched.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !cyReady) return;
    cy.elements().forEach((el) => {
      if (hiddenIds?.has(el.id())) el.addClass("filtered");
      else el.removeClass("filtered");
    });
  }, [hiddenIds, model, cyReady]);

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
    <>
      <div
        ref={containerRef}
        role="img"
        tabIndex={0}
        aria-label={summary}
        aria-describedby={tableId}
        data-testid="connection-graph"
        className={`w-full border border-slate-200 bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 ${
          maximized ? "h-full rounded-none" : "h-[28rem] rounded-lg"
        }`}
      />
      {hoverName && (
        <div
          aria-hidden="true"
          data-testid="node-hover-name"
          style={{ left: hoverName.x, top: hoverName.y }}
          className="pointer-events-none fixed z-[60] max-w-xs -translate-x-1/2 -translate-y-full rounded bg-slate-900 px-2 py-1 text-xs text-white shadow"
        >
          {hoverName.name}
        </div>
      )}
    </>
  );
}
