/**
 * Connect <-> Explore mode switch (Feature 115, FR-010 / SC-006): the toggle itself, and the
 * page-level guarantees that switching preserves the selected entities and leaves Connect's
 * answer unchanged.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { ConnectionExplorerPage } from "../../../pages/ConnectionExplorerPage";
import { GraphModeToggle } from "../GraphModeToggle";
import { A_ID, B_ID, fixtureConnection, fixtureSubgraph } from "./fixtures";

const connectionMock = vi.fn();
const neighborhoodMock = vi.fn();
vi.mock("../../../hooks/useConnection", () => ({
  useConnection: (...args: unknown[]) => connectionMock(...args),
  useGraphHealth: () => ({
    health: { status: "complete", servable: true, loaded_at: null, declared_layers: [] },
    isLoading: false,
  }),
  useGraphPresence: () => ({ present: new Set<string>(), isLoading: false }),
}));
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => neighborhoodMock(...args),
  useExpansions: () => ({ results: [], pending: 0, failed: 0 }),
}));
vi.mock("../../../hooks/useConnectionEvidence", () => ({
  EVIDENCE_PAGE_SIZE: 12,
  useConnectionEvidence: () => ({ items: [], first: undefined, isLoading: true, isError: false, error: null }),
}));
vi.mock("../../../hooks/useEntitySearch", () => ({
  useEntitySearch: () => ({ entities: [], isLoading: false, isFetched: false, isError: false, isBelowMinChars: true }),
}));
vi.mock("../../../hooks/useEntityDetail", () => ({
  useEntityDetail: () => ({ entityDetail: undefined, aliasNames: [], isLoading: false }),
}));
vi.mock("../ConnectionGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../ConnectionGraph")>()),
  ConnectionGraph: () => <div data-testid="connection-graph" />,
}));

function LocationProbe() {
  const loc = useLocation();
  return <output data-testid="loc">{loc.search}</output>;
}

describe("GraphModeToggle", () => {
  it("exposes both modes as radios and reports a change", () => {
    const onChange = vi.fn();
    render(<GraphModeToggle mode="connect" onChange={onChange} />);
    expect(screen.getByRole("radio", { name: "Connect" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Explore" }));
    expect(onChange).toHaveBeenCalledWith("explore");
  });
});

describe("mode switching on the Connection Explorer page", () => {
  beforeEach(() => {
    connectionMock.mockReset();
    neighborhoodMock.mockReset();
    connectionMock.mockReturnValue({
      connection: fixtureConnection(),
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
    neighborhoodMock.mockReturnValue({
      subgraph: fixtureSubgraph(10),
      isLoading: false,
      failure: null,
      refetch: vi.fn(),
    });
  });

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={[`/connections?a=${A_ID}&b=${B_ID}`]}>
        <ConnectionExplorerPage />
        <LocationProbe />
      </MemoryRouter>,
    );
  }

  it("keeps the selected entities, seeds Explore with the pair, and restores Connect unchanged", () => {
    renderPage();
    const connectTable = screen.getByRole("table").innerHTML;
    expect(screen.queryByTestId("explore-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Explore" }));
    expect(screen.getByTestId("explore-panel")).toBeInTheDocument();
    const loc = screen.getByTestId("loc").textContent ?? "";
    expect(loc).toContain(`a=${A_ID}`);
    expect(loc).toContain(`b=${B_ID}`);
    expect(neighborhoodMock).toHaveBeenLastCalledWith(
      [A_ID, B_ID],
      expect.objectContaining({ enabled: true }),
    );
    // Connect's result is not shown while exploring, and its request is skipped.
    expect(connectionMock).toHaveBeenLastCalledWith(
      A_ID,
      B_ID,
      expect.objectContaining({ enabled: false }),
    );

    fireEvent.click(screen.getByRole("radio", { name: "Connect" }));
    expect(screen.queryByTestId("explore-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("table").innerHTML).toBe(connectTable);
    expect(screen.getByTestId("loc").textContent).toContain(`a=${A_ID}`);
  });
});
