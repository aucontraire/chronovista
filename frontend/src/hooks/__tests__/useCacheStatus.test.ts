/**
 * Tests for useCacheStatus hook.
 *
 * Coverage:
 * - Initial loading state while the cache-status query is pending
 * - Successful cache status fetch populates cacheStatus
 * - purgeCache() triggers the DELETE mutation and sets isPurging
 * - Successful purge invalidates the cache-status query key
 * - Error handling from the fetch query
 * - purgeResult is populated after a successful purge
 * - cacheStatus is undefined while loading
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock at module level so all consumers see the mock
vi.mock("../../api/settings", () => ({
  fetchCacheStatus: vi.fn(),
  purgeCache: vi.fn(),
}));

import { fetchCacheStatus, purgeCache } from "../../api/settings";
import {
  useCacheStatus,
  CACHE_STATUS_KEY,
} from "../useCacheStatus";
import type {
  CacheStatus,
  CachePurgeResult,
} from "../../api/settings";

const mockedFetchCacheStatus = vi.mocked(fetchCacheStatus);
const mockedPurgeCache = vi.mocked(purgeCache);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeCacheStatusResponse(
  overrides: Partial<CacheStatus> = {}
): { data: CacheStatus; pagination: null } {
  return {
    data: {
      channel_count: 10,
      video_count: 132,
      total_count: 142,
      total_size_bytes: 24_500_000,
      total_size_display: "23.4 MB",
      oldest_file: "2024-01-01T00:00:00Z",
      newest_file: "2024-06-01T00:00:00Z",
      ...overrides,
    },
    pagination: null,
  };
}

function makePurgeResponse(
  overrides: Partial<CachePurgeResult> = {}
): { data: CachePurgeResult; pagination: null } {
  return {
    data: {
      purged: true,
      message: "Cache cleared successfully",
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

describe("useCacheStatus", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();

    // Default: fetch resolves with a populated cache status
    mockedFetchCacheStatus.mockResolvedValue(makeCacheStatusResponse());
    mockedPurgeCache.mockResolvedValue(makePurgeResponse());
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("returns isLoading=true and cacheStatus=undefined while fetching", () => {
    mockedFetchCacheStatus.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.cacheStatus).toBeUndefined();
  });

  it("returns isLoading=false once the query resolves", async () => {
    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  // -------------------------------------------------------------------------
  // Successful data fetch
  // -------------------------------------------------------------------------

  it("populates cacheStatus with data from the API response", async () => {
    mockedFetchCacheStatus.mockResolvedValue(
      makeCacheStatusResponse({ total_count: 142, total_size_display: "23.4 MB" })
    );

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.cacheStatus).toBeDefined();
    expect(result.current.cacheStatus?.total_count).toBe(142);
    expect(result.current.cacheStatus?.total_size_display).toBe("23.4 MB");
  });

  it("returns all CacheStatus fields correctly", async () => {
    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const status = result.current.cacheStatus!;
    expect(status.channel_count).toBe(10);
    expect(status.video_count).toBe(132);
    expect(status.total_count).toBe(142);
    expect(status.total_size_bytes).toBe(24_500_000);
    expect(typeof status.total_size_display).toBe("string");
  });

  // -------------------------------------------------------------------------
  // purgeCache mutation
  // -------------------------------------------------------------------------

  it("isPurging transitions to true while the DELETE is in flight", async () => {
    let resolveDelete!: (value: unknown) => void;
    const pendingDelete = new Promise((resolve) => {
      resolveDelete = resolve;
    });

    mockedPurgeCache.mockReturnValue(
      pendingDelete as ReturnType<typeof purgeCache>
    );

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isPurging).toBe(false);

    act(() => {
      result.current.purgeCache();
    });

    await waitFor(() => expect(result.current.isPurging).toBe(true));

    // Clean up
    resolveDelete(makePurgeResponse());
    await waitFor(() => expect(result.current.isPurging).toBe(false));
  });

  it("purgeCache() calls the purgeCache API function", async () => {
    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.purgeCache();
    });

    await waitFor(() => expect(mockedPurgeCache).toHaveBeenCalledTimes(1));
  });

  it("successful purge invalidates the CACHE_STATUS_KEY query", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.purgeCache();
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: CACHE_STATUS_KEY })
      )
    );

    invalidateSpy.mockRestore();
  });

  it("purgeResult is populated after a successful purge", async () => {
    mockedPurgeCache.mockResolvedValue(
      makePurgeResponse({ purged: true, message: "All 142 files deleted" })
    );

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.purgeResult).toBeUndefined();

    act(() => {
      result.current.purgeCache();
    });

    await waitFor(() => expect(result.current.purgeResult).toBeDefined());
    expect(result.current.purgeResult?.purged).toBe(true);
    expect(result.current.purgeResult?.message).toBe("All 142 files deleted");
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  it("returns error when the cache-status fetch fails", async () => {
    const fetchError = new Error("Cache endpoint unavailable");
    mockedFetchCacheStatus.mockRejectedValue(fetchError);

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("Cache endpoint unavailable");
    expect(result.current.cacheStatus).toBeUndefined();
  });

  it("returns error=null and no cacheStatus when still loading", () => {
    mockedFetchCacheStatus.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.error).toBeNull();
    expect(result.current.cacheStatus).toBeUndefined();
  });

  it("returns isPurging=false initially", async () => {
    const { result } = renderHook(() => useCacheStatus(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isPurging).toBe(false);
  });
});
