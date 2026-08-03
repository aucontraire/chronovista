/**
 * Tests for the Overview Dashboard breakdown cards (Feature 061, T060).
 *
 * Covers FR-020/FR-020a (Watch Later depth and its absent state), FR-021/FR-022
 * (inventory over types present, system lists labelled in words), FR-023/FR-023a
 * (liked as a video attribute, not a playlist type), FR-024 (saved is never
 * called watched), FR-025/FR-025a (deep link only when unambiguous), and
 * FR-027/FR-027a (zero and loading states).
 *
 * Located in `tests/` rather than `src/**\/__tests__/` because it uses
 * `renderWithProviders` (GitHub #159, research R7).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within } from "@testing-library/react";

import { renderWithProviders } from "../test-utils";
import { OverviewPage } from "../../src/pages/OverviewPage";
import { useOverview } from "../../src/hooks/useOverview";
import type { Overview } from "../../src/api/overview";

vi.mock("../../src/hooks/useOverview", () => ({
  useOverview: vi.fn(),
}));

const mockUseOverview = vi.mocked(useOverview);

function overview(patch: Partial<Overview> = {}): Overview {
  return {
    saved_and_forgotten: 609,
    watch_later: { total: 4973, unwatched: 2392, playlist_id: "WL" },
    playlist_inventory: [
      { playlist_type: "regular", playlist_count: 290, is_system: false },
      { playlist_type: "watch_later", playlist_count: 1, is_system: true },
      { playlist_type: "history", playlist_count: 1, is_system: true },
    ],
    rollup: {
      watched_videos: 51271,
      saved_curated_videos: 20259,
      liked_videos: 5830,
    },
    ...patch,
  };
}

function render(patch: Partial<Overview> = {}) {
  mockUseOverview.mockReturnValue({
    overview: overview(patch),
    isLoading: false,
    isError: false,
    error: null,
    retry: vi.fn(),
  });
  renderWithProviders(<OverviewPage />);
}

/** The tile whose `<dt>` is `label`, within the grid named by `headingId`. */
function tile(headingId: string, label: string): HTMLElement {
  const list = document.querySelector(`dl[aria-labelledby="${headingId}"]`);
  expect(list).not.toBeNull();
  const term = within(list as HTMLElement).getByText(label);
  return term.closest("div") as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("OverviewPage — Watch Later depth (FR-020)", () => {
  it("shows queue total and unwatched", () => {
    render();
    expect(tile("overview-watch-later", "In the queue")).toHaveTextContent(
      "4,973"
    );
    expect(tile("overview-watch-later", "Unwatched")).toHaveTextContent("2,392");
  });

  it("links unwatched to the playlist pre-filtered to Unwatched (FR-025)", () => {
    render();
    const link = screen.getByRole("link", {
      name: /unwatched videos in Watch Later/i,
    });
    expect(link.getAttribute("href")).toBe(
      "/playlists/WL?watched_status=unwatched"
    );
  });

  it("renders unwatched inert when the link target is ambiguous (FR-025a)", () => {
    render({ watch_later: { total: 10, unwatched: 4, playlist_id: null } });

    expect(
      screen.queryByRole("link", { name: /unwatched videos in Watch Later/i })
    ).not.toBeInTheDocument();
    // The figure is still shown — it just is not interactive.
    expect(tile("overview-watch-later", "Unwatched")).toHaveTextContent("4");
  });

  it("renders an explicit absent state, not zeros, when there is no queue (FR-020a)", () => {
    render({ watch_later: null });

    expect(screen.getByText(/no watch later playlist found/i)).toBeInTheDocument();
    // Zeros here would read as "your queue is empty", a different fact.
    const card = screen.getByText(/no watch later playlist found/i).closest(
      "section"
    ) as HTMLElement;
    expect(within(card).queryByText("0")).not.toBeInTheDocument();
  });

  it("distinguishes a present-but-empty queue with zeros", () => {
    render({ watch_later: { total: 0, unwatched: 0, playlist_id: "WL" } });

    expect(
      screen.queryByText(/no watch later playlist found/i)
    ).not.toBeInTheDocument();
    expect(tile("overview-watch-later", "In the queue")).toHaveTextContent("0");
  });
});

describe("OverviewPage — playlist inventory (FR-021, FR-022)", () => {
  it("renders only the types present in the data", () => {
    render();
    const list = document.querySelector(
      'dl[aria-labelledby="overview-inventory"]'
    ) as HTMLElement;

    expect(within(list).getByText("Curated playlists")).toBeInTheDocument();
    expect(within(list).getByText("Watch Later")).toBeInTheDocument();
    expect(within(list).getByText("History")).toBeInTheDocument();
    // `favorites` exists upstream but not in the data — never a permanent zero.
    expect(within(list).queryByText("Favorites")).not.toBeInTheDocument();
  });

  it("marks system lists with words, not styling alone (FR-022, FR-034)", () => {
    render();
    expect(tile("overview-inventory", "Watch Later")).toHaveTextContent(
      "System list"
    );
    expect(tile("overview-inventory", "History")).toHaveTextContent(
      "System list"
    );
    expect(tile("overview-inventory", "Curated playlists")).not.toHaveTextContent(
      "System list"
    );
  });

  it("labels an unrecognised future type instead of dropping it (FR-021)", () => {
    render({
      playlist_inventory: [
        { playlist_type: "regular", playlist_count: 2, is_system: false },
        { playlist_type: "some_new_type", playlist_count: 7, is_system: true },
      ],
    });

    const t = tile("overview-inventory", "Some new type");
    expect(t).toHaveTextContent("7");
    expect(t).toHaveTextContent("System list");
  });

  it("renders an empty-library state cleanly (FR-027)", () => {
    render({ playlist_inventory: [] });
    expect(screen.getByText(/no playlists yet/i)).toBeInTheDocument();
  });
});

describe("OverviewPage — rollups (FR-023, FR-023a, FR-024)", () => {
  it("keeps saved and watched verbally distinct", () => {
    render();
    const list = document.querySelector(
      'dl[aria-labelledby="overview-rollup"]'
    ) as HTMLElement;

    expect(within(list).getByText("Watched videos")).toBeInTheDocument();
    const saved = within(list).getByText(/saved in curated playlists/i);
    // Membership must never be described as watching (FR-024).
    expect(saved.textContent?.toLowerCase()).not.toContain("watched");
  });

  it("places liked videos among the rollups, never in the inventory (FR-023)", () => {
    render();

    expect(tile("overview-rollup", "Liked videos")).toHaveTextContent("5,830");

    const inventory = document.querySelector(
      'dl[aria-labelledby="overview-inventory"]'
    ) as HTMLElement;
    expect(within(inventory).queryByText("Liked videos")).not.toBeInTheDocument();
  });

  it("distinguishes a liked playlist count from the liked-video count (FR-023a)", () => {
    render({
      playlist_inventory: [
        { playlist_type: "regular", playlist_count: 290, is_system: false },
        { playlist_type: "liked", playlist_count: 1, is_system: true },
      ],
    });

    // Same word, different quantities from different tables: 1 playlist vs
    // 5,830 videos. They must not be presented as one figure.
    expect(tile("overview-inventory", "Liked playlists")).toHaveTextContent("1");
    expect(tile("overview-rollup", "Liked videos")).toHaveTextContent("5,830");
  });

  it("renders zero rollups as figures, not blanks (FR-027)", () => {
    render({
      rollup: { watched_videos: 0, saved_curated_videos: 0, liked_videos: 0 },
    });
    expect(tile("overview-rollup", "Watched videos")).toHaveTextContent("0");
  });
});

describe("OverviewPage — breakdown loading state (FR-027a)", () => {
  it("shows skeletons for every card, not zeros", () => {
    mockUseOverview.mockReturnValue({
      overview: undefined,
      isLoading: true,
      isError: false,
      error: null,
      retry: vi.fn(),
    });
    renderWithProviders(<OverviewPage />);

    expect(
      screen.getByTestId("overview-watch-later-loading")
    ).toBeInTheDocument();
    expect(screen.getByTestId("overview-inventory-loading")).toBeInTheDocument();
    expect(screen.getByTestId("overview-rollup-loading")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
