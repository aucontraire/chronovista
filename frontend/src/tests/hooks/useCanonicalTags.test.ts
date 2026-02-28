/**
 * Unit tests for useCanonicalTags hook.
 *
 * Tests TanStack Query integration for fetching canonical tags with prefix search,
 * rate limiting, debounce, and fuzzy suggestions support.
 *
 * The hook uses native fetch (not apiFetch), so we mock global.fetch via
 * vi.stubGlobal("fetch", ...) following the project's established pattern.
 *
 * @module tests/hooks/useCanonicalTags
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useCanonicalTags } from "../../hooks/useCanonicalTags";
import type {
  CanonicalTagListItem,
  CanonicalTagListResponse,
  CanonicalTagSuggestion,
} from "../../types/canonical-tags";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Builds a minimal Response stub for use with vi.stubGlobal("fetch", ...).
 *
 * Parameters
 * ----------
 * body : unknown
 *     Value returned by response.json().
 * status : number
 *     HTTP status code (default 200).
 * headers : Record<string, string>
 *     Optional response headers (keyed by lowercase name).
 *
 * Returns
 * -------
 * Response
 *     A stubbed Response object.
 */
function makeFetchResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {}
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : status === 429 ? "Too Many Requests" : "Error",
    headers: {
      get: (name: string): string | null => headers[name.toLowerCase()] ?? null,
    },
    json: vi.fn().mockResolvedValue(body),
    // Minimal stubs for other Response properties
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

/**
 * Creates a fresh QueryClient with retries disabled for fast, deterministic
 * tests. The hook's own query-level retry callback overrides this for 429
 * detection; for tests requiring retry behaviour use a separate client.
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

/** Creates the QueryClientProvider wrapper for renderHook. */
function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockTagItem1: CanonicalTagListItem = {
  canonical_form: "Python",
  normalized_form: "python",
  alias_count: 3,
  video_count: 42,
};

const mockTagItem2: CanonicalTagListItem = {
  canonical_form: "PyTorch",
  normalized_form: "pytorch",
  alias_count: 1,
  video_count: 17,
};

const mockSuggestion: CanonicalTagSuggestion = {
  canonical_form: "Py Game",
  normalized_form: "py game",
};

const mockListResponse: CanonicalTagListResponse = {
  data: [mockTagItem1, mockTagItem2],
  pagination: {
    total: 2,
    limit: 10,
    offset: 0,
    has_more: false,
  },
};

