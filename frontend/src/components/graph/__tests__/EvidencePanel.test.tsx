import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EvidencePanel } from "../EvidencePanel";
import { A_ID, B_ID, fixtureEvidence } from "./fixtures";
import type { ConnectionEvidence } from "../../../api/graph";

const hookMock = vi.fn();
vi.mock("../../../hooks/useConnectionEvidence", () => ({
  EVIDENCE_PAGE_SIZE: 12,
  useConnectionEvidence: (...args: unknown[]) => hookMock(...args),
}));

function state(overrides: Record<string, unknown> = {}) {
  return {
    items: [],
    first: undefined,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    ...overrides,
  };
}

/** Spread a ConnectionEvidence into the hook's flattened return (items + first page). */
function loaded(ev: ConnectionEvidence) {
  return { items: ev.items, first: ev };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <EvidencePanel entityAId={A_ID} entityBId={B_ID} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  hookMock.mockReset();
  // jsdom has no IntersectionObserver; the panel constructs one when there's a next page.
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

describe("EvidencePanel", () => {
  it("shows items and the denominator-labeled count line", () => {
    hookMock.mockReturnValue(state(loaded(fixtureEvidence())));
    renderPanel();
    expect(hookMock).toHaveBeenCalledWith(A_ID, B_ID);
    expect(
      screen.getByRole("heading", { name: /discussed together/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("evidence-counts")).toHaveTextContent(
      "Spoken together in 1 video (3 transcripts).",
    );
    expect(screen.getAllByTestId("evidence-item")).toHaveLength(1);
  });

  it("announces loading with role=status", () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    renderPanel();
    expect(screen.getByTestId("evidence-loading")).toHaveAttribute(
      "role",
      "status",
    );
  });

  it("states the basis when there is no readable passage", () => {
    hookMock.mockReturnValue(
      state(
        loaded(
          fixtureEvidence({
            items: [],
            total_available: 0,
            raw_cooccurrence_count: 0,
            returned: 0,
            basis_when_empty: "title",
          }),
        ),
      ),
    );
    renderPanel();
    expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
      /co-occur through title mentions/,
    );
    expect(screen.queryByTestId("evidence-item")).not.toBeInTheDocument();
  });

  it("degrades to a panel-level alert on error", () => {
    hookMock.mockReturnValue(state({ isError: true }));
    renderPanel();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /rest of this page is unaffected/i,
    );
  });

  it("offers Show more while a next page exists, and calls fetchNextPage", () => {
    const fetchNextPage = vi.fn();
    hookMock.mockReturnValue(
      state({
        ...loaded(fixtureEvidence({ truncated: true, total_available: 30 })),
        hasNextPage: true,
        fetchNextPage,
      }),
    );
    renderPanel();
    fireEvent.click(
      screen.getByRole("button", { name: "Show more co-mention videos" }),
    );
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("hides Show more when there is no next page", () => {
    hookMock.mockReturnValue(
      state(loaded(fixtureEvidence({ truncated: false }))),
    );
    renderPanel();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a disabled loading state while fetching more, and the count is a polite live region", () => {
    hookMock.mockReturnValue(
      state({
        ...loaded(fixtureEvidence({ truncated: true, total_available: 90 })),
        hasNextPage: true,
        isFetchingNextPage: true,
      }),
    );
    renderPanel();
    expect(screen.getByTestId("evidence-counts")).toHaveAttribute(
      "aria-live",
      "polite",
    );
    const btn = screen.getByRole("button", {
      name: "Show more co-mention videos",
    });
    expect(btn).toHaveTextContent("Loading more…");
    expect(btn).toHaveAttribute("aria-disabled", "true");
  });

  it("says there are no more passages for a past-end page", () => {
    hookMock.mockReturnValue(
      state(
        loaded(
          fixtureEvidence({
            items: [],
            returned: 0,
            total_available: 5,
            basis_when_empty: null,
          }),
        ),
      ),
    );
    renderPanel();
    expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
      /no more transcript passages/i,
    );
  });

  it("says no passage mentions both when total is 0 and no basis", () => {
    hookMock.mockReturnValue(
      state(
        loaded(
          fixtureEvidence({
            items: [],
            returned: 0,
            total_available: 0,
            raw_cooccurrence_count: 0,
            basis_when_empty: null,
          }),
        ),
      ),
    );
    renderPanel();
    expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
      /No transcript passage mentions both/,
    );
  });

  it("does not observe after a failed next page, and shows an inline alert", () => {
    const observe = vi.fn();
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = observe;
        disconnect() {}
      },
    );
    hookMock.mockReturnValue(
      state({
        ...loaded(fixtureEvidence({ truncated: true, total_available: 30 })),
        hasNextPage: true,
        isError: true,
        isFetchNextPageError: true,
      }),
    );
    renderPanel();
    expect(observe).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/load more/i);
  });

  it("fetches the next page when the sentinel intersects", () => {
    let cb: IntersectionObserverCallback = () => {};
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(c: IntersectionObserverCallback) {
          cb = c;
        }
        observe() {}
        disconnect() {}
      },
    );
    const fetchNextPage = vi.fn();
    hookMock.mockReturnValue(
      state({
        ...loaded(fixtureEvidence({ truncated: true, total_available: 30 })),
        hasNextPage: true,
        fetchNextPage,
      }),
    );
    renderPanel();
    cb(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });
});
