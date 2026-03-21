/**
 * Tests for CacheSection component.
 *
 * Coverage:
 * - Loading skeleton shown when isLoading=true (role="status" with aria-label)
 * - Error state shows alert with error message and Retry button
 * - Empty cache shows "No cached images" text
 * - Populated cache shows count and size text
 * - "Clear Cache" button only appears when images exist
 * - Clicking "Clear Cache" shows confirmation alertdialog
 * - Confirmation dialog contains warning text about re-downloading
 * - Confirming calls purgeCache()
 * - Canceling hides the confirmation dialog
 * - Escape key closes the confirmation dialog
 * - aria-live region exists for purge completion announcements
 * - Singular "image" when count is 1
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock the hook — component is only responsible for rendering
vi.mock("../../../hooks/useCacheStatus", () => ({
  useCacheStatus: vi.fn(),
}));

import { useCacheStatus } from "../../../hooks/useCacheStatus";
import { CacheSection } from "../CacheSection";
import type { UseCacheStatusReturn } from "../../../hooks/useCacheStatus";

const mockedUseCacheStatus = vi.mocked(useCacheStatus);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHookReturn(
  overrides: Partial<UseCacheStatusReturn> = {}
): UseCacheStatusReturn {
  return {
    cacheStatus: undefined,
    isLoading: false,
    error: null,
    purgeCache: vi.fn(),
    isPurging: false,
    purgeResult: undefined,
    ...overrides,
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderComponent(hookReturn: Partial<UseCacheStatusReturn> = {}) {
  mockedUseCacheStatus.mockReturnValue(buildHookReturn(hookReturn));
  const queryClient = createQueryClient();
  render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(CacheSection)
    )
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CacheSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("shows loading skeleton with role=status and aria-label when isLoading=true", () => {
    renderComponent({ isLoading: true });
    const skeleton = screen.getByRole("status", {
      name: "Loading cache statistics",
    });
    expect(skeleton).toBeDefined();
  });

  it("does not show statistics text while loading", () => {
    renderComponent({ isLoading: true });
    expect(screen.queryByText(/cached images/i)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error alert with the error message", () => {
    renderComponent({ error: new Error("Cache endpoint failed") });
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Cache endpoint failed")).toBeDefined();
  });

  it("shows a Retry button in the error state", () => {
    renderComponent({ error: new Error("Oops") });
    expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
  });

  it("shows the error heading text", () => {
    renderComponent({ error: new Error("Something broke") });
    expect(
      screen.getByText(/Failed to load cache statistics/i)
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Empty cache
  // -------------------------------------------------------------------------

  it("shows 'No cached images' when total_count is 0", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 0,
        video_count: 0,
        total_count: 0,
        total_size_bytes: 0,
        total_size_display: "0 B",
        oldest_file: null,
        newest_file: null,
      },
    });
    expect(screen.getByText("No cached images")).toBeDefined();
  });

  it("does not show Clear Cache button when cache is empty", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 0,
        video_count: 0,
        total_count: 0,
        total_size_bytes: 0,
        total_size_display: "0 B",
        oldest_file: null,
        newest_file: null,
      },
    });
    expect(
      screen.queryByRole("button", { name: /clear/i })
    ).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Populated cache
  // -------------------------------------------------------------------------

  it("shows count and size text for a populated cache", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 10,
        video_count: 132,
        total_count: 142,
        total_size_bytes: 24_500_000,
        total_size_display: "23.4 MB",
        oldest_file: "2024-01-01T00:00:00Z",
        newest_file: "2024-06-01T00:00:00Z",
      },
    });
    expect(screen.getByText(/142 images, 23.4 MB/)).toBeDefined();
  });

  it("uses singular 'image' when total_count is 1", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 1,
        video_count: 0,
        total_count: 1,
        total_size_bytes: 12_000,
        total_size_display: "11.7 KB",
        oldest_file: "2024-01-01T00:00:00Z",
        newest_file: "2024-01-01T00:00:00Z",
      },
    });
    expect(screen.getByText(/1 image, 11\.7 KB/)).toBeDefined();
  });

  it("shows 'Clear Cache' button when images exist", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    expect(
      screen.getByRole("button", { name: /clear all cached images/i })
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Confirmation dialog
  // -------------------------------------------------------------------------

  it("clicking Clear Cache opens an alertdialog", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /clear all cached images/i })
    );
    expect(screen.getByRole("alertdialog")).toBeDefined();
  });

  it("confirmation dialog has warning text about re-downloading", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /clear all cached images/i })
    );
    expect(
      screen.getByText(/Cached images will need to be re-downloaded/i)
    ).toBeDefined();
  });

  it("clicking 'Yes, clear cache' calls purgeCache()", () => {
    const purgeCache = vi.fn();
    renderComponent({
      purgeCache,
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /clear all cached images/i })
    );
    fireEvent.click(screen.getByText(/Yes, clear cache/i));
    expect(purgeCache).toHaveBeenCalledTimes(1);
  });

  it("clicking Cancel hides the confirmation dialog", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /clear all cached images/i })
    );
    expect(screen.getByRole("alertdialog")).toBeDefined();
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("pressing Escape closes the confirmation dialog", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 5,
        video_count: 20,
        total_count: 25,
        total_size_bytes: 500_000,
        total_size_display: "488 KB",
        oldest_file: null,
        newest_file: null,
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /clear all cached images/i })
    );
    const dialog = screen.getByRole("alertdialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // aria-live region
  // -------------------------------------------------------------------------

  it("renders an aria-live polite region for purge completion announcements", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 0,
        video_count: 0,
        total_count: 0,
        total_size_bytes: 0,
        total_size_display: "0 B",
        oldest_file: null,
        newest_file: null,
      },
    });
    // The sr-only div has role="status" and aria-live="polite"
    const liveRegions = document.querySelectorAll('[aria-live="polite"]');
    expect(liveRegions.length).toBeGreaterThan(0);
  });

  // -------------------------------------------------------------------------
  // Section heading
  // -------------------------------------------------------------------------

  it("renders the section heading 'Cache'", () => {
    renderComponent({
      cacheStatus: {
        channel_count: 0,
        video_count: 0,
        total_count: 0,
        total_size_bytes: 0,
        total_size_display: "0 B",
        oldest_file: null,
        newest_file: null,
      },
    });
    expect(screen.getByText("Cache")).toBeDefined();
  });
});
