/**
 * Tests for useDiffAnalysis hook.
 *
 * Coverage:
 * - Fetches data with no params (default case)
 * - Fetches data with entityName param (server-side filter)
 * - Query key includes params object (cache segmentation — different params → separate fetches)
 * - Returns data on success
 * - Exposes error on fetch failure
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { fetchDiffAnalysis } from "../../api/batchCorrections";
import { useDiffAnalysis } from "../useDiffAnalysis";
import type { DiffErrorPattern } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/batchCorrections", () => ({
  fetchDiffAnalysis: vi.fn(),
}));

const mockedFetchDiffAnalysis = vi.mocked(fetchDiffAnalysis);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeDiffErrorPattern(
  overrides: Partial<DiffErrorPattern> = {}
): DiffErrorPattern {
  return {
    error_token: "barak",
    canonical_form: "Barack",
    frequency: 12,
    remaining_matches: 8,
    entity_id: null,
    entity_name: null,
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

describe("useDiffAnalysis", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("fetches diff analysis data with no params and returns the array", async () => {
    const pattern = makeDiffErrorPattern();
    mockedFetchDiffAnalysis.mockResolvedValueOnce([pattern]);

    const { result } = renderHook(() => useDiffAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.error_token).toBe("barak");
    expect(result.current.data?.[0]?.canonical_form).toBe("Barack");
    expect(result.current.data?.[0]?.frequency).toBe(12);
  });

  it("passes params to fetchDiffAnalysis when provided", async () => {
    mockedFetchDiffAnalysis.mockResolvedValueOnce([]);

    const params = { entityName: "Obama", minOccurrences: 5, limit: 50 };

    const { result } = renderHook(() => useDiffAnalysis(params), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedFetchDiffAnalysis).toHaveBeenCalledWith(
      params,
      expect.anything() // AbortSignal
    );
  });

  it("issues separate fetches for different params objects (cache segmentation)", async () => {
    mockedFetchDiffAnalysis.mockResolvedValue([]);

    const paramsA = { entityName: "Obama" };
    const paramsB = { entityName: "Clinton" };

    // Each hook uses its own QueryClient wrapper to avoid cross-test cache hits.
    const qcA = createQueryClient();
    const qcB = createQueryClient();

    const { result: resultA } = renderHook(() => useDiffAnalysis(paramsA), {
      wrapper: createWrapper(qcA),
    });

    await waitFor(() => expect(resultA.current.isSuccess).toBe(true));

    const { result: resultB } = renderHook(() => useDiffAnalysis(paramsB), {
      wrapper: createWrapper(qcB),
    });

    await waitFor(() => expect(resultB.current.isSuccess).toBe(true));

    // fetchDiffAnalysis should have been called twice — once per unique params.
    expect(mockedFetchDiffAnalysis).toHaveBeenCalledTimes(2);
    expect(mockedFetchDiffAnalysis).toHaveBeenCalledWith(paramsA, expect.anything());
    expect(mockedFetchDiffAnalysis).toHaveBeenCalledWith(paramsB, expect.anything());
  });

  it("calls fetchDiffAnalysis with undefined when no params are passed", async () => {
    mockedFetchDiffAnalysis.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useDiffAnalysis(undefined), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedFetchDiffAnalysis).toHaveBeenCalledTimes(1);
    expect(mockedFetchDiffAnalysis).toHaveBeenCalledWith(
      undefined,
      expect.anything()
    );
  });

  it("returns an empty array when the API returns no patterns", async () => {
    mockedFetchDiffAnalysis.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useDiffAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });

  it("returns multiple patterns when the API returns multiple results", async () => {
    const patterns = [
      makeDiffErrorPattern({ error_token: "barak", canonical_form: "Barack" }),
      makeDiffErrorPattern({
        error_token: "hussain",
        canonical_form: "Hussein",
        frequency: 7,
      }),
    ];
    mockedFetchDiffAnalysis.mockResolvedValueOnce(patterns);

    const { result } = renderHook(() => useDiffAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(2);
  });

  it("exposes isError and error when fetchDiffAnalysis rejects", async () => {
    const err = new Error("Network failure");
    mockedFetchDiffAnalysis.mockRejectedValueOnce(err);

    const { result } = renderHook(() => useDiffAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeTruthy();
    expect(result.current.data).toBeUndefined();
  });

  it("returns a pattern with entity_id and entity_name when entity is linked", async () => {
    const pattern = makeDiffErrorPattern({
      error_token: "obamma",
      canonical_form: "Obama",
      entity_id: "entity-uuid-123",
      entity_name: "Barack Obama",
    });
    mockedFetchDiffAnalysis.mockResolvedValueOnce([pattern]);

    const { result } = renderHook(() => useDiffAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.[0]?.entity_id).toBe("entity-uuid-123");
    expect(result.current.data?.[0]?.entity_name).toBe("Barack Obama");
  });
});
