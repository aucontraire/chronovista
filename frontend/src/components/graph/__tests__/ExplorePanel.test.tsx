/**
 * ExplorePanel — Explore renders a neighborhood subgraph, not chains (Feature 115, US1).
 * The Cytoscape canvas is stubbed; the stub records the model it is given and the panel's
 * table is asserted by role.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import type { ConnectionModel } from "../connectionModel";
import { toCytoscapeElements } from "../ConnectionGraph";
import { ExplorePanel } from "../ExplorePanel";
import { fixtureSubgraph } from "./fixtures";

const hookMock = vi.fn();
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => hookMock(...args),
  useExpansions: () => ({ results: [], pending: 0, failed: 0 }),
}));

const graphProps: { model: ConnectionModel; updateMode?: string }[] = [];
vi.mock("../ConnectionGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../ConnectionGraph")>()),
  ConnectionGraph: (props: { model: ConnectionModel; updateMode?: string }) => {
    graphProps.push(props);
    return <div data-testid="connection-graph" />;
  },
}));

function result(overrides: Record<string, unknown> = {}) {
  return { subgraph: undefined, isLoading: false, failure: null, refetch: vi.fn(), ...overrides };
}

describe("ExplorePanel", () => {
  beforeEach(() => {
    hookMock.mockReset();
    graphProps.length = 0;
  });

  it("renders a subgraph of >=10 nodes across >=2 trust layers, carrying each backend layer", () => {
    hookMock.mockReturnValue(result({ subgraph: fixtureSubgraph(12) }));
    render(<ExplorePanel seeds={["a", "b"]} />);

    const props = graphProps.at(-1);
    expect(props?.updateMode).toBe("incremental");
    const elements = toCytoscapeElements(props!.model);
    const nodes = elements.filter((e) => e.group === "nodes");
    const edges = elements.filter((e) => e.group === "edges");
    expect(nodes.length).toBeGreaterThanOrEqual(10);
    // Cytoscape element ids are the server node_key.
    expect(nodes.map((n) => n.data["id"])).toContain("key-n3");
    const layers = new Set(edges.map((e) => e.data["layer"]));
    expect(layers.size).toBeGreaterThanOrEqual(2);
    for (const e of edges) expect(e.classes).toContain(`layer-${String(e.data["layer"])}`);
    // Seeds get the endpoint roles; the accessible table lists every edge.
    expect(nodes.find((n) => n.data["id"] === "key-a")?.classes).toBe("endpoint-a");
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(1 + 12);
  });

  it("shows 'showing N of M' only when more neighbors exist than are rendered", () => {
    hookMock.mockReturnValue(result({ subgraph: fixtureSubgraph(12, 340) }));
    const { rerender } = render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("explore-count")).toHaveTextContent("Showing 14 of 340 nodes");

    hookMock.mockReturnValue(result({ subgraph: fixtureSubgraph(12) }));
    rerender(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("explore-count")).toHaveTextContent("Showing all 14 nodes");
  });

  it("shows a loading state", () => {
    hookMock.mockReturnValue(result({ isLoading: true }));
    render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("explore-loading")).toBeInTheDocument();
  });

  it("shows a non-blocking error that keeps the current view", () => {
    hookMock.mockReturnValue(
      result({ subgraph: fixtureSubgraph(10), failure: { kind: "error" } }),
    );
    render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("explore-error")).toBeInTheDocument();
    expect(screen.getByTestId("connection-graph")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("distinguishes graph-unavailable from a generic error", () => {
    hookMock.mockReturnValue(result({ failure: { kind: "unavailable" } }));
    render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("explore-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("explore-error")).not.toBeInTheDocument();
  });

  it("seeds the hook with the given entities and the default layers", () => {
    hookMock.mockReturnValue(result());
    render(<ExplorePanel seeds={["a", "b"]} maxCategorySize={500} />);
    expect(hookMock).toHaveBeenCalledWith(
      ["a", "b"],
      expect.objectContaining({ edgeTypes: ["verified", "category"], maxCategorySize: 500 }),
    );
  });
});