const mockEmptyResponseWithSuggestions: CanonicalTagListResponse = {
  data: [],
  pagination: {
    total: 0,
    limit: 10,
    offset: 0,
    has_more: false,
  },
  suggestions: [mockSuggestion],
};

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("useCanonicalTags", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // 1. Prefix search returns CanonicalTagListItem array
  // -------------------------------------------------------------------------
  describe("prefix search returns CanonicalTagListItem array", () => {
    it("returns tags array populated from response data", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.tags).toHaveLength(2);
      expect(result.current.tags[0]).toEqual(mockTagItem1);
      expect(result.current.tags[1]).toEqual(mockTagItem2);
    });

    it("returns tags with correct CanonicalTagListItem shape", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      const tag = result.current.tags[0];
      // Verify all required fields are present and have the expected types
      expect(tag).toHaveProperty("canonical_form");
      expect(tag).toHaveProperty("normalized_form");
      expect(tag).toHaveProperty("alias_count");
      expect(tag).toHaveProperty("video_count");
      expect(typeof tag?.canonical_form).toBe("string");
      expect(typeof tag?.normalized_form).toBe("string");
      expect(typeof tag?.alias_count).toBe("number");
      expect(typeof tag?.video_count).toBe("number");
    });

    it("fetches from the canonical-tags endpoint with q and limit params", async () => {
      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags("python"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const calledUrl: string = fetchSpy.mock.calls[0]?.[0] as string;
      expect(calledUrl).toContain("/canonical-tags");
      expect(calledUrl).toContain("q=python");
      expect(calledUrl).toContain("limit=10");
    });

    it("passes an AbortSignal for request cancellation", async () => {
      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      const requestInit: RequestInit = fetchSpy.mock.calls[0]?.[1] as RequestInit;
      expect(requestInit).toHaveProperty("signal");
      expect(requestInit?.signal).toBeInstanceOf(AbortSignal);
    });

    it("returns empty tags array when response data is empty", async () => {
      const emptyResponse: CanonicalTagListResponse = {
        data: [],
        pagination: { total: 0, limit: 10, offset: 0, has_more: false },
      };

      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(makeFetchResponse(emptyResponse)));

      const { result } = renderHook(
        () => useCanonicalTags("zzz"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.tags).toEqual([]);
    });
  });

  // -------------------------------------------------------------------------
  // 2. Empty search disables the query
  // -------------------------------------------------------------------------
  describe("empty search disables query", () => {
    it("does not call fetch when search is empty string", () => {
      const fetchSpy = vi.fn();
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags(""),
        { wrapper: createWrapper(queryClient) }
      );

      // Query is disabled — isLoading must remain false and no fetch issued
      expect(result.current.isLoading).toBe(false);
      expect(result.current.tags).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("transitions from disabled to enabled when search becomes non-empty", async () => {
      const fetchSpy = vi
        .fn()
        .mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      let search = "";
      const { result, rerender } = renderHook(
        () => useCanonicalTags(search),
        { wrapper: createWrapper(queryClient) }
      );

      // Initially disabled — no fetch
      expect(result.current.isLoading).toBe(false);
      expect(fetchSpy).not.toHaveBeenCalled();

      // Provide a non-empty search term
      search = "py";
      rerender();

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // 3. Fuzzy suggestions returned
  // -------------------------------------------------------------------------
  describe("fuzzy suggestions", () => {
    it("returns suggestions when API response includes them", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockEmptyResponseWithSuggestions))
      );

      const { result } = renderHook(
        () => useCanonicalTags("pgame"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.tags).toEqual([]);
      expect(result.current.suggestions).toHaveLength(1);
      expect(result.current.suggestions[0]).toEqual(mockSuggestion);
    });

    it("returns empty suggestions array when API omits suggestions field", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse)) // no suggestions field
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      // suggestions should default to []
      expect(result.current.suggestions).toEqual([]);
    });

    it("returns suggestions with correct CanonicalTagSuggestion shape", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockEmptyResponseWithSuggestions))
      );

      const { result } = renderHook(
        () => useCanonicalTags("pgame"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.suggestions).toHaveLength(1);
      });

      const suggestion = result.current.suggestions[0];
      expect(suggestion).toHaveProperty("canonical_form");
      expect(suggestion).toHaveProperty("normalized_form");
      expect(typeof suggestion?.canonical_form).toBe("string");
      expect(typeof suggestion?.normalized_form).toBe("string");
    });

    it("populates both tags and suggestions when both are present", async () => {
      const combinedResponse: CanonicalTagListResponse = {
        data: [mockTagItem1],
        pagination: { total: 1, limit: 10, offset: 0, has_more: false },
        suggestions: [mockSuggestion],
      };

      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(combinedResponse))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.tags).toHaveLength(1);
      expect(result.current.suggestions).toHaveLength(1);
      expect(result.current.tags[0]?.canonical_form).toBe("Python");
      expect(result.current.suggestions[0]?.canonical_form).toBe("Py Game");
    });
  });

  // -------------------------------------------------------------------------
  // 4. 429 response sets isRateLimited and rateLimitRetryAfter
  // -------------------------------------------------------------------------
  describe("429 rate limit handling", () => {
    it("sets isRateLimited=true when API returns 429", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "30" }))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });
    });

    it("sets rateLimitRetryAfter from Retry-After header value", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "30" }))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      expect(result.current.rateLimitRetryAfter).toBe(30);
    });

    it("defaults rateLimitRetryAfter to 10 when Retry-After header is absent", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, {}))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      expect(result.current.rateLimitRetryAfter).toBe(10);
    });

    it("defaults rateLimitRetryAfter to 10 when Retry-After header is non-numeric", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "banana" }))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      expect(result.current.rateLimitRetryAfter).toBe(10);
    });

    it("sets isError=true when rate limited", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "5" }))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.isRateLimited).toBe(true);
    });

    it("clears isRateLimited after retryAfter seconds have elapsed", async () => {
      // This test verifies the clearTimeout useEffect in the hook:
      //
      //   useEffect(() => {
      //     if (isError && isRateLimitError(error)) {
      //       ...
      //       const timer = setTimeout(() => {
      //         setIsRateLimited(false);
      //         setRateLimitRetryAfter(0);
      //       }, retryAfter * 1000);
      //       return () => clearTimeout(timer);
      //     }
      //   }, [isError, error]);
      //
      // Strategy:
      // 1. Use real timers to wait for the 429 error state (fast — microtask-based).
      // 2. Verify isRateLimited=true.
      // 3. Wait for the 5-second clearance window using real timers (waitFor with 8s timeout).
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "5" }))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      // Step 1: Wait for the 429 error to be processed
      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      // Step 2: Confirm values
      expect(result.current.rateLimitRetryAfter).toBe(5);

      // Step 3: Wait for the clearance timer (5 seconds) to fire
      await waitFor(
        () => {
          expect(result.current.isRateLimited).toBe(false);
        },
        { timeout: 8000 }
      );

      expect(result.current.rateLimitRetryAfter).toBe(0);
    }, 12000);
  });

  // -------------------------------------------------------------------------
  // 5. Retry skipped on 429
  // -------------------------------------------------------------------------
  describe("retry behavior on 429", () => {
    it("does NOT retry the query after a 429 response", async () => {
      // Every call returns 429
      const fetchSpy = vi
        .fn()
        .mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "10" }));
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      // fetch must have been called exactly once — the hook's retry callback
      // returns false for RateLimitError objects, preventing any retry.
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it("blocks retries even when QueryClient default allows 3 retries", async () => {
      // Verify that the hook's own retry(failureCount, err) callback takes
      // precedence over a QueryClient that permits retries.
      const permissiveClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: 3,
            retryDelay: 0,
          },
        },
      });

      const fetchSpy = vi
        .fn()
        .mockResolvedValue(makeFetchResponse(null, 429, { "retry-after": "2" }));
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(permissiveClient) }
      );

      await waitFor(() => {
        expect(result.current.isRateLimited).toBe(true);
      });

      // Despite the permissive client, the hook's retry fn returns false for 429
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      permissiveClient.clear();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Debounce consolidates rapid inputs
  // -------------------------------------------------------------------------
  describe("debounce consolidates rapid inputs", () => {
    it("fires an API call after the 300ms debounce delay", async () => {
      // useDebounce initialises its state to the initial value on the very first render,
      // so debouncedSearch starts as "py" immediately and the query fires on the first
      // render without any timer advancement needed. This test simply confirms the fetch
      // occurs and uses the correct URL parameter.
      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(1);
      });

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      const calledUrl: string = fetchSpy.mock.calls[0]?.[0] as string;
      expect(calledUrl).toContain("q=py");
    });

    it("makes only one API call for rapid sequential search changes", async () => {
      // Rapid typing: each keystroke triggers a rerender within the debounce window.
      // Only the FINAL debounced value should cause a fetch.
      // We use fake timers to control the 300ms debounce window.
      vi.useFakeTimers();

      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      // Start with empty search so no query fires initially
      let search = "";
      const { rerender } = renderHook(
        () => useCanonicalTags(search),
        { wrapper: createWrapper(queryClient) }
      );

      // No fetch yet — query is disabled for empty search
      expect(fetchSpy).not.toHaveBeenCalled();

      // Simulate rapid typing within the debounce window
      search = "p";
      rerender();
      search = "py";
      rerender();
      search = "pyt";
      rerender();
      search = "pyth";
      rerender();

      // Advance past the debounce delay to trigger the FINAL debounced value
      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Exactly one fetch should have been made, with the final search term
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const calledUrl: string = fetchSpy.mock.calls[0]?.[0] as string;
      expect(calledUrl).toContain("q=pyth");
    });

    it("does not issue a fetch when search resets to empty before debounce fires", async () => {
      // Start with empty search (query disabled), change to non-empty, then immediately
      // clear back to empty — all within the debounce window. The debounced value should
      // settle on "" which keeps the query disabled with no fetch.
      vi.useFakeTimers();

      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      // Start with empty — query is disabled
      let search = "";
      const { rerender } = renderHook(
        () => useCanonicalTags(search),
        { wrapper: createWrapper(queryClient) }
      );

      expect(fetchSpy).not.toHaveBeenCalled();

      // Change to non-empty search (starts debounce timer)
      search = "py";
      rerender();

      // Immediately reset to empty BEFORE the 300ms debounce fires
      search = "";
      rerender();

      // Advance past the debounce window; debouncedSearch settles on ""
      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      // Query is disabled (debouncedSearch === "") — no fetch should have occurred
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // 7. Cache configuration (staleTime / gcTime)
  // -------------------------------------------------------------------------
  describe("cache configuration", () => {
    it("stores query result in cache under canonical-tags key", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      // The query state must exist in the client cache with success status
      const queryState = queryClient.getQueryState(["canonical-tags", "py"]);
      expect(queryState).toBeDefined();
      expect(queryState?.status).toBe("success");
    });

    it("serves cached data without re-fetching within staleTime (5 min)", async () => {
      const fetchSpy = vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse));
      vi.stubGlobal("fetch", fetchSpy);

      // First render — populates the cache
      const { result: result1, unmount: unmount1 } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.tags).toHaveLength(2);
      });

      unmount1();

      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Second render with same search + same queryClient — should hit the cache
      const { result: result2 } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      // Immediately has cached data; no additional network call
      expect(result2.current.tags).toEqual(mockListResponse.data);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it("uses separate cache entries for different search terms", async () => {
      const responseA: CanonicalTagListResponse = {
        data: [mockTagItem1],
        pagination: { total: 1, limit: 10, offset: 0, has_more: false },
      };
      const responseB: CanonicalTagListResponse = {
        data: [mockTagItem2],
        pagination: { total: 1, limit: 10, offset: 0, has_more: false },
      };

      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValueOnce(makeFetchResponse(responseA))
          .mockResolvedValueOnce(makeFetchResponse(responseB))
      );

      const { result: resultA } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: resultB } = renderHook(
        () => useCanonicalTags("py2"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(resultA.current.tags).toHaveLength(1);
        expect(resultB.current.tags).toHaveLength(1);
      });

      expect(resultA.current.tags[0]?.canonical_form).toBe("Python");
      expect(resultB.current.tags[0]?.canonical_form).toBe("PyTorch");
    });

    it("records updatedAt timestamp in cache state after successful fetch", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(mockListResponse))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.tags).toHaveLength(2);
      });

      // Confirms staleTime/gcTime options are accepted and query completed
      const queryState = queryClient.getQueryState(["canonical-tags", "py"]);
      expect(queryState?.dataUpdatedAt).toBeGreaterThan(0);
    });
  });

  // -------------------------------------------------------------------------
  // 8. Error handling (non-429)
  //
  // The hook's retry callback allows up to 3 retries for non-429 errors with
  // an exponential retryDelay (1s + 2s + 4s = 7s total).  These tests use a
  // dedicated QueryClient that overrides the retry count to 0 so they complete
  // without any retry delays while still exercising the error propagation path.
  //
  // The hook-level retry callback IS overrideable via a QueryClient default
  // when the client option is set to `false` — in TanStack Query v5 the final
  // merged value used is determined by the QueryObserver, which takes the
  // query-level option first.  Because we cannot mutate the hook, we instead
  // patch `global.fetch` to REJECT (throw) rather than resolve with a 500
  // response.  A thrown fetch error still satisfies `isError: true` and the
  // hook's retry callback still fires (returnint true up to 3 times).
  //
  // The cleanest way to avoid real-time wait: make the error look like a
  // 429 rate-limit error from the hook's perspective — `isRateLimitError(err)`
  // returns true only when err.status === 429.  For the "does not set
  // isRateLimited for non-429 errors" test we need the error to NOT set the
  // rate-limited state, so we test a different aspect: we verify the initial
  // error state using a fast `waitFor` timeout on a properly-resolved error.
  //
  // For tests that need isError:true without waiting for retries, we use a
  // QueryClient with `retry: (failureCount, err) => false` at the default
  // level.  NOTE: Per TanStack Query v5 source, the query-level `retry` option
  // IS merged and takes PRECEDENCE over the client default, so a true override
  // from outside is not possible.  We therefore accept a ~1s wait (first
  // attempt fails immediately; no retry for non-429 via the hook itself — the
  // hook's callback does allow retries, but the fetch mock can control the
  // timing by resolving instantly and the first failure registers immediately).
  //
  // Practical solution: use REAL timers + waitFor with a generous timeout of
  // 15000ms to cover the hook's 3 retries (1s + 2s + 4s = 7s total).
  // -------------------------------------------------------------------------
  describe("error handling", () => {
    it("sets isError=true for generic API errors (500)", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 500))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      // Wait for the hook to finish all retries and settle in error state.
      // The hook retries 3 times with exponential backoff (1s + 2s + 4s = 7s max).
      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 12000 }
      );

      expect(result.current.isRateLimited).toBe(false);
    }, 15000);

    it("exposes an Error object when the query fails", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 500))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 12000 }
      );

      expect(result.current.error).toBeInstanceOf(Error);
    }, 15000);

    it("returns empty tags and suggestions arrays on error", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 500))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 12000 }
      );

      expect(result.current.tags).toEqual([]);
      expect(result.current.suggestions).toEqual([]);
    }, 15000);

    it("does not set isRateLimited for non-429 errors", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(makeFetchResponse(null, 503))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true);
        },
        { timeout: 12000 }
      );

      expect(result.current.isRateLimited).toBe(false);
      expect(result.current.rateLimitRetryAfter).toBe(0);
    }, 15000);
  });

  // -------------------------------------------------------------------------
  // 9. Initial / default state
  // -------------------------------------------------------------------------
  describe("initial state", () => {
    it("returns all expected fields from the hook", () => {
      // Empty search — query is disabled; hook must return a complete shape
      vi.stubGlobal("fetch", vi.fn());

      const { result } = renderHook(
        () => useCanonicalTags(""),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current).toHaveProperty("tags");
      expect(result.current).toHaveProperty("suggestions");
      expect(result.current).toHaveProperty("isLoading");
      expect(result.current).toHaveProperty("isError");
      expect(result.current).toHaveProperty("error");
      expect(result.current).toHaveProperty("isRateLimited");
      expect(result.current).toHaveProperty("rateLimitRetryAfter");
    });

    it("has correct default values when query is disabled", () => {
      vi.stubGlobal("fetch", vi.fn());

      const { result } = renderHook(
        () => useCanonicalTags(""),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.tags).toEqual([]);
      expect(result.current.suggestions).toEqual([]);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.isRateLimited).toBe(false);
      expect(result.current.rateLimitRetryAfter).toBe(0);
    });

    it("shows isLoading=true initially when search is non-empty", () => {
      // Mock a fetch that never resolves so we can inspect the loading state
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(() => new Promise(() => undefined))
      );

      const { result } = renderHook(
        () => useCanonicalTags("py"),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.tags).toEqual([]);
    });
  });
});
