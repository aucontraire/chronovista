/**
 * Tests for useBatchHistory and useRevertBatch hooks.
 *
 * Coverage:
 * - useBatchHistory: fetches first page, getNextPageParam returns undefined
 *   when has_more=false, returns next offset when has_more=true
 * - useRevertBatch: calls DELETE with correct URL, invalidates all 6 query
 *   keys on success
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch } from "../../api/config";
import { useBatchHistory, useRevertBatch } from "../useBatchHistory";
import type { BatchSummary } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown) => {
    return (
      typeof err === "object" &&
      err !== null &&
      "type" in err &&
      "message" in err
    );
  }),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeBatchSummary(overrides: Partial<BatchSummary> = {}): BatchSummary {
  return {
    batch_id: "batch-uuid-001",
    correction_count: 5,
    corrected_by_user_id: "user:batch",
    pattern: "colour",
    replacement: "color",
    batch_timestamp: "2025-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeBatchListResponse(
  data: BatchSummary[],
  pagination: {
    has_more: boolean;
    total: number;
    offset: number;
    limit: number;
  }
) {
  return { data, pagination };
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// ---------------------------------------------------------------------------
// useBatchHistory tests
// ---------------------------------------------------------------------------

describe("useBatchHistory", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("fetches the first page and returns batch data", async () => {
    const batch = makeBatchSummary();
    const response = makeBatchListResponse([batch], {
      has_more: false,
      total: 1,
      offset: 0,
      limit: 20,
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useBatchHistory(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const batches = result.current.data?.pages.flatMap((p) => p.data) ?? [];
    expect(batches).toHaveLength(1);
    expect(batches[0]?.batch_id).toBe("batch-uuid-001");
    expect(batches[0]?.pattern).toBe("colour");
  });

  it("calls apiFetch with correct URL including offset and limit", async () => {
    const response = makeBatchListResponse([], {
      has_more: false,
      total: 0,
      offset: 0,
      limit: 20,
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useBatchHistory(20), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/batches?offset=0&limit=20",
      expect.objectContaining({ externalSignal: expect.anything() })
    );
  });

  it("returns undefined from getNextPageParam when has_more is false", async () => {
    const response = makeBatchListResponse([makeBatchSummary()], {
      has_more: false,
      total: 1,
      offset: 0,
      limit: 20,
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useBatchHistory(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.hasNextPage).toBe(false);
  });

  it("returns next offset from getNextPageParam when has_more is true", async () => {
    const batches = Array.from({ length: 20 }, (_, i) =>
      makeBatchSummary({ batch_id: `batch-${i}`, pattern: `pattern-${i}` })
    );
    const response = makeBatchListResponse(batches, {
      has_more: true,
      total: 35,
      offset: 0,
      limit: 20,
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useBatchHistory(20), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.hasNextPage).toBe(true);
  });

  it("fetches the second page with offset=20 when fetchNextPage is called", async () => {
    // First page: 20 items, has_more=true
    const firstPageBatches = Array.from({ length: 20 }, (_, i) =>
      makeBatchSummary({ batch_id: `batch-p1-${i}` })
    );
    const firstResponse = makeBatchListResponse(firstPageBatches, {
      has_more: true,
      total: 25,
      offset: 0,
      limit: 20,
    });

    // Second page: 5 items, has_more=false
    const secondPageBatches = Array.from({ length: 5 }, (_, i) =>
      makeBatchSummary({ batch_id: `batch-p2-${i}` })
    );
    const secondResponse = makeBatchListResponse(secondPageBatches, {
      has_more: false,
      total: 25,
      offset: 20,
      limit: 20,
    });

    mockedApiFetch
      .mockResolvedValueOnce(firstResponse)
      .mockResolvedValueOnce(secondResponse);

    const { result } = renderHook(() => useBatchHistory(20), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.pages).toHaveLength(1);

    // Fetch next page
    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));

    // Second apiFetch call should use offset=20
    expect(mockedApiFetch).toHaveBeenNthCalledWith(
      2,
      "/corrections/batch/batches?offset=20&limit=20",
      expect.objectContaining({ externalSignal: expect.anything() })
    );

    // Both pages' data should be available
    const allBatches = result.current.data?.pages.flatMap((p) => p.data) ?? [];
    expect(allBatches).toHaveLength(25);
    expect(result.current.hasNextPage).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// useRevertBatch tests
// ---------------------------------------------------------------------------

describe("useRevertBatch", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls DELETE with the correct batch ID URL", async () => {
    mockedApiFetch.mockResolvedValueOnce({
      data: { reverted_count: 5, skipped_count: 0 },
    });

    const { result } = renderHook(() => useRevertBatch(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate("batch-uuid-abc");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/batch-uuid-abc",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("returns the reverted_count and skipped_count from the API response", async () => {
    mockedApiFetch.mockResolvedValueOnce({
      data: { reverted_count: 12, skipped_count: 3 },
    });

    const { result } = renderHook(() => useRevertBatch(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate("batch-uuid-xyz");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.reverted_count).toBe(12);
    expect(result.current.data?.skipped_count).toBe(3);
  });

  it("invalidates all 6 query keys on success", async () => {
    mockedApiFetch.mockResolvedValueOnce({
      data: { reverted_count: 1, skipped_count: 0 },
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRevertBatch(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate("batch-uuid-123");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0]
    );

    expect(invalidatedKeys).toContain("batch-list");
    expect(invalidatedKeys).toContain("corrections");
    expect(invalidatedKeys).toContain("transcriptSegments");
    expect(invalidatedKeys).toContain("transcript");
    expect(invalidatedKeys).toContain("diff-analysis");
    expect(invalidatedKeys).toContain("cross-segment-candidates");
    expect(invalidateSpy).toHaveBeenCalledTimes(6);

    invalidateSpy.mockRestore();
  });

  it("does NOT invalidate caches when the mutation fails", async () => {
    mockedApiFetch.mockRejectedValueOnce(new Error("Not found"));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRevertBatch(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate("batch-uuid-bad");
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();

    invalidateSpy.mockRestore();
  });

  it("exposes the error when the mutation fails", async () => {
    const error = new Error("Server error");
    mockedApiFetch.mockRejectedValueOnce(error);

    const { result } = renderHook(() => useRevertBatch(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate("batch-uuid-fail");
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });
});