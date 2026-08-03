/**
 * Tests for the Overview Dashboard headline (Feature 061, T048).
 *
 * Covers FR-014 (prominent metric), FR-018/FR-025 (links to the filtered list),
 * FR-019 (explicit zero state), and FR-027a/b/c (loading, error, retry).
 *
 * Located in `tests/` rather than `src/**\/__tests__/` because it uses
 * `renderWithProviders`: `tsconfig.json` includes only `src`, so a `src/` file
 * importing `tests/test-utils` drags that file into the type-check program and
 * exposes latent errors in it (GitHub #159, research R7).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../test-utils";
import { OverviewPage } from "../../src/pages/OverviewPage";
import { useOverview } from "../../src/hooks/useOverview";

vi.mock("../../src/hooks/useOverview", () => ({
  useOverview: vi.fn(),
}));

const mockUseOverview = vi.mocked(useOverview);

function overview(savedAndForgotten: number) {
  return {
    saved_and_forgotten: savedAndForgotten,
    watch_later: { total: 4973, unwatched: 2392, playlist_id: "WL" },
    playlist_inventory: [
      { playlist_type: "regular", playlist_count: 290, is_system: false },
    ],
    rollup: {
      watched_videos: 51271,
      saved_curated_videos: 20259,
      liked_videos: 5830,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseOverview.mockReturnValue({
    overview: overview(609),
    isLoading: false,
    isError: false,
    error: null,
    retry: vi.fn(),
  });
});

describe("OverviewPage — Saved & Forgotten headline", () => {
  it("shows the metric with its label associated (FR-014, FR-033)", () => {
    renderWithProviders(<OverviewPage />);

    const terms = Array.from(document.querySelectorAll("dl dt")).map((el) =>
      el.textContent?.trim()
    );
    const values = Array.from(document.querySelectorAll("dl dd")).map((el) =>
      el.textContent?.trim()
    );

    expect(terms).toContain("Saved & Forgotten");
    expect(values).toContain("609");
  });

  it("titles the page with an h2, leaving the single h1 to the shell", () => {
    renderWithProviders(<OverviewPage />);

    // `layout/Header.tsx` renders the document's only `h1` ("Chronovista").
    // A page-level `h1` here would give the rendered document two top-level
    // headings and break the outline screen-reader users navigate by. Every
    // mature page (Videos, Settings) uses `h2` for its title for this reason.
    expect(
      screen.queryByRole("heading", { level: 1 })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Overview" })
    ).toBeInTheDocument();
  });

  it("links to the filtered list carrying include_unavailable (FR-018, FR-018b)", () => {
    renderWithProviders(<OverviewPage />);

    const link = screen.getByRole("link", { name: /saved & forgotten/i });
    const href = link.getAttribute("href") ?? "";

    expect(href).toContain("/videos");
    expect(href).toContain("saved_unwatched=true");
    // Without this the user clicks 609 and lands on 586 — the dashboard counts
    // unavailable videos, the list hides them by default.
    expect(href).toContain("include_unavailable=true");
  });

  it("renders an explicit zero state, not a bare 0 (FR-019)", () => {
    mockUseOverview.mockReturnValue({
      overview: overview(0),
      isLoading: false,
      isError: false,
      error: null,
      retry: vi.fn(),
    });
    renderWithProviders(<OverviewPage />);

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/nothing forgotten/i)).toBeInTheDocument();
  });

  it("shows a loading state distinguishable from zero (FR-027a)", () => {
    mockUseOverview.mockReturnValue({
      overview: undefined,
      isLoading: true,
      isError: false,
      error: null,
      retry: vi.fn(),
    });
    renderWithProviders(<OverviewPage />);

    expect(screen.getByTestId("overview-loading")).toBeInTheDocument();
    // A zero value must not be implied while loading.
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows an error state distinguishable from an empty library (FR-027b)", () => {
    mockUseOverview.mockReturnValue({
      overview: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      retry: vi.fn(),
    });
    renderWithProviders(<OverviewPage />);

    expect(screen.getByText(/could not load your overview/i)).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("offers retry without a full reload (FR-027c)", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    mockUseOverview.mockReturnValue({
      overview: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      retry,
    });
    renderWithProviders(<OverviewPage />);

    await user.click(screen.getByRole("button", { name: /try again|retry/i }));
    expect(retry).toHaveBeenCalled();
  });
});
