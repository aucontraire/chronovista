/**
 * Tests for useCrossSegmentCandidates hook.
 *
 * Coverage:
 * - Fetches candidates without params (bare query key)
 * - Fetches candidates with params included in the query key
 * - Returns data array on success
 * - Passes AbortSignal through to fetchCrossSegmentCandidates
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { fetchCrossSegmentCandidates } from "../../api/batchCorrections";
import { useCrossSegmentCandidates } from "../useCrossSegmentCandidates";
import type { CrossSegmentCandidate } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/batchCorrections", () => ({
  fetchCrossSegmentCandidates: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchCrossSegmentCandidates);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeCrossSegmentCandidate(
  overrides: Partial<CrossSegmentCandidate> = {}
): CrossSegmentCandidate {
  return {
    segment_n_id: 1,
    segment_n_text: "the quick brown",
    segment_n1_id: 2,
    segment_n1_text: "fox jumps over",
    proposed_correction: "The Quick Brown",
    source_pattern: "the quick brown",
    confidence: 0.85,
    is_partially_corrected: false,
    video_id: "video-uuid-001",
    discovery_source: "correction_pattern",
    ...overrides,
  };
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
    },
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useCrossSegmentCandidates", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("fetches candidates without params and returns data on success", async () => {
    const candidate = makeCrossSegmentCandidate();
    mockedFetch.mockResolvedValueOnce([candidate]);

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.segment_n_id).toBe(1);
    expect(result.current.data?.[0]?.proposed_correction).toBe(
      "The Quick Brown"
    );
  });

  it("uses query key that includes params when params are provided", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const params = { minCorrections: 3, entityName: "TestEntity" };
    const { result } = renderHook(() => useCrossSegmentCandidates(params), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The query should have been called (params are part of the cache key)
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch).toHaveBeenCalledWith(params, expect.any(AbortSignal));
  });

  it("uses separate cache entries for different params", async () => {
    mockedFetch
      .mockResolvedValueOnce([makeCrossSegmentCandidate({ segment_n_id: 10 })])
      .mockResolvedValueOnce([makeCrossSegmentCandidate({ segment_n_id: 20 })]);

    const { result: result1 } = renderHook(
      () => useCrossSegmentCandidates({ minCorrections: 1 }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result1.current.isSuccess).toBe(true));
    expect(result1.current.data?.[0]?.segment_n_id).toBe(10);

    const { result: result2 } = renderHook(
      () => useCrossSegmentCandidates({ minCorrections: 5 }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result2.current.isSuccess).toBe(true));
    expect(result2.current.data?.[0]?.segment_n_id).toBe(20);
  });

  it("returns an empty array when no candidates exist", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });

  it("returns multiple candidates with correct fields", async () => {
    const candidates = [
      makeCrossSegmentCandidate({
        segment_n_id: 1,
        confidence: 0.9,
        is_partially_corrected: false,
      }),
      makeCrossSegmentCandidate({
        segment_n_id: 2,
        confidence: 0.7,
        is_partially_corrected: true,
      }),
    ];
    mockedFetch.mockResolvedValueOnce(candidates);

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[1]?.is_partially_corrected).toBe(true);
  });

  it("exposes isLoading=true while the fetch is in progress", () => {
    // Never resolves during this test
    mockedFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("exposes isError=true and data=undefined when fetch rejects", async () => {
    mockedFetch.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.data).toBeUndefined();
  });

  it("passes AbortSignal to fetchCrossSegmentCandidates", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useCrossSegmentCandidates(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const callArgs = mockedFetch.mock.calls[0];
    expect(callArgs?.[1]).toBeInstanceOf(AbortSignal);
  });
});
