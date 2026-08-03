/**
 * Watched indicator on PlaylistVideoCard (Feature 061, T063).
 *
 * Covers FR-009 (each row exposes its watched state) and FR-032 (that state is
 * carried by a text alternative, never by colour or icon shape alone).
 *
 * FR-032 is the reason these assertions read the badge's *text* rather than its
 * classes: a test that checked for `bg-emerald-100` would keep passing if the
 * word were removed, which is precisely the failure the requirement forbids.
 *
 * Located in `tests/` rather than `src/**\/__tests__/` because it uses
 * `renderWithProviders` (GitHub #159, research R7).
 */

import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../test-utils";
import { PlaylistVideoCard } from "../../src/components/PlaylistVideoCard";
import type { PlaylistVideoItem } from "../../src/types/playlist";

// No `as PlaylistVideoItem` cast: `frontend/tests/` is outside tsconfig's
// `include`, so a cast here would be the only thing standing between a wrong
// fixture and a confusing runtime failure — and it would lose that argument.
// Every field is spelled out so the fixture breaks loudly if the type changes.
function video(overrides: Partial<PlaylistVideoItem> = {}): PlaylistVideoItem {
  return {
    video_id: "vid1",
    title: "A video",
    channel_title: "A channel",
    channel_id: "UC1",
    upload_date: "2024-01-01T00:00:00Z",
    duration: 120,
    view_count: 10,
    position: 0,
    availability_status: "available",
    watched: false,
    transcript_summary: {
      count: 0,
      languages: [],
      has_manual: false,
      has_corrections: false,
    },
    ...overrides,
  };
}

function render(overrides: Partial<PlaylistVideoItem> = {}) {
  renderWithProviders(<PlaylistVideoCard video={video(overrides)} />, {
    initialEntries: ["/playlists/PLtest"],
  });
}

describe("PlaylistVideoCard watched indicator", () => {
  it("labels a watched video in words (FR-009, FR-032)", () => {
    render({ watched: true });
    expect(screen.getByText("Watched")).toBeInTheDocument();
    expect(screen.queryByText("Unwatched")).not.toBeInTheDocument();
  });

  it("labels an unwatched video in words (FR-009, FR-032)", () => {
    render({ watched: false });
    expect(screen.getByText("Unwatched")).toBeInTheDocument();
    expect(screen.queryByText("Watched")).not.toBeInTheDocument();
  });

  it("distinguishes the two states by text, not colour alone (FR-032)", () => {
    render({ watched: true });
    const watched = screen.getByText("Watched").textContent;

    renderWithProviders(<PlaylistVideoCard video={video({ watched: false })} />, {
      initialEntries: ["/playlists/PLtest"],
    });
    const unwatched = screen.getByText("Unwatched").textContent;

    // Strip styling out of the comparison entirely: the two states must differ
    // in their text content, which is what survives monochrome and a screen
    // reader.
    expect(watched).not.toEqual(unwatched);
  });

  it("still reports watched state for an unavailable video (FR-011)", () => {
    // A deleted video you watched is still watched — watch history outlives
    // availability, and the badge must not silently drop.
    render({ watched: true, availability_status: "deleted" });
    expect(screen.getByText("Watched")).toBeInTheDocument();
  });
});
