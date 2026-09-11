/**
 * Tests for useWikidataCandidates in hooks/useEntityMentions.ts.
 *
 * Coverage:
 * - Lazy: the lookup never fires until `search()` is called
 * - `search()` fetches the first page (offset 0, default limit 7)
 * - `showMore()` fetches the next page and appends it to `candidates`
 * - `canShowMore` goes false once a page comes back shorter than `limit`
 *   (the backend's end-of-results signal), and while a page fetch is in
 *   flight
 * - `unavailable` reflects the most recently fetched page
 * - `resolveByQid()` resolves a single QID independently of the paged search
 *   and never rejects for a "not found" or "unavailable" result
 * - `reset()` clears both the paged list and any QID-resolve state
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import {
  fetchWikidataCandidates,
  fetchWikidataCandidateByQid,
} from "../../api/entityMentions";
import { useWikidataCandidates } from "../useEntityMentions";
import type { WikidataCandidate } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  fetchWikidataCandidates: vi.fn(),
  fetchWikidataCandidateByQid: vi.fn(),
  // Other exports imported transitively by useEntityMentions.ts — no-op stubs.
  fetchVideoEntities: vi.fn(),
  fetchEntityVideos: vi.fn(),
  fetchEntities: vi.fn(),
  createManualAssociation: vi.fn(),
  deleteManualAssociation: vi.fn(),
  classifyTag: vi.fn(),
  checkEntityDuplicate: vi.fn(),
  createEntity: vi.fn(),
  updateEntity: vi.fn(),
  scanEntity: vi.fn(),
  scanVideoEntities: vi.fn(),
  getScanJob: vi.fn(),
}));

const mockedFetchWikidataCandidates = vi.mocked(fetchWikidataCandidates);
const mockedFetchWikidataCandidateByQid = vi.mocked(fetchWikidataCandidateByQid);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function makeCandidate(overrides: Partial<WikidataCandidate> = {}): WikidataCandidate {
  return {
    qid: "Q000009",
    label: "Placeholder Nine",
    description: "A placeholder entity used for testing",
    instance_of: ["Q5"],
    statement_count: 10,
    sitelink_count: 1,
    is_stub: false,
    type_matches: true,
    ...overrides,
  };
}

/** Builds a page of `count` distinct candidates, qids offset by `start`. */
function makePage(count: number, start = 0): WikidataCandidate[] {
  return Array.from({ length: count }, (_, i) =>
    makeCandidate({ qid: `Q${String(start + i + 1).padStart(6, "0")}`, label: `Placeholder ${start + i + 1}` })
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useWikidataCandidates — lazy search", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("does not call fetchWikidataCandidates until search() is invoked", () => {
    renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    expect(mockedFetchWikidataCandidates).not.toHaveBeenCalled();
  });

  it("fetches the first page at offset 0 with the default limit (7) once search() is called", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());

    await waitFor(() => expect(result.current.hasSearched).toBe(true));
    await waitFor(() => expect(result.current.candidates).toHaveLength(3));

    expect(mockedFetchWikidataCandidates).toHaveBeenCalledWith(
      "Placeholder",
      "person",
      7,
      expect.anything(),
      0
    );
  });

  it("respects a caller-supplied limit", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(2), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person", 3), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());

    await waitFor(() => expect(result.current.candidates).toHaveLength(2));

    expect(mockedFetchWikidataCandidates).toHaveBeenCalledWith(
      "Placeholder",
      "person",
      3,
      expect.anything(),
      0
    );
  });
});

