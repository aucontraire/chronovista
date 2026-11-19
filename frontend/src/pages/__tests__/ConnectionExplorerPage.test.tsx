/**
 * ConnectionExplorerPage — result states and deep-link prefill (Feature 113).
 * The Cytoscape canvas cannot rasterise in jsdom, so the graph and the picker's
 * search are stubbed; assertions run against the role-queryable table and states.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ConnectionKind } from "../../api/graph";
import { MemoryRouter } from "react-router-dom";

import { ConnectionExplorerPage } from "../ConnectionExplorerPage";
import { A_ID, B_ID, entityB, fixtureConnection, noPathConnection } from "../../components/graph/__tests__/fixtures";

const connectionMock = vi.fn();
const healthMock = vi.fn();
vi.mock("../../hooks/useConnection", () => ({
  useConnection: (...args: unknown[]) => connectionMock(...args),
  useGraphHealth: () => healthMock(),
  useGraphPresence: () => ({ present: new Set<string>(), isLoading: false }),
}));
vi.mock("../../hooks/useEntitySearch", () => ({
  useEntitySearch: () => ({ entities: [], isLoading: false, isFetched: false, isError: false, isBelowMinChars: true }),
}));
vi.mock("../../hooks/useEntityDetail", () => ({
  useEntityDetail: () => ({ entityDetail: undefined, aliasNames: [], isLoading: false }),
}));
vi.mock("../../components/graph/ConnectionGraph", () => ({
  ConnectionGraph: () => <div data-testid="connection-graph" />,
}));

function result(overrides: Record<string, unknown> = {}) {
  return { connection: undefined, isLoading: false, failure: null, refetch: vi.fn(), ...overrides };
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ConnectionExplorerPage />
    </MemoryRouter>,
  );
}

describe("ConnectionExplorerPage", () => {
  beforeEach(() => {
    connectionMock.mockReset();
    healthMock.mockReset();
    healthMock.mockReturnValue({ health: { status: "complete", servable: true, loaded_at: null, declared_layers: [] }, isLoading: false });
  });

  it("asks for both entities when none are chosen", () => {
    connectionMock.mockReturnValue(result());
    renderAt("/connections");
    expect(screen.getByTestId("pick-prompt")).toBeInTheDocument();
  });

  it("prefills both endpoints from ?a=&b= and requests that pair", () => {
    connectionMock.mockReturnValue(result({ connection: fixtureConnection() }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(connectionMock).toHaveBeenCalledWith(A_ID, B_ID, expect.anything());
    const selected = screen.getAllByTestId("picker-selected").map((n) => n.textContent);
    expect(selected).toEqual(["Entity A", "Entity B"]);
  });

  it("renders table rows with endpoints marked for a connected pair", () => {
    connectionMock.mockReturnValue(result({ connection: fixtureConnection() }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
    expect(screen.getAllByText(/\(endpoint A\)/).length).toBeGreaterThan(0);
  });

  it("shows the coverage view (kb_degree) for a no-path result, not an error", () => {
    connectionMock.mockReturnValue(result({ connection: noPathConnection() }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("no-connection")).toBeInTheDocument();
    expect(screen.getByText("7 knowledge-base facts")).toBeInTheDocument();
    expect(screen.getByText("0 knowledge-base facts")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("graph-unavailable")).not.toBeInTheDocument();
  });

  it("shows 'not available yet' when the connect call returns 503", () => {
    connectionMock.mockReturnValue(result({ failure: { kind: "unavailable" } }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("graph-unavailable")).toHaveTextContent(/isn.t available yet/);
    expect(screen.queryByTestId("no-connection")).not.toBeInTheDocument();
  });

  it("shows 'not available yet' with the rebuild action when health says loading", () => {
    healthMock.mockReturnValue({ health: { status: "loading", servable: false, loaded_at: null, declared_layers: [] }, isLoading: false });
    connectionMock.mockReturnValue(result());
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("graph-unavailable")).toHaveTextContent(/being rebuilt/);
    expect(connectionMock.mock.calls[0]?.[2]).toMatchObject({ enabled: false });
  });

  it("distinguishes an entity missing from the graph from 'no connection'", () => {
    connectionMock.mockReturnValue(result({ failure: { kind: "not_in_graph", detail: undefined } }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("not-in-graph")).toHaveTextContent(/older than your library/);
    expect(screen.queryByTestId("no-connection")).not.toBeInTheDocument();
  });

  it("never presents two outcomes at once — unavailable excludes result/no-path/not-in-graph (SC-005)", () => {
    healthMock.mockReturnValue({ health: { status: "loading", servable: false, loaded_at: "2026-11-18T00:00:00Z", declared_layers: [] }, isLoading: false });
    connectionMock.mockReturnValue(result({ failure: { kind: "unavailable" } }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("graph-unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("no-connection")).not.toBeInTheDocument();
    expect(screen.queryByTestId("not-in-graph")).not.toBeInTheDocument();
    // FR-017: the 'graph as of' line is hidden when the graph is not servable.
    expect(screen.queryByTestId("graph-as-of")).not.toBeInTheDocument();
  });

  it("shows the 'graph as of' line when the graph is servable (FR-017)", () => {
    healthMock.mockReturnValue({ health: { status: "complete", servable: true, loaded_at: "2026-11-18T12:00:00Z", declared_layers: ["observed"] }, isLoading: false });
    connectionMock.mockReturnValue(result({ connection: fixtureConnection() }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("graph-as-of")).toHaveTextContent(/Graph as of/);
  });

  it("offers an external lookup for each endpoint in the no-path coverage view (US3, FR-012)", () => {
    connectionMock.mockReturnValue(result({ connection: noPathConnection() }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    // useEntityDetail is mocked with no enrichment, so the fallback Wikidata lookup renders —
    // one per endpoint, so the gap case is always actionable (not blank for un-enriched entities).
    expect(screen.getAllByText("Look up on Wikidata")).toHaveLength(2);
  });

  it("enforces the reach floor (3) and the category-size default (500) in the controls (US4, FR-013/FR-014)", () => {
    connectionMock.mockReturnValue(result());
    renderAt("/connections");
    const reach = screen.getByLabelText(/reach/i) as HTMLInputElement;
    expect(reach.min).toBe("3");
    expect(reach.max).toBe("6"); // mirror the server le=6 cap
    expect(reach.value).toBe("3");
    // Typing above the ceiling clamps to 6 (never sent as 8 → avoids a 422 the user can't read).
    fireEvent.change(reach, { target: { value: "8" } });
    expect(reach.value).toBe("6");
    const cat = screen.getByLabelText(/largest category size/i) as HTMLInputElement;
    expect(cat.value).toBe("500");
  });

  it("surfaces 'not available' up-front when health is unservable, before any entity is picked (FR-010)", () => {
    // Regression: the banner used to be gated on `ready` (both entities picked), so an unloaded
    // or down graph looked fully functional until you tried to connect. Health alone must trigger
    // it — and the pick-prompt yields to it.
    healthMock.mockReturnValue({ health: { status: null, servable: false, loaded_at: null, declared_layers: [] }, isLoading: false });
    connectionMock.mockReturnValue(result());
    renderAt("/connections"); // no ?a=&b= → not ready
    expect(screen.getByTestId("graph-unavailable")).toHaveTextContent(/isn.t available yet/);
    expect(screen.queryByTestId("pick-prompt")).not.toBeInTheDocument();
  });

  function withChains(kinds: ConnectionKind[], kbDegreeA = 7, kbDegreeB = 7) {
    const base = noPathConnection();
    return {
      ...base,
      entity_a: { ...base.entity_a, kb_degree: kbDegreeA },
      entity_b: { ...entityB, kb_degree: kbDegreeB },
      has_connection: true,
      chains: kinds.map((kind) => ({
        kind,
        truncated: false,
        score: null,
        steps: [{ edge_type: "LINKED", kind, to_node: { ...entityB, kb_degree: kbDegreeB }, specificity: null, forward: true }],
      })),
    };
  }

  it("shows the coverage view alongside co-occurrence rows for a co-occurrence-only pair", () => {
    connectionMock.mockReturnValue(
      result({ connection: withChains(["co_occurrence_transcript", "co_occurrence_tags"]) }),
    );
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("no-connection")).toBeInTheDocument();
    expect(screen.getAllByText("7 knowledge-base facts").length).toBe(2);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBe(3); // header + one row per channel
  });

  it("does not show the coverage view for a shared-referent connection", () => {
    connectionMock.mockReturnValue(result({ connection: withChains(["shared_referent"]) }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.queryByTestId("no-connection")).not.toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows the coverage view for a shared-category-only pair (not a KB connection)", () => {
    connectionMock.mockReturnValue(result({ connection: withChains(["shared_category"]) }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("no-connection")).toBeInTheDocument();
  });

  it("omits the hop-limit advice when there is no KB connection, keeps it when connected", () => {
    connectionMock.mockReturnValue(
      result({ connection: { ...withChains(["co_occurrence_tags"]), any_truncated: true } }),
    );
    const { unmount } = renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.queryByText(/hop limit; a longer path may exist/)).not.toBeInTheDocument();
    unmount();
    connectionMock.mockReturnValue(
      result({ connection: { ...withChains(["asserted"]), any_truncated: true } }),
    );
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByText(/hop limit; a longer path may exist/)).toBeInTheDocument();
  });

  it("uses enrichment-gap wording and no larger-reach advice when an endpoint has kb_degree < 3", () => {
    connectionMock.mockReturnValue(
      result({ connection: { ...withChains(["co_occurrence_tags"], 7, 1), any_truncated: true } }),
    );
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    const view = screen.getByTestId("no-connection");
    expect(view).toHaveTextContent(/barely in the knowledge base/);
    expect(view).toHaveTextContent(/enrichment gap/);
    expect(view).not.toHaveTextContent(/larger reach/);
  });

  it("keeps the unrelated-or-thin wording when both endpoints have kb_degree >= 3", () => {
    connectionMock.mockReturnValue(result({ connection: withChains(["co_occurrence_tags"], 5, 9) }));
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    expect(screen.getByTestId("no-connection")).toHaveTextContent(/unrelated, or that one is thinly covered/);
  });

  it("says 'maximum reach', not 'try a larger reach', when truncated at the hop cap", () => {
    // Regression: the advice used to say "try a larger reach" even at the ceiling (reach 6),
    // which is unactionable exactly when shown.
    connectionMock.mockReturnValue(
      result({
        connection: {
          ...withChains(["co_occurrence_tags"], 5, 9),
          any_truncated: true,
          searched_max_hops: 6,
        },
      }),
    );
    renderAt(`/connections?a=${A_ID}&b=${B_ID}`);
    const view = screen.getByTestId("no-connection");
    expect(view).toHaveTextContent(/maximum reach/);
    expect(view).not.toHaveTextContent(/try a larger reach/);
  });
});
