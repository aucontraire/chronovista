/** Entity nodes are filled by entity type; categories/bridges are not (Feature 115 polish). */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ENTITY_TYPE_GRAPH_COLORS,
  ENTITY_TYPE_GRAPH_FALLBACK_COLOR,
  GRAPH_STRUCTURAL_COLORS,
  entityTypeGraphColor,
} from "../../../constants/entityTypes";
import { toCytoscapeElements } from "../ConnectionGraph";
import { buildSubgraphModel } from "../connectionModel";
import { NodeTypeLegend } from "../NodeTypeLegend";
import { fixtureSubgraph } from "./fixtures";

function subgraphWithTypes() {
  const sub = fixtureSubgraph(3);
  const types = ["organization", "place", "technical_term"];
  sub.nodes.slice(2).forEach((n, i) => (n.node.label = types[i] ?? ""));
  sub.nodes.push({
    node_key: "key-cat",
    node: { entity_id: null, name: "Cat", label: "Category", is_bridge: true, kb_degree: null, specificity: 3 },
  });
  return sub;
}

describe("entity-type node colours", () => {
  it("fills entities and endpoints by type; categories get no type fill", () => {
    const nodes = toCytoscapeElements(buildSubgraphModel(subgraphWithTypes())).filter((e) => e.group === "nodes");
    const fill = (id: string) => nodes.find((n) => n.data["id"] === id)?.data["fill"];
    expect(fill("key-n0")).toBe(ENTITY_TYPE_GRAPH_COLORS["organization"]);
    expect(fill("key-n1")).toBe(ENTITY_TYPE_GRAPH_COLORS["place"]);
    // Folded types and endpoints (label "Person", any case) resolve too.
    expect(fill("key-n2")).toBe(entityTypeGraphColor("other"));
    expect(fill("key-a")).toBe(ENTITY_TYPE_GRAPH_COLORS["person"]);
    expect(fill("key-cat")).toBeUndefined();
  });

  it("uses distinct colours for the eight coloured types", () => {
    expect(new Set(Object.values(ENTITY_TYPE_GRAPH_COLORS)).size).toBe(8);
  });

  it("legend names each type present, in text", () => {
    render(<NodeTypeLegend model={buildSubgraphModel(subgraphWithTypes())} />);
    const legend = screen.getByRole("list", { name: /colour by entity type/i });
    expect(legend).toHaveTextContent("Organization");
    expect(legend).toHaveTextContent("Place");
    expect(legend).toHaveTextContent("Person");
    expect(legend).not.toHaveTextContent("Category");
  });

  it("keeps the three neutral kinds distinct from each other and from every typed hue", () => {
    const neutrals = [
      ENTITY_TYPE_GRAPH_FALLBACK_COLOR,
      GRAPH_STRUCTURAL_COLORS.category,
      GRAPH_STRUCTURAL_COLORS.bridge,
    ];
    expect(new Set(neutrals).size).toBe(3);
    for (const n of neutrals) expect(Object.values(ENTITY_TYPE_GRAPH_COLORS)).not.toContain(n);
  });

  it("legend explains the structural kinds, only when they are on screen", () => {
    const withBridge = subgraphWithTypes();
    withBridge.nodes.push({
      node_key: "key-br",
      node: { entity_id: null, name: "Office", label: "WikidataItem", is_bridge: true, kb_degree: null, specificity: null },
    });
    const { unmount } = render(<NodeTypeLegend model={buildSubgraphModel(withBridge)} />);
    const kinds = screen.getByRole("list", { name: /other node kinds/i });
    expect(kinds).toHaveTextContent("Shared category");
    expect(kinds).toHaveTextContent(/reference value/i);
    unmount();

    render(<NodeTypeLegend model={buildSubgraphModel(fixtureSubgraph(3))} />);
    expect(screen.queryByRole("list", { name: /other node kinds/i })).not.toBeInTheDocument();
  });
});
