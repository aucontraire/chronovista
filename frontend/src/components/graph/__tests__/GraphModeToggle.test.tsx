/**
 * Connect <-> Explore mode switch (Feature 115, FR-010 / SC-006): the toggle itself, and the
 * page-level guarantees that switching preserves the selected entities and leaves Connect's
 * answer unchanged.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
vi.mock("../../../hooks/usePairPassages", () => ({
  EVIDENCE_PAGE_SIZE: 12,
  usePairPassages: () => ({ items: [], first: undefined, isLoading: true, isError: false, error: null }),
}));
vi.mock("../../../hooks/useEntitySearch", () => ({
  useEntitySearch: () => ({ entities: [], isLoading: false, isFetched: false, isError: false, isBelowMinChars: true }),
}));
const detailMock = vi.fn();
vi.mock("../../../hooks/useEntityDetail", () => ({
  useEntityDetail: (id: string | null) => detailMock(id),
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
    detailMock.mockReset();
    detailMock.mockImplementation((id: string | null) => ({
      entityDetail: id
        ? {
            canonical_name: `Name of ${id.slice(0, 4)}`,
            enrichment:
              id === B_ID ? { identifiers: [{ url: "https://example.test/record-b" }] } : undefined,
          }
        : undefined,
      aliasNames: [],
      isLoading: false,
    }));
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

  it("keeps the transcript-evidence panel in Explore when both entities are chosen", () => {
    renderPage();
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Explore" }));
    expect(screen.getByTestId("explore-panel")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
  });

  it("hides the evidence panel in Explore when only one entity is chosen (no pair)", () => {
    render(
      <MemoryRouter initialEntries={[`/connections?a=${A_ID}&mode=explore`]}>
        <ConnectionExplorerPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("explore-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("evidence-panel")).not.toBeInTheDocument();
  });

  it("shows each selected entity's links in Explore when both are chosen", () => {
    render(
      <MemoryRouter initialEntries={[`/connections?a=${A_ID}&b=${B_ID}&mode=explore`]}>
        <ConnectionExplorerPage />
      </MemoryRouter>,
    );
    const cards = screen.getByRole("list", { name: "Selected entities" });
    // B has an enriched external record; A falls back to a Wikidata lookup.
    expect(within(cards).getByRole("link", { name: "External record" })).toHaveAttribute(
      "href",
      "https://example.test/record-b",
    );
    expect(within(cards).getByRole("link", { name: "Look up on Wikidata" })).toBeInTheDocument();
    const pages = within(cards).getAllByRole("link", { name: "Entity page" });
    expect(pages.map((l) => l.getAttribute("href"))).toEqual([`/entities/${A_ID}`, `/entities/${B_ID}`]);
  });

  it("shows no entity links in Explore with a single entity", () => {
    render(
      <MemoryRouter initialEntries={[`/connections?a=${A_ID}&mode=explore`]}>
        <ConnectionExplorerPage />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("list", { name: "Selected entities" })).not.toBeInTheDocument();
  });

  it("also shows them for a knowledge-base-connected Connect result, but not beside the no-path cards", () => {
    const connected = fixtureConnection();
    connected.chains = [
      {
        kind: "asserted",
        truncated: false,
        score: null,
        steps: [
          { edge_type: "RELATED_TO", kind: "asserted", to_node: connected.entity_b, specificity: null, forward: true },
        ],
      },
    ];
    connectionMock.mockReturnValue({ connection: connected, isLoading: false, failure: null, refetch: vi.fn() });
    const { unmount } = renderPage();
    expect(screen.getByRole("list", { name: "Selected entities" })).toBeInTheDocument();
    unmount();

    // The default fixture has only a shared-category link (no KB path): the coverage cards
    // already carry the links, so the selected-entity cards are not added on top.
    connectionMock.mockReturnValue({ connection: fixtureConnection(), isLoading: false, failure: null, refetch: vi.fn() });
    renderPage();
    expect(screen.queryByRole("list", { name: "Selected entities" })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Knowledge-base coverage" })).toBeInTheDocument();
  });

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
