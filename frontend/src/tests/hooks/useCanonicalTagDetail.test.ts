/**
 * Unit tests for useCanonicalTagDetail hook.
 *
 * The hook uses the native fetch API (not apiFetch) to call the canonical-tag
 * detail endpoint. Tests mock global.fetch via vi.stubGlobal and wrap
 * components in QueryClientProvider.
 *
 * Error-path tests use vi.useFakeTimers() to advance through TanStack
 * Query's retry-delay scheduler without waiting for real wall-clock time.
 *
 * @module tests/hooks/useCanonicalTagDetail
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useCanonicalTagDetail } from "../../hooks/useCanonicalTagDetail";
import type {
  CanonicalTagDetail,
  CanonicalTagDetailResponse,
} from "../../types/canonical-tags";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal fetch Response stub. */
function makeFetchResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText:
      status === 200 ? "OK" : status === 404 ? "Not Found" : "Error",
    json: vi.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: "basic" as ResponseType,
    url: "",
    body: null,
    bodyUsed: false,
    clone: vi.fn(),
    text: vi.fn(),
    arrayBuffer: vi.fn(),
    blob: vi.fn(),
    formData: vi.fn(),
  } as unknown as Response;
}

// ---------------------------------------------------------------------------
// QueryClient factory
// ---------------------------------------------------------------------------

/**
 * Creates a fresh QueryClient with retries disabled so successful-path tests
 * resolve predictably without extra async ticks.
 */
function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

/** Creates a wrapper component that provides TanStack Query context. */
function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockDetail: CanonicalTagDetail = {
  canonical_form: "JavaScript",
  normalized_form: "javascript",
  alias_count: 3,
  video_count: 42,
  top_aliases: [
    { raw_form: "javascript", occurrence_count: 30 },
    { raw_form: "JavaScript", occurrence_count: 10 },
    { raw_form: "js", occurrence_count: 2 },
  ],
  created_at: "2024-01-15T10:00:00Z",
  updated_at: "2024-06-01T08:00:00Z",
};

const mockDetailResponse: CanonicalTagDetailResponse = { data: mockDetail };

// ===========================================================================
// useCanonicalTagDetail
// ===========================================================================

