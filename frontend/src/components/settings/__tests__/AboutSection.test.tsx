/**
 * Tests for AboutSection component.
 *
 * Coverage:
 * - Loading skeleton shown when isLoading=true (role="status" with aria-label)
 * - Error state shows alert with error message and Retry button
 * - Version display shows backend and frontend versions using dl/dt/dd markup
 * - Database statistics grid shows all 6 entity counts
 * - Sync timestamps display with relative formatting
 * - "Never synced" shown for null sync timestamps (italic text)
 * - 0 counts display correctly (fresh install edge case)
 * - Section has aria-labelledby="about-heading"
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../../hooks/useAppInfo", () => ({
  useAppInfo: vi.fn(),
}));

import { useAppInfo } from "../../../hooks/useAppInfo";
import { AboutSection } from "../AboutSection";
import type { UseAppInfoReturn } from "../../../hooks/useAppInfo";
import type { AppInfo } from "../../../api/settings";

const mockedUseAppInfo = vi.mocked(useAppInfo);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHookReturn(
  overrides: Partial<UseAppInfoReturn> = {}
): UseAppInfoReturn {
  return {
    appInfo: undefined,
    isLoading: false,
    error: null,
    ...overrides,
  };
}

function makeAppInfo(overrides: Partial<AppInfo> = {}): AppInfo {
  return {
    backend_version: "0.49.0",
    frontend_version: "0.18.0",
    database_stats: {
      videos: 1234,
      channels: 56,
      playlists: 12,
      transcripts: 987,
      corrections: 45,
      canonical_tags: 678,
    },
    sync_timestamps: {
      subscriptions: "2020-01-01T00:00:00Z",
      videos: "2020-01-02T00:00:00Z",
      transcripts: null,
      playlists: "2020-01-03T00:00:00Z",
      topics: null,
    },
    ...overrides,
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderComponent(hookReturn: Partial<UseAppInfoReturn> = {}) {
  mockedUseAppInfo.mockReturnValue(buildHookReturn(hookReturn));
  const queryClient = createQueryClient();
  render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(AboutSection)
    )
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AboutSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("shows loading skeleton with role=status when isLoading=true", () => {
    renderComponent({ isLoading: true });
    const skeleton = screen.getByRole("status", {
      name: "Loading application information",
    });
    expect(skeleton).toBeDefined();
  });

  it("does not show version information while loading", () => {
    renderComponent({ isLoading: true });
    expect(screen.queryByText(/Backend:/i)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error alert with the error message", () => {
    renderComponent({ error: new Error("App info unavailable") });
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("App info unavailable")).toBeDefined();
  });

  it("shows a Retry button in the error state", () => {
    renderComponent({ error: new Error("Timeout") });
    expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
  });

  it("shows the error heading for app info failure", () => {
    renderComponent({ error: new Error("Boom") });
    expect(
      screen.getByText(/Failed to load application information/i)
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Version display
  // -------------------------------------------------------------------------

  it("renders backend version in a dd element", () => {
    renderComponent({ appInfo: makeAppInfo({ backend_version: "1.0.0" }) });
    // Find dd for backend version
    const dd = screen.getByText("1.0.0");
    expect(dd.tagName.toLowerCase()).toBe("dd");
  });

  it("renders frontend version in a dd element", () => {
    renderComponent({ appInfo: makeAppInfo({ frontend_version: "2.0.0" }) });
    const dd = screen.getByText("2.0.0");
    expect(dd.tagName.toLowerCase()).toBe("dd");
  });

  it("renders 'Backend:' and 'Frontend:' dt labels", () => {
    renderComponent({ appInfo: makeAppInfo() });
    expect(screen.getByText("Backend:")).toBeDefined();
    expect(screen.getByText("Frontend:")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Database statistics
  // -------------------------------------------------------------------------

  it("shows all 6 database entity type labels", () => {
    renderComponent({ appInfo: makeAppInfo() });
    // "Videos" and "Transcripts" appear in both the stats grid and the sync
    // timestamps list, so use getAllByText and verify at least one match exists
    for (const label of [
      "Videos",
      "Channels",
      "Playlists",
      "Transcripts",
      "Corrections",
      "Canonical Tags",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("displays the Videos count", () => {
    renderComponent({
      appInfo: makeAppInfo({
        database_stats: {
          videos: 500,
          channels: 0,
          playlists: 0,
          transcripts: 0,
          corrections: 0,
          canonical_tags: 0,
        },
      }),
    });
    expect(screen.getByText("500")).toBeDefined();
  });

  it("displays 0 counts correctly for a fresh install", () => {
    renderComponent({
      appInfo: makeAppInfo({
        database_stats: {
          videos: 0,
          channels: 0,
          playlists: 0,
          transcripts: 0,
          corrections: 0,
          canonical_tags: 0,
        },
      }),
    });
    // All 6 zero values should be present in dd elements
    const zeros = screen
      .getAllByText("0")
      .filter((el) => el.tagName.toLowerCase() === "dd");
    expect(zeros.length).toBe(6);
  });

  // -------------------------------------------------------------------------
  // Sync timestamps
  // -------------------------------------------------------------------------

  it("renders sync timestamp labels: Subscriptions, Videos, Transcripts, Playlists, Topics", () => {
    renderComponent({ appInfo: makeAppInfo() });
    // "Videos" and "Transcripts" appear in both the stats grid and sync list;
    // use getAllByText and confirm at least one match
    for (const label of [
      "Subscriptions",
      "Videos",
      "Transcripts",
      "Playlists",
      "Topics",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("shows 'Never synced' italic text for null sync timestamps", () => {
    renderComponent({
      appInfo: makeAppInfo({
        sync_timestamps: {
          subscriptions: null,
          videos: null,
          transcripts: null,
          playlists: null,
          topics: null,
        },
      }),
    });
    const neverSyncedItems = screen.getAllByText("Never synced");
    // All 5 timestamps are null
    expect(neverSyncedItems.length).toBe(5);
  });

  it("renders a relative time element (time tag) for non-null timestamps", () => {
    renderComponent({
      appInfo: makeAppInfo({
        sync_timestamps: {
          subscriptions: "2020-01-01T00:00:00Z",
          videos: null,
          transcripts: null,
          playlists: null,
          topics: null,
        },
      }),
    });
    // The non-null timestamp renders as a <time> element
    const timeEl = document.querySelector("time");
    expect(timeEl).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  it("section has aria-labelledby pointing to about-heading", () => {
    renderComponent({ appInfo: makeAppInfo() });
    const section = document.querySelector("section[aria-labelledby='about-heading']");
    expect(section).not.toBeNull();
  });

  it("renders the About heading text", () => {
    renderComponent({ appInfo: makeAppInfo() });
    expect(screen.getByText("About")).toBeDefined();
  });

  it("renders 'Database Statistics' heading", () => {
    renderComponent({ appInfo: makeAppInfo() });
    expect(screen.getByText("Database Statistics")).toBeDefined();
  });

  it("renders 'Last Synced' heading", () => {
    renderComponent({ appInfo: makeAppInfo() });
    expect(screen.getByText("Last Synced")).toBeDefined();
  });
});
