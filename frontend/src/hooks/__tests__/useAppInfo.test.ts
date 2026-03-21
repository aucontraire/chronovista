/**
 * Tests for useAppInfo hook.
 *
 * Coverage:
 * - Initial loading state while the app-info query is pending
 * - Successful fetch returns populated appInfo
 * - Error handling when the fetch fails
 * - staleTime is set (30 seconds) — verified via query options indirectly
 * - appInfo is undefined while loading and on error
 * - All AppInfo fields are accessible after a successful fetch
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../api/settings", () => ({
  fetchAppInfo: vi.fn(),
}));

import { fetchAppInfo } from "../../api/settings";
import { useAppInfo } from "../useAppInfo";
import type { AppInfo } from "../../api/settings";

const mockedFetchAppInfo = vi.mocked(fetchAppInfo);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAppInfoResponse(overrides: Partial<AppInfo> = {}): {
  data: AppInfo;
  pagination: null;
} {
  return {
    data: {
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
        subscriptions: "2024-06-01T10:00:00Z",
        videos: "2024-06-02T08:30:00Z",
        transcripts: null,
        playlists: "2024-05-28T15:45:00Z",
        topics: null,
      },
      ...overrides,
    },
    pagination: null,
  };
}

// ---------------------------------------------------------------------------
// Wrapper & QueryClient helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useAppInfo", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
    mockedFetchAppInfo.mockResolvedValue(makeAppInfoResponse());
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("returns isLoading=true and appInfo=undefined while fetching", () => {
    mockedFetchAppInfo.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.appInfo).toBeUndefined();
    expect(result.current.error).toBeNull();
  });

  it("returns isLoading=false after the query resolves", async () => {
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  // -------------------------------------------------------------------------
  // Successful data fetch
  // -------------------------------------------------------------------------

  it("populates appInfo with backend_version from the API response", async () => {
    mockedFetchAppInfo.mockResolvedValue(
      makeAppInfoResponse({ backend_version: "1.2.3" })
    );

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.appInfo?.backend_version).toBe("1.2.3");
  });

  it("populates appInfo with frontend_version", async () => {
    mockedFetchAppInfo.mockResolvedValue(
      makeAppInfoResponse({ frontend_version: "0.18.0" })
    );

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.appInfo?.frontend_version).toBe("0.18.0");
  });

  it("populates appInfo with all 6 database_stats fields", async () => {
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const stats = result.current.appInfo?.database_stats;
    expect(stats?.videos).toBe(1234);
    expect(stats?.channels).toBe(56);
    expect(stats?.playlists).toBe(12);
    expect(stats?.transcripts).toBe(987);
    expect(stats?.corrections).toBe(45);
    expect(stats?.canonical_tags).toBe(678);
  });

  it("populates appInfo.sync_timestamps with both ISO strings and null values", async () => {
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const timestamps = result.current.appInfo?.sync_timestamps;
    expect(timestamps?.subscriptions).toBe("2024-06-01T10:00:00Z");
    expect(timestamps?.transcripts).toBeNull();
    expect(timestamps?.topics).toBeNull();
  });

  it("returns error=null on a successful fetch", async () => {
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  it("returns error when the fetch fails", async () => {
    const fetchError = new Error("App info endpoint unavailable");
    mockedFetchAppInfo.mockRejectedValue(fetchError);

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("App info endpoint unavailable");
  });

  it("returns appInfo=undefined on error", async () => {
    mockedFetchAppInfo.mockRejectedValue(new Error("Server error"));

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.appInfo).toBeUndefined();
  });

  it("returns isLoading=false when query settles with an error", async () => {
    mockedFetchAppInfo.mockRejectedValue(new Error("500 Internal Server Error"));

    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // staleTime behavior
  // -------------------------------------------------------------------------

  it("uses the app-info query key ['app-info']", async () => {
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // The query data is in the cache under the 'app-info' key
    const cached = queryClient.getQueryData(["app-info"]);
    expect(cached).toBeDefined();
  });

  it("does not re-fetch immediately on a second render (staleTime = 30s)", async () => {
    const { result, rerender } = renderHook(() => useAppInfo(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const callCountAfterFirstFetch = mockedFetchAppInfo.mock.calls.length;

    rerender();

    // Should not have triggered another fetch within staleTime
    expect(mockedFetchAppInfo.mock.calls.length).toBe(callCountAfterFirstFetch);
  });
});
