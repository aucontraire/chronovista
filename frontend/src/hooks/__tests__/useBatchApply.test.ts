/**
 * Tests for useBatchApply mutation hook.
 *
 * Coverage:
 * - Calls POST /corrections/batch/apply with the correct request body
 * - Returns the unwrapped BatchApplyResult from the API envelope
 * - Invalidates all 6 query keys on success per the Feature 046 cache
 *   invalidation matrix
 * - Does NOT invalidate caches when the mutation fails
 * - Does not retry 4xx (client) errors
 * - Exposes the error when the mutation fails
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch, isApiError } from "../../api/config";
import { useBatchApply } from "../useBatchApply";
import type { BatchApplyRequest, BatchApplyResult } from "../../types/batchCorrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown) => {
    return (
      typeof err === "object" &&
      err !== null &&
      "status" in err
    );
  }),
}));

const mockedApiFetch = vi.mocked(apiFetch);
const mockedIsApiError = vi.mocked(isApiError);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeRequest(overrides: Partial<BatchApplyRequest> = {}): BatchApplyRequest {
  return {
    pattern: "teh",
    replacement: "the",
    segment_ids: [42, 99, 137],
    ...overrides,
  };
}

function makeResult(overrides: Partial<BatchApplyResult> = {}): BatchApplyResult {
  return {
    total_applied: 3,
    total_skipped: 0,
    total_failed: 0,
    failed_segment_ids: [],
    affected_video_ids: ["video-abc"],
    rebuild_triggered: true,
    ...overrides,
  };
}

function makeApiEnvelope(result: BatchApplyResult): { data: BatchApplyResult } {
  return { data: result };
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
// useBatchApply tests
// ---------------------------------------------------------------------------

describe("useBatchApply", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
    // Default: isApiError returns false unless overridden
    mockedIsApiError.mockReturnValue(false);
  });

  it("calls POST /corrections/batch/apply with the request body", async () => {
    const result = makeResult();
    mockedApiFetch.mockResolvedValueOnce(makeApiEnvelope(result));

    const request = makeRequest();
    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/apply",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      })
    );
  });

  it("returns the unwrapped BatchApplyResult on success", async () => {
    const result = makeResult({ total_applied: 5, total_skipped: 2 });
    mockedApiFetch.mockResolvedValueOnce(makeApiEnvelope(result));

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(hook.current.data?.total_applied).toBe(5);
    expect(hook.current.data?.total_skipped).toBe(2);
    expect(hook.current.data?.affected_video_ids).toEqual(["video-abc"]);
  });

  it("invalidates all 6 query keys on success", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeApiEnvelope(makeResult()));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0]
    );

    expect(invalidatedKeys).toContain("transcriptSegments");
    expect(invalidatedKeys).toContain("transcript");
    expect(invalidatedKeys).toContain("batch-list");
    expect(invalidatedKeys).toContain("corrections");
    expect(invalidatedKeys).toContain("diff-analysis");
    expect(invalidatedKeys).toContain("cross-segment-candidates");
    expect(invalidateSpy).toHaveBeenCalledTimes(6);

    invalidateSpy.mockRestore();
  });

  it("does NOT invalidate caches when the mutation fails", async () => {
    // Use a 4xx-shaped error so the hook's retry guard returns false immediately
    // (no retries), preventing the 1-second waitFor timeout.
    const clientError = Object.assign(new Error("Bad request"), { status: 400 });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValueOnce(clientError);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();

    invalidateSpy.mockRestore();
  });

  it("exposes the error object when the mutation fails", async () => {
    // Use a 4xx-shaped error so the hook's retry guard returns false immediately.
    const clientError = Object.assign(new Error("Network failure"), { status: 400 });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValueOnce(clientError);

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(hook.current.error).toBeTruthy();
    expect(hook.current.error?.message).toBe("Network failure");
  });

  it("does not retry 4xx client errors", async () => {
    const clientError = Object.assign(new Error("Validation error"), { status: 422 });
    // isApiError returns true for this error (has status property)
    mockedIsApiError.mockImplementation((err: unknown) => {
      return (
        typeof err === "object" &&
        err !== null &&
        "status" in err
      );
    });
    mockedApiFetch.mockRejectedValue(clientError);

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    // Only one attempt — no retries for 4xx
    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
  });

  it("passes optional fields (correction_type, correction_note, entity_id) in the request", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeApiEnvelope(makeResult()));

    const request = makeRequest({
      correction_type: "proper_noun",
      correction_note: "Fixing entity name capitalisation",
      entity_id: "entity-uuid-001",
      is_regex: false,
      case_insensitive: true,
    });

    const { result: hook } = renderHook(() => useBatchApply(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/apply",
      expect.objectContaining({
        body: JSON.stringify(request),
      })
    );
  });
});
