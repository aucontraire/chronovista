/**
 * Tests for useMergeTags mutation hook (Feature 056).
 *
 * Coverage:
 * - Calls POST /canonical-tags/merge with the correct request body
 * - Returns the unwrapped MergeResult from the API envelope, including entity_hint
 * - Invalidates canonical-tags and canonical-tag-detail caches on success
 * - Does NOT invalidate caches when the mutation fails
 * - Does not retry 4xx (client) errors
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch, isApiError } from "../../api/config";
import { useMergeTags } from "../useMergeTags";
import type { MergeRequest, MergeResult } from "../../types/canonical-tags";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown) => {
    return typeof err === "object" && err !== null && "status" in err;
  }),
}));

const mockedApiFetch = vi.mocked(apiFetch);
const mockedIsApiError = vi.mocked(isApiError);

function makeRequest(overrides: Partial<MergeRequest> = {}): MergeRequest {
  return {
    source_normalized_forms: ["professor hannah fry"],
    target_normalized_form: "hannah fry",
    ...overrides,
  };
}

function makeResult(overrides: Partial<MergeResult> = {}): MergeResult {
  return {
    source_tags: ["Professor Hannah Fry"],
    target_tag: "Hannah Fry",
    aliases_moved: 2,
    new_alias_count: 5,
    new_video_count: 42,
    operation_id: "op-123e4567-e89b-12d3-a456-426614174000",
    entity_hint: null,
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

describe("useMergeTags", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
    mockedIsApiError.mockReturnValue(false);
  });

  it("calls POST /canonical-tags/merge with the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeResult() });

    const request = makeRequest();
    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/canonical-tags/merge",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      })
    );
  });

  it("forwards the optional reason field when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeResult() });

    const request = makeRequest({ reason: "Same person, title variant" });
    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/canonical-tags/merge",
      expect.objectContaining({ body: JSON.stringify(request) })
    );
  });

  it("returns the unwrapped MergeResult on success, including operation_id", async () => {
    const result = makeResult({ aliases_moved: 3, new_video_count: 100 });
    mockedApiFetch.mockResolvedValueOnce({ data: result });

    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(hook.current.data?.aliases_moved).toBe(3);
    expect(hook.current.data?.new_video_count).toBe(100);
    expect(hook.current.data?.operation_id).toBe(result.operation_id);
  });

  it("surfaces entity_hint when the source tag is linked to a named entity (FR-016)", async () => {
    const result = makeResult({ entity_hint: "Linked to entity: Hannah Fry (person)" });
    mockedApiFetch.mockResolvedValueOnce({ data: result });

    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(hook.current.data?.entity_hint).toBe(
      "Linked to entity: Hannah Fry (person)"
    );
  });

  it("invalidates canonical-tags and canonical-tag-detail caches on success", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makeResult() });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0]
    );

    expect(invalidatedKeys).toContain("canonical-tags");
    expect(invalidatedKeys).toContain("canonical-tag-detail");

    invalidateSpy.mockRestore();
  });

  it("does NOT invalidate caches when the mutation fails", async () => {
    const clientError = Object.assign(new Error("Cannot merge a tag into itself"), {
      status: 400,
    });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValueOnce(clientError);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();

    invalidateSpy.mockRestore();
  });

  it("does not retry 4xx client errors (e.g. 409 conflict)", async () => {
    const conflictError = Object.assign(new Error("Concurrent merge detected"), {
      status: 409,
    });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValue(conflictError);

    const { result: hook } = renderHook(() => useMergeTags(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
  });
});
