/**
 * Tests for useUndoMerge mutation hook (Feature 056).
 *
 * Coverage:
 * - Calls POST /canonical-tags/operations/{operationId}/undo
 * - Returns the unwrapped UndoResult from the API envelope
 * - Invalidates canonical-tags and canonical-tag-detail caches on success
 * - Does NOT invalidate caches when the mutation fails
 * - Does not retry 4xx errors (404 not found, 409 already undone)
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch, isApiError } from "../../api/config";
import { useUndoMerge } from "../useUndoMerge";
import type { UndoResult } from "../../types/canonical-tags";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown) => {
    return typeof err === "object" && err !== null && "status" in err;
  }),
}));

const mockedApiFetch = vi.mocked(apiFetch);
const mockedIsApiError = vi.mocked(isApiError);

const OPERATION_ID = "op-123e4567-e89b-12d3-a456-426614174000";

function makeUndoResult(overrides: Partial<UndoResult> = {}): UndoResult {
  return {
    operation_type: "merge",
    operation_id: OPERATION_ID,
    details: "Restored 1 source tag and 2 aliases to Professor Hannah Fry",
    ...overrides,
  };
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
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

describe("useUndoMerge", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
    mockedIsApiError.mockReturnValue(false);
  });

  it("calls POST /canonical-tags/operations/{operationId}/undo", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeUndoResult() });

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(OPERATION_ID);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/canonical-tags/operations/${OPERATION_ID}/undo`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("URL-encodes the operation ID", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeUndoResult() });

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate("op with spaces");
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/canonical-tags/operations/op%20with%20spaces/undo",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("returns the unwrapped UndoResult on success", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeUndoResult() });

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(OPERATION_ID);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(hook.current.data?.operation_type).toBe("merge");
    expect(hook.current.data?.operation_id).toBe(OPERATION_ID);
  });

  it("invalidates canonical-tags and canonical-tag-detail caches on success", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeUndoResult() });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(OPERATION_ID);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0]
    );

    expect(invalidatedKeys).toContain("canonical-tags");
    expect(invalidatedKeys).toContain("canonical-tag-detail");

    invalidateSpy.mockRestore();
  });

  it("does NOT invalidate caches when the undo fails", async () => {
    const alreadyUndoneError = Object.assign(
      new Error("This operation has already been undone"),
      { status: 409 }
    );
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValueOnce(alreadyUndoneError);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(OPERATION_ID);
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(hook.current.error?.message).toBe(
      "This operation has already been undone"
    );

    invalidateSpy.mockRestore();
  });

  it("does not retry 4xx errors (404 not found)", async () => {
    const notFoundError = Object.assign(new Error("Operation not found"), {
      status: 404,
    });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValue(notFoundError);

    const { result: hook } = renderHook(() => useUndoMerge(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate("unknown-op-id");
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
  });
});
