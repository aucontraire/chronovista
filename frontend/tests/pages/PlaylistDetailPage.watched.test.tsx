/**
 * URL persistence for the watched filter (Feature 061, T029).
 *
 * Covers FR-007a (the filter lives in the address under the same name the API
 * uses), FR-007b (arriving with it pre-set renders filtered), FR-007c (the
 * default is never written), and FR-007e (an invalid value falls back to All).
 *
 * This is the mechanism FR-025 depends on: the dashboard's "Watch Later
 * unwatched" card links to this page pre-filtered, which is only possible
 * because the filter is addressable.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders, getTestLocation } from "../test-utils";
import { PlaylistDetailPage } from "../../src/pages/PlaylistDetailPage";
import { usePlaylistDetail, usePlaylistVideos } from "../../src/hooks";

vi.mock("../../src/hooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../src/hooks")>();
  return {
    ...original,
    usePlaylistDetail: vi.fn(),
    usePlaylistVideos: vi.fn(),
  };
});

vi.mock("../../src/components/PlaylistVideoCard", () => ({
  PlaylistVideoCard: () => <div data-testid="video-card" />,
}));

const mockDetail = vi.mocked(usePlaylistDetail);
const mockVideos = vi.mocked(usePlaylistVideos);

beforeEach(() => {
  vi.clearAllMocks();

  mockDetail.mockReturnValue({
    playlist: {
      playlist_id: "PLtest",
      title: "Test playlist",
      description: "d",
      video_count: 3,
      privacy_status: "private",
      is_linked: true,
      playlist_type: "regular",
      default_language: null,
      channel_id: null,
      published_at: null,
      deleted_flag: false,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
    isLoading: false,
    isError: false,
    error: null,
    retry: vi.fn(),
  } as unknown as ReturnType<typeof usePlaylistDetail>);

  mockVideos.mockReturnValue({
    videos: [],
    total: 1,
    stats: { playlist_total: 3, watched: 2, unwatched: 1 },
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  } as unknown as ReturnType<typeof usePlaylistVideos>);
});

function lastCallOptions(): Record<string, unknown> {
  const call = mockVideos.mock.calls[mockVideos.mock.calls.length - 1];
  return (call?.[1] ?? {}) as Record<string, unknown>;
}

describe("PlaylistDetailPage watched filter URL persistence", () => {
  it("defaults to all and does not write the param (FR-007c)", () => {
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest"],
      path: "/playlists/:playlistId",
    });

    expect(lastCallOptions().watchedStatus).toBe("all");
    expect(getTestLocation().search).not.toContain("watched_status");
  });

  it("writes the selected value to the address (FR-007a)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest"],
      path: "/playlists/:playlistId",
    });

    await user.click(screen.getByRole("tab", { name: /only unwatched/i }));

    // Same name the API uses, so address and request cannot drift (FR-007a).
    expect(getTestLocation().search).toContain("watched_status=unwatched");
  });

  it("renders pre-filtered when the address already carries it (FR-007b)", () => {
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?watched_status=unwatched"],
      path: "/playlists/:playlistId",
    });

    // No interaction required — this is what makes the dashboard deep link
    // in FR-025 possible.
    expect(lastCallOptions().watchedStatus).toBe("unwatched");
    expect(
      screen.getByRole("tab", { name: /only unwatched/i })
    ).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to all for an invalid value rather than erroring (FR-007e)", () => {
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?watched_status=bogus"],
      path: "/playlists/:playlistId",
    });

    expect(lastCallOptions().watchedStatus).toBe("all");
    expect(screen.getByRole("tab", { name: /all videos/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("preserves the sort selection when the filter changes (FR-007d)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?sort_by=title&sort_order=desc"],
      path: "/playlists/:playlistId",
    });

    await user.click(screen.getByRole("tab", { name: /only watched/i }));

    const search = getTestLocation().search;
    expect(search).toContain("watched_status=watched");
    expect(search).toContain("sort_by=title");
    expect(search).toContain("sort_order=desc");
  });

  it("shows the stats header, unchanged by the filter (FR-004, FR-005b)", () => {
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?watched_status=unwatched"],
      path: "/playlists/:playlistId",
    });

    // "Watched" also appears as a tab label, so scope to the stats list. Each
    // figure must sit in a <dt>/<dd> pair so the number and what it counts are
    // programmatically associated (FR-033).
    const terms = Array.from(document.querySelectorAll("dl dt")).map((el) =>
      el.textContent?.trim()
    );
    const values = Array.from(document.querySelectorAll("dl dd")).map((el) =>
      el.textContent?.trim()
    );

    expect(terms).toEqual(["Total", "Watched", "Unwatched"]);
    // The playlist figures (3/2/1), NOT the filtered result count of 1 —
    // the header does not move with the filter (FR-005b).
    expect(values).toEqual(["3", "2", "1"]);
  });

  it("announces the filtered result count to assistive tech (FR-031)", () => {
    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?watched_status=unwatched"],
      path: "/playlists/:playlistId",
    });

    // A filter change alters the result set, which must be perceivable without
    // sight — the count lives in a polite live region rather than only in the
    // visual list. The page carries more than one status region, so find the
    // one that carries the count rather than assuming there is exactly one.
    const regions = screen.getAllByRole("status");
    const countRegion = regions.find((el) => /\d+\s+videos?/.test(el.textContent ?? ""));

    expect(countRegion, "no live region announces the result count").toBeDefined();
    expect(countRegion).toHaveAttribute("aria-live", "polite");
    expect(countRegion?.textContent).toContain("1 video");
    // The announcement says the list is filtered, so the number is not mistaken
    // for the playlist's full size.
    expect(countRegion?.textContent).toContain("filtered");
  });

  it("does not announce a stale count while results are loading (FR-031)", () => {
    mockVideos.mockReturnValue({
      videos: [],
      total: null,
      stats: null,
      loadedCount: 0,
      isLoading: true,
      isError: false,
      error: null,
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
      retry: vi.fn(),
      loadMoreRef: { current: null },
    } as unknown as ReturnType<typeof usePlaylistVideos>);

    renderWithProviders(<PlaylistDetailPage />, {
      initialEntries: ["/playlists/PLtest?watched_status=unwatched"],
      path: "/playlists/:playlistId",
    });

    // Announcing the previous filter's total mid-load would state a number that
    // is about to change. The loading skeleton has its own status region, so
    // assert on the announced *text* rather than on the role's absence.
    const announced = screen
      .getAllByRole("status")
      .map((el) => el.textContent ?? "")
      .join(" ");

    expect(announced).not.toMatch(/\d+\s+videos?/);
    expect(announced).toMatch(/loading/i);
  });
});