describe("useWikidataCandidates — Show more pagination", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("canShowMore is true after a full first page, and showMore() appends the second page", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3, 0), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person", 3), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());
    await waitFor(() => expect(result.current.candidates).toHaveLength(3));
    expect(result.current.canShowMore).toBe(true);

    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3, 3), unavailable: false });
    act(() => result.current.showMore());

    await waitFor(() => expect(result.current.candidates).toHaveLength(6));
    expect(mockedFetchWikidataCandidates).toHaveBeenLastCalledWith(
      "Placeholder",
      "person",
      3,
      expect.anything(),
      3
    );
    // All six candidates present, first page's then second page's, in order.
    expect(result.current.candidates.map((c) => c.qid)).toEqual([
      "Q000001",
      "Q000002",
      "Q000003",
      "Q000004",
      "Q000005",
      "Q000006",
    ]);
  });

  it("canShowMore goes false once a page comes back shorter than limit", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3, 0), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person", 3), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());
    await waitFor(() => expect(result.current.candidates).toHaveLength(3));

    // Second page shorter than limit — no more results.
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(1, 3), unavailable: false });
    act(() => result.current.showMore());

    await waitFor(() => expect(result.current.candidates).toHaveLength(4));
    expect(result.current.canShowMore).toBe(false);
  });

  it("canShowMore is false while a page fetch is in flight", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3, 0), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person", 3), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());
    await waitFor(() => expect(result.current.candidates).toHaveLength(3));

    let resolveSecondPage: (() => void) | undefined;
    mockedFetchWikidataCandidates.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecondPage = () => resolve({ candidates: makePage(3, 3), unavailable: false });
        })
    );

    act(() => result.current.showMore());

    await waitFor(() => expect(result.current.isFetchingMore).toBe(true));
    expect(result.current.canShowMore).toBe(false);

    resolveSecondPage?.();
    await waitFor(() => expect(result.current.isFetchingMore).toBe(false));
  });

  it("reflects the unavailable flag from the most recently fetched page", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: [], unavailable: true });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());

    await waitFor(() => expect(result.current.hasSearched).toBe(true));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.unavailable).toBe(true);
    expect(result.current.candidates).toHaveLength(0);
  });
});

describe("useWikidataCandidates — resolveByQid", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("resolves to the candidate on a successful lookup, independent of any paged search", async () => {
    const candidate = makeCandidate({ qid: "Q42", label: "Placeholder Universal" });
    mockedFetchWikidataCandidateByQid.mockResolvedValueOnce({ candidate, unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    expect(mockedFetchWikidataCandidates).not.toHaveBeenCalled();

    let resolved: Awaited<ReturnType<typeof result.current.resolveByQid>> | undefined;
    await act(async () => {
      resolved = await result.current.resolveByQid("Q42");
    });

    expect(resolved).toEqual({ candidate, unavailable: false });
    expect(mockedFetchWikidataCandidateByQid).toHaveBeenCalledWith("Q42", "person");
    // The paged search state is untouched by a QID resolve.
    expect(result.current.hasSearched).toBe(false);
    expect(result.current.candidates).toHaveLength(0);
  });

  it("resolves to candidate: null, unavailable: false for an unknown QID (never rejects)", async () => {
    mockedFetchWikidataCandidateByQid.mockResolvedValueOnce({ candidate: null, unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    let resolved: Awaited<ReturnType<typeof result.current.resolveByQid>> | undefined;
    await act(async () => {
      resolved = await result.current.resolveByQid("Q999999999");
    });

    expect(resolved).toEqual({ candidate: null, unavailable: false });
  });

  it("resolves to candidate: null, unavailable: true for a soft lookup failure", async () => {
    mockedFetchWikidataCandidateByQid.mockResolvedValueOnce({ candidate: null, unavailable: true });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    let resolved: Awaited<ReturnType<typeof result.current.resolveByQid>> | undefined;
    await act(async () => {
      resolved = await result.current.resolveByQid("Q42");
    });

    expect(resolved).toEqual({ candidate: null, unavailable: true });
  });

  it("tracks isResolvingQid while the lookup is in flight", async () => {
    let resolveLookup: (() => void) | undefined;
    mockedFetchWikidataCandidateByQid.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLookup = () => resolve({ candidate: null, unavailable: false });
        })
    );

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      void result.current.resolveByQid("Q42");
    });

    await waitFor(() => expect(result.current.isResolvingQid).toBe(true));

    resolveLookup?.();
    await waitFor(() => expect(result.current.isResolvingQid).toBe(false));
  });
});

describe("useWikidataCandidates — reset", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("clears the paged search state — hasSearched, candidates, canShowMore", async () => {
    mockedFetchWikidataCandidates.mockResolvedValueOnce({ candidates: makePage(3), unavailable: false });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person", 3), {
      wrapper: createWrapper(queryClient),
    });

    act(() => result.current.search());
    await waitFor(() => expect(result.current.candidates).toHaveLength(3));

    act(() => result.current.reset());

    expect(result.current.hasSearched).toBe(false);
    expect(result.current.candidates).toHaveLength(0);
    expect(result.current.canShowMore).toBe(false);
  });

  it("clears QID-resolve state (isResolvingQid) alongside the paged search", async () => {
    mockedFetchWikidataCandidateByQid.mockResolvedValueOnce({ candidate: null, unavailable: true });

    const { result } = renderHook(() => useWikidataCandidates("Placeholder", "person"), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.resolveByQid("Q42");
    });

    act(() => result.current.reset());

    expect(result.current.isResolvingQid).toBe(false);
  });
});
