/**
 * Tests for useMergePreview mutation hook (Feature 056).
 *
 * Coverage:
 * - Calls POST /canonical-tags/merge/preview with the correct request body
 * - Returns the unwrapped MergePreview from the API envelope
 * - Does not retry 4xx (client) errors
 * - Exposes the error when the mutation fails
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch, isApiError } from "../../api/config";
import { useMergePreview } from "../useMergePreview";
import type { MergePreview, MergePreviewRequest } from "../../types/canonical-tags";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown) => {
    return typeof err === "object" && err !== null && "status" in err;
  }),
}));

const mockedApiFetch = vi.mocked(apiFetch);
const mockedIsApiError = vi.mocked(isApiError);

function makeRequest(
  overrides: Partial<MergePreviewRequest> = {}
): MergePreviewRequest {
  return {
    source_normalized_forms: ["professor hannah fry"],
    target_normalized_form: "hannah fry",
    ...overrides,
  };
}

function makePreview(overrides: Partial<MergePreview> = {}): MergePreview {
  return {
    source_tags: ["Professor Hannah Fry"],
    target_tag: "Hannah Fry",
    resulting_alias_count: 5,
    resulting_video_count: 42,
    source_alias_count: 2,
    source_video_count: 12,
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

describe("useMergePreview", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
    mockedIsApiError.mockReturnValue(false);
  });

  it("calls POST /canonical-tags/merge/preview with the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makePreview() });

    const request = makeRequest();
    const { result: hook } = renderHook(() => useMergePreview(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/canonical-tags/merge/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      })
    );
  });

  it("returns the unwrapped MergePreview on success, computed over the union (no overcounting)", async () => {
    const preview = makePreview({
      resulting_video_count: 100,
      source_video_count: 30,
    });
    mockedApiFetch.mockResolvedValueOnce({ data: preview });

    const { result: hook } = renderHook(() => useMergePreview(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(hook.current.data?.resulting_video_count).toBe(100);
    expect(hook.current.data?.resulting_alias_count).toBe(5);
  });

  it("supports multiple source tags in a single preview request", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: makePreview() });

    const request = makeRequest({
      source_normalized_forms: ["professor hannah fry", "dr hannah fry", "prof fry"],
    });

    const { result: hook } = renderHook(() => useMergePreview(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(request);
    });

    await waitFor(() => expect(hook.current.isSuccess).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/canonical-tags/merge/preview",
      expect.objectContaining({ body: JSON.stringify(request) })
    );
  });

  it("does not retry 4xx client errors (e.g. self-merge validation)", async () => {
    const clientError = Object.assign(new Error("Cannot merge a tag into itself"), {
      status: 400,
    });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValue(clientError);

    const { result: hook } = renderHook(() => useMergePreview(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest());
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
    expect(hook.current.error?.message).toBe("Cannot merge a tag into itself");
  });

  it("exposes a 404 error when a source tag is missing", async () => {
    const notFoundError = Object.assign(new Error("Tag not found: ghost-tag"), {
      status: 404,
    });
    mockedIsApiError.mockReturnValue(true);
    mockedApiFetch.mockRejectedValue(notFoundError);

    const { result: hook } = renderHook(() => useMergePreview(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      hook.current.mutate(makeRequest({ source_normalized_forms: ["ghost-tag"] }));
    });

    await waitFor(() => expect(hook.current.isError).toBe(true));

    expect(hook.current.error?.message).toBe("Tag not found: ghost-tag");
  });
});
