import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EvidencePanel } from "../EvidencePanel";
import { A_ID, B_ID, fixturePairPassages } from "./fixtures";
import type { PairPassages } from "../../../api/graph";

const hookMock = vi.fn();
const fartherMock = vi.fn();
vi.mock("../../../hooks/usePairPassages", () => ({
  EVIDENCE_PAGE_SIZE: 12,
  usePairPassages: (...args: unknown[]) => hookMock(...args),
  useFartherVideos: (...args: unknown[]) => fartherMock(...args),
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

/** Spread a PairPassages into the hook's flattened return (items + first page). */
function loaded(ev: PairPassages) {
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
  fartherMock.mockReset();
  fartherMock.mockReturnValue({
    items: [],
    total: undefined,
    isLoading: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  });
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
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    renderPanel();
    expect(hookMock).toHaveBeenCalledWith(A_ID, B_ID, 30);
    expect(
      screen.getByRole("heading", { name: /discussed together/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("evidence-counts")).toHaveTextContent(
      "1 discussion passage across 1 video, 1 channel; closest mentions 8 s apart.",
    );
    expect(screen.getAllByTestId("evidence-item")).toHaveLength(1);
  });

  it("has the exact heading and never claims a relationship (FR-017)", () => {
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    renderPanel();
    expect(
      screen.getByRole("heading", { name: "Where they're discussed together" }),
    ).toBeInTheDocument();
    const text = screen.getByTestId("evidence-panel").textContent ?? "";
    expect(text).not.toMatch(/relationship|related/i);
  });

  it("passes an explicit window to the hook", () => {
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    render(
      <MemoryRouter>
        <EvidencePanel entityAId={A_ID} entityBId={B_ID} window={120} />
      </MemoryRouter>,
    );
    expect(hookMock).toHaveBeenCalledWith(A_ID, B_ID, 120);
  });

  it("offers the four windows as a radio group, with the current one checked", () => {
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    renderPanel();
    const group = screen.getByRole("group", { name: "Mentioned within" });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => (r as HTMLInputElement).value)).toEqual([
      "15",
      "30",
      "60",
      "120",
    ]);
    expect(screen.getByRole("radio", { name: "30 s" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "15 s" })).not.toBeChecked();
  });

  it("calls onWindowChange with the chosen number", () => {
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    const onWindowChange = vi.fn();
    render(
      <MemoryRouter>
        <EvidencePanel
          entityAId={A_ID}
          entityBId={B_ID}
          window={30}
          onWindowChange={onWindowChange}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("radio", { name: "60 s" }));
    expect(onWindowChange).toHaveBeenCalledWith(60);
  });

  it("queries the hook with the new window and checks it when the prop changes", () => {
    hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
    const { rerender } = render(
      <MemoryRouter>
        <EvidencePanel entityAId={A_ID} entityBId={B_ID} window={30} />
      </MemoryRouter>,
    );
    rerender(
      <MemoryRouter>
        <EvidencePanel entityAId={A_ID} entityBId={B_ID} window={15} />
      </MemoryRouter>,
    );
    expect(hookMock).toHaveBeenLastCalledWith(A_ID, B_ID, 15);
    expect(screen.getByRole("radio", { name: "15 s" })).toBeChecked();
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
          fixturePairPassages({
            items: [],
            video_count: 0,
            returned: 0,
            basis_when_empty: "title",
            state: "no_transcript",
          }),
        ),
      ),
    );
    renderPanel();
    expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
      /Not spoken together in any transcript\..*co-occur through title mentions/,
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
        ...loaded(fixturePairPassages({ truncated: true, video_count: 30 })),
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
      state(loaded(fixturePairPassages({ truncated: false }))),
    );
    renderPanel();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a disabled loading state while fetching more, and the count is a polite live region", () => {
    hookMock.mockReturnValue(
      state({
        ...loaded(fixturePairPassages({ truncated: true, video_count: 90 })),
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
          fixturePairPassages({
            items: [],
            returned: 0,
            video_count: 5,
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
        ...loaded(fixturePairPassages({ truncated: true, video_count: 30 })),
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
        ...loaded(fixturePairPassages({ truncated: true, video_count: 30 })),
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

  describe("summary sentence", () => {
    it("uses plural forms", () => {
      hookMock.mockReturnValue(
        state(
          loaded(
            fixturePairPassages({
              passage_count: 7,
              video_count: 4,
              channel_count: 3,
              closest_gap_seconds: 5.6,
            }),
          ),
        ),
      );
      renderPanel();
      expect(screen.getByTestId("evidence-counts")).toHaveTextContent(
        "7 discussion passages across 4 videos, 3 channels; closest mentions 6 s apart.",
      );
    });

    it("omits the gap clause when there is none", () => {
      hookMock.mockReturnValue(
        state(loaded(fixturePairPassages({ closest_gap_seconds: null }))),
      );
      renderPanel();
      expect(screen.getByTestId("evidence-counts")).toHaveTextContent(
        /^1 discussion passage across 1 video, 1 channel\.$/,
      );
    });
  });

  describe("state notes", () => {
    it("shows an updating note together with the counts", () => {
      hookMock.mockReturnValue(
        state(loaded(fixturePairPassages({ pending_scopes: 2 }))),
      );
      renderPanel();
      expect(screen.getByTestId("evidence-pending")).toHaveTextContent(
        "Updating: 2 transcripts are being recomputed; counts may change.",
      );
      expect(screen.getByTestId("evidence-pending")).toHaveAttribute("role", "status");
      expect(screen.getByTestId("evidence-counts")).toBeInTheDocument();
    });

    it("uses singular for one pending transcript and shows no note at zero", () => {
      hookMock.mockReturnValue(
        state(loaded(fixturePairPassages({ pending_scopes: 1 }))),
      );
      const { unmount } = renderPanel();
      expect(screen.getByTestId("evidence-pending")).toHaveTextContent(
        "Updating: 1 transcript is being recomputed",
      );
      unmount();
      hookMock.mockReturnValue(state(loaded(fixturePairPassages())));
      renderPanel();
      expect(screen.queryByTestId("evidence-pending")).not.toBeInTheDocument();
    });

    it("lists failed transcripts behind a toggle and never says 'updating'", () => {
      hookMock.mockReturnValue(
        state(
          loaded(
            fixturePairPassages({
              failed_scopes: [
                {
                  video_id: "vid00000009",
                  language_code: "es",
                  video_title: "Failed Video Title",
                  channel_title: "Failed Channel",
                },
              ],
            }),
          ),
        ),
      );
      renderPanel();
      const toggle = screen.getByRole("button", {
        name: "1 transcript could not be computed; counts may be incomplete",
      });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText(/Failed Video Title/)).not.toBeInTheDocument();
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText(/Failed Video Title · Failed Channel · es/)).toBeInTheDocument();
      expect(screen.getByTestId("evidence-failed")).toHaveAttribute("role", "status");
      expect(screen.getByTestId("evidence-failed").textContent).not.toMatch(/updating/i);
    });
  });

  describe("empty outcomes by state", () => {
    function empty(overrides: Record<string, unknown>) {
      hookMock.mockReturnValue(
        state(
          loaded(
            fixturePairPassages({
              items: [],
              returned: 0,
              video_count: 0,
              passage_count: 0,
              channel_count: 0,
              closest_gap_seconds: null,
              ...overrides,
            }),
          ),
        ),
      );
    }

    it("no_passage_in_window names the window and offers the farther toggle", () => {
      empty({ state: "no_passage_in_window", farther_video_count: 2 });
      renderPanel();
      expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
        "No passage within 30 s.",
      );
      expect(
        screen.getByRole("button", {
          name: "Plus 2 videos where both are spoken farther apart",
        }),
      ).toBeInTheDocument();
    });

    it("no_transcript says so, without a basis", () => {
      empty({ state: "no_transcript" });
      renderPanel();
      expect(screen.getByTestId("evidence-empty")).toHaveTextContent(
        "Not spoken together in any transcript.",
      );
    });

    it("not_computed never shows a zero", () => {
      empty({ state: "not_computed" });
      renderPanel();
      const el = screen.getByTestId("evidence-empty");
      expect(el).toHaveTextContent(
        "Not computed yet; this updates automatically.",
      );
      expect(el.textContent).not.toMatch(/\b0\b/);
    });
  });

  describe("farther-apart videos", () => {
    const withFarther = () =>
      hookMock.mockReturnValue(
        state(loaded(fixturePairPassages({ farther_video_count: 1 }))),
      );

    it("enables the farther hook only when expanded", () => {
      withFarther();
      fartherMock.mockReturnValue({
        items: [
          {
            video_id: "vid00000007",
            video_title: "Farther Video Title",
            channel_title: "Farther Channel",
            language_code: "en",
            nearest_gap_seconds: 181.4,
            nearest_start_time: 225.7,
          },
        ],
        total: 1,
        isLoading: false,
        isError: false,
        hasNextPage: false,
        isFetchingNextPage: false,
        fetchNextPage: vi.fn(),
      });
      renderPanel();
      expect(fartherMock).toHaveBeenLastCalledWith(A_ID, B_ID, 30, false);
      const toggle = screen.getByRole("button", {
        name: "Plus 1 video where both are spoken farther apart",
      });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText(/Farther Video Title/)).not.toBeInTheDocument();

      fireEvent.click(toggle);
      expect(fartherMock).toHaveBeenLastCalledWith(A_ID, B_ID, 30, true);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(
        screen.getByText(/Farther Video Title · Farther Channel · en · 181s apart/),
      ).toBeInTheDocument();
      const link = screen.getByRole("link", { name: /^Open at 3:45 – Farther Video Title \(en\)$/ });
      expect(link).toHaveTextContent("Open at 3:45");
      expect(link).toHaveAttribute("href", "/videos/vid00000007?lang=en&t=225");
    });

    it("loads further pages on request", () => {
      withFarther();
      const fetchNextPage = vi.fn();
      fartherMock.mockReturnValue({
        items: [],
        total: 30,
        isLoading: false,
        isError: false,
        hasNextPage: true,
        isFetchingNextPage: false,
        fetchNextPage,
      });
      renderPanel();
      fireEvent.click(
        screen.getByRole("button", { name: /Plus 1 video where both/ }),
      );
      fireEvent.click(screen.getByRole("button", { name: "Show more" }));
      expect(fetchNextPage).toHaveBeenCalledTimes(1);
    });
  });

  it("offers Retry on a request error and calls refetch", () => {
    const refetch = vi.fn();
    hookMock.mockReturnValue(state({ isError: true, refetch }));
    renderPanel();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
