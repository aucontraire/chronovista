/**
 * Discoverability of the Connection Explorer (Feature 115, US4: FR-015, FR-016, SC-008):
 * a "Connections" entry in the Entities nav group, and the explorer's unseeded default state
 * when it is reached from the nav with nothing selected.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ConnectionExplorerPage } from "../../../pages/ConnectionExplorerPage";
import { Sidebar } from "../Sidebar";

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
vi.mock("../../../hooks/useEntitySearch", () => ({
  useEntitySearch: () => ({ entities: [], isLoading: false, isFetched: false, isError: false, isBelowMinChars: true }),
}));
vi.mock("../../../hooks/useEntityDetail", () => ({
  useEntityDetail: () => ({ entityDetail: undefined, aliasNames: [], isLoading: false }),
}));

beforeEach(() => {
  localStorage.clear();
  connectionMock.mockReset();
  neighborhoodMock.mockReset();
  connectionMock.mockReturnValue({ connection: undefined, isLoading: false, failure: null, refetch: vi.fn() });
  neighborhoodMock.mockReturnValue({ subgraph: undefined, isLoading: false, failure: null, refetch: vi.fn() });
});

describe("primary navigation", () => {
  it("lists Connections inside the Entities group, linking to the explorer with no params", () => {
    render(
      <MemoryRouter initialEntries={["/videos"]}>
        <Sidebar />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    const link = within(nav).getByRole("link", { name: /connections/i });
    expect(link).toHaveAttribute("href", "/connections");
    // It sits in the Entities group's own list item, beside the other entity links.
    const groupItem = within(nav).getByRole("button", { name: /entities/i }).closest("li");
    expect(groupItem).not.toBeNull();
    expect(within(groupItem as HTMLElement).getByRole("link", { name: /connections/i })).toBe(link);
    expect(within(groupItem as HTMLElement).getByRole("link", { name: /candidates/i })).toBeInTheDocument();
  });
});

describe("explorer entered from the nav (nothing selected)", () => {
  it("shows the empty picker state with no error and issues no graph request", () => {
    render(
      <MemoryRouter initialEntries={["/connections"]}>
        <ConnectionExplorerPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("pick-prompt")).toHaveTextContent(/choose both entities/i);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Entity A")).toBeInTheDocument();
    // No request fires: Connect has no pair to look up (a and b both null).
    expect(connectionMock).toHaveBeenCalledWith(null, null, expect.anything());
  });

  it("opens with the entity from the link already chosen as A", () => {
    render(
      <MemoryRouter initialEntries={["/connections?a=11111111-1111-4111-8111-111111111111"]}>
        <ConnectionExplorerPage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Entity 11111111/)).toBeInTheDocument();
    expect(screen.getByTestId("pick-prompt")).toBeInTheDocument();
  });
});
