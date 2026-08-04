/**
 * useVideos — entity intersection parameters (Feature 062).
 *
 * The centrepiece is the **cache-key** test. React Query caches on the query
 * key alone, so a filter that reaches the request URL but is missing from the
 * key produces a result that looks right on first load and then never updates:
 * changing the filter serves the previous answer from cache, and only a hard
 * reload appears to "fix" it. That shipped once here — the entity params were
 * appended to the URL but omitted from the key — and it is invisible to any
 * test that checks a single request in isolation.
 *
 * @module tests/hooks/useVideos.entity
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useVideos } from "../../hooks/useVideos";
import type { VideoListResponse } from "../../types/video";
import * as apiConfig from "../../api/config";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

const mockResponse: VideoListResponse = {
  data: [],
  pagination: { total: 0, limit: 25, offset: 0, has_more: false },
};

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** Last URL passed to apiFetch. */
function lastUrl(): string {
  const calls = vi.mocked(apiConfig.apiFetch).mock.calls;
  return String(calls[calls.length - 1]?.[0] ?? "");
}

describe("useVideos — entity filter parameters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiConfig.apiFetch).mockResolvedValue(mockResponse);
  });

  describe("request construction", () => {
    it("sends required entities as repeated entity_id keys", async () => {
      const queryClient = newClient();
      renderHook(() => useVideos({ entityIds: ["e1", "e2"] }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
      const params = new URLSearchParams(lastUrl().split("?")[1]);
      expect(params.getAll("entity_id")).toEqual(["e1", "e2"]);
    });

    it("sends excluded entities as repeated exclude_entity_id keys", async () => {
      const queryClient = newClient();
      renderHook(() => useVideos({ excludedEntityIds: ["x1", "x2"] }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
      const params = new URLSearchParams(lastUrl().split("?")[1]);
      expect(params.getAll("exclude_entity_id")).toEqual(["x1", "x2"]);
    });

    it("sends min_evidence only when a scope is requested", async () => {
      const withScope = newClient();
      renderHook(() => useVideos({ entityIds: ["e1"], minEvidence: "transcript" }), {
        wrapper: createWrapper(withScope),
      });
      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
      expect(new URLSearchParams(lastUrl().split("?")[1]).get("min_evidence")).toBe(
        "transcript"
      );

      vi.clearAllMocks();
      const noScope = newClient();
      renderHook(() => useVideos({ entityIds: ["e1"] }), {
        wrapper: createWrapper(noScope),
      });
      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
      expect(new URLSearchParams(lastUrl().split("?")[1]).has("min_evidence")).toBe(
        false
      );
    });

    it("omits entity params entirely when no entity filter is active", async () => {
      const queryClient = newClient();
      renderHook(() => useVideos({}), { wrapper: createWrapper(queryClient) });

      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
      const params = new URLSearchParams(lastUrl().split("?")[1]);
      expect(params.has("entity_id")).toBe(false);
      expect(params.has("exclude_entity_id")).toBe(false);
    });
  });

  describe("cache key covers every entity parameter", () => {
    /**
     * Each case changes ONE entity parameter on a shared QueryClient and
     * asserts a second request is issued. If the parameter is missing from the
     * query key, React Query answers from cache and `apiFetch` is never called
     * again — the exact stale-until-reload bug this guards.
     */
    it.each([
      ["required entities", { entityIds: ["a"] }, { entityIds: ["a", "b"] }],
      [
        "excluded entities",
        { excludedEntityIds: ["a"] },
        { excludedEntityIds: ["a", "b"] },
      ],
      [
        "evidence scope",
        { entityIds: ["a"] },
        { entityIds: ["a"], minEvidence: "transcript" as const },
      ],
    ])("refetches when %s change", async (_label, first, second) => {
      const queryClient = newClient();
      const wrapper = createWrapper(queryClient);

      const { rerender } = renderHook((props: Parameters<typeof useVideos>[0]) => useVideos(props), {
        wrapper,
        initialProps: first,
      });
      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1));

      rerender(second);
      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2));

      // And the second request actually carries the new filter, so the refetch
      // is meaningful rather than an identical repeat.
      expect(lastUrl()).not.toBe(
        String(vi.mocked(apiConfig.apiFetch).mock.calls[0]?.[0] ?? "")
      );
    });

    it("does NOT refetch when nothing relevant changed", async () => {
      // The counterweight: a key containing something volatile would refetch
      // constantly and make the test above pass for the wrong reason.
      const queryClient = newClient();
      const wrapper = createWrapper(queryClient);

      const { rerender } = renderHook(
        (props: Parameters<typeof useVideos>[0]) => useVideos(props),
        { wrapper, initialProps: { entityIds: ["a"] } }
      );
      await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1));

      rerender({ entityIds: ["a"] });
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);
    });
  });
});