describe("useCanonicalTagDetail", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  // -------------------------------------------------------------------------
  // 1. Fetches detail by normalized_form
  // -------------------------------------------------------------------------
  describe("successful data fetching", () => {
    it("returns populated data when the API responds with a canonical tag detail", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(queryClient) }
      );

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeNull();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockDetail);
      expect(result.current.isError).toBe(false);
    });

    it("calls fetch with the correct URL for the given normalizedForm", async () => {
      const fetchSpy = vi
        .fn()
        .mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200));
      vi.stubGlobal("fetch", fetchSpy);

      renderHook(() => useCanonicalTagDetail("javascript"), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      const calledUrl: string = fetchSpy.mock.calls[0]?.[0] as string;
      expect(calledUrl).toContain("/canonical-tags/javascript");
      expect(calledUrl).toContain("alias_limit=10");
    });

    it("URL-encodes special characters in normalizedForm", async () => {
      const fetchSpy = vi
        .fn()
        .mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200));
      vi.stubGlobal("fetch", fetchSpy);

      renderHook(() => useCanonicalTagDetail("c++"), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      const calledUrl: string = fetchSpy.mock.calls[0]?.[0] as string;
      // encodeURIComponent("c++") === "c%2B%2B"
      expect(calledUrl).toContain("c%2B%2B");
    });

    it("caches the result under the correct query key", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Data should be accessible in the cache under the expected key
      const cached = queryClient.getQueryData<CanonicalTagDetail | null>([
        "canonical-tag-detail",
        "javascript",
      ]);
      expect(cached).toEqual(mockDetail);
    });
  });

  // -------------------------------------------------------------------------
  // 2. Handles 404 gracefully
  // -------------------------------------------------------------------------
  describe("404 handling", () => {
    it("returns null data and isError=false when the API responds with 404", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce(makeFetchResponse(null, 404))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("nonexistent-tag"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // 404 is treated as "not found", not as an error
      expect(result.current.data).toBeNull();
      expect(result.current.isError).toBe(false);
    });

    it("stores null in the cache for a 404 response", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce(makeFetchResponse(null, 404))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("nonexistent-tag"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const cached = queryClient.getQueryData([
        "canonical-tag-detail",
        "nonexistent-tag",
      ]);
      expect(cached).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 3. Disabled when normalizedForm is empty
  // -------------------------------------------------------------------------
  describe("query disabled state", () => {
    it("does not call fetch when normalizedForm is an empty string", () => {
      const fetchSpy = vi.fn();
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(() => useCanonicalTagDetail(""), {
        wrapper: createWrapper(queryClient),
      });

      // Query is disabled — no loading, no data, no fetch call
      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeNull();
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("starts fetching once normalizedForm becomes non-empty", async () => {
      const fetchSpy = vi
        .fn()
        .mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200));
      vi.stubGlobal("fetch", fetchSpy);

      let normalizedForm = "";
      const { result, rerender } = renderHook(
        () => useCanonicalTagDetail(normalizedForm),
        { wrapper: createWrapper(queryClient) }
      );

      // Disabled initially
      expect(result.current.isLoading).toBe(false);
      expect(fetchSpy).not.toHaveBeenCalled();

      // Enable by setting a non-empty value
      normalizedForm = "javascript";
      rerender();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(result.current.data).toEqual(mockDetail);
    });
  });

  // -------------------------------------------------------------------------
  // 4. Cache configuration
  // -------------------------------------------------------------------------
  describe("cache configuration", () => {
    it("stores query state after a successful fetch (staleTime/gcTime configured)", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // A defined query state confirms the result is in the cache
      const queryState = queryClient.getQueryState([
        "canonical-tag-detail",
        "javascript",
      ]);
      expect(queryState).toBeDefined();
      expect(queryState?.status).toBe("success");
    });

    it("serves cached data on re-render without making a second fetch call", async () => {
      const fetchSpy = vi
        .fn()
        .mockResolvedValueOnce(makeFetchResponse(mockDetailResponse, 200));
      vi.stubGlobal("fetch", fetchSpy);

      // First render — populates cache
      const { result: result1 } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
      });

      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Second render reusing the same QueryClient — should use cached data
      const { result: result2 } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockDetail);
      // staleTime = 5 min, so no second fetch should occur
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // 5. Non-404 error handling
  //
  // useCanonicalTagDetail has a custom `retry` function that retries up to 3
  // times for non-404 errors.  The default TanStack Query retry delay is
  // exponential but caps at 30 000ms.  We use a custom QueryClient that sets
  // retryDelay: 0 at the client level; TanStack Query uses the minimum of the
  // query-level and client-level delays only when both are numeric (not
  // functions).  Because the hook does NOT define a retryDelay function,
  // the client's retryDelay: 0 takes effect, making all retries immediate.
  // We then extend the waitFor timeout to give 3 rapid retries time to settle.
  // -------------------------------------------------------------------------
  describe("error handling for non-404 responses", () => {
    it("sets isError=true when the API responds with a 500 status", async () => {
      // Build a client where retryDelay is 0 so the hook's 3 retries fire
      // back-to-back without real delays.
      const fastRetryClient = new QueryClient({
        defaultOptions: { queries: { retryDelay: 0 } },
      });

      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 500))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(fastRetryClient) }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 10000 }
      );

      expect(result.current.data).toBeNull();
      fastRetryClient.clear();
    }, 15000);

    it("sets isError=true on a network failure (fetch rejects)", async () => {
      const fastRetryClient = new QueryClient({
        defaultOptions: { queries: { retryDelay: 0 } },
      });

      vi.stubGlobal(
        "fetch",
        vi.fn().mockRejectedValue(new TypeError("Network request failed"))
      );

      const { result } = renderHook(
        () => useCanonicalTagDetail("javascript"),
        { wrapper: createWrapper(fastRetryClient) }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 10000 }
      );

      expect(result.current.data).toBeNull();
      fastRetryClient.clear();
    }, 15000);
  });
});
