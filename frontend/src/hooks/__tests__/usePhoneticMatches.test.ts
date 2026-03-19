/**
 * Tests for usePhoneticMatches hook.
 *
 * Coverage:
 * - Returns filtered data based on displayThreshold (client-side)
 * - Query key only includes serverFloor, not displayThreshold
 * - Query is disabled when enabled=false
 * - Re-fetches when serverFloor changes
 * - Server floor bumps up when displayThreshold < serverFloor
 * - Returns undefined when query has not fired (enabled=false)
 * - Error state propagates from fetchPhoneticMatches
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { fetchPhoneticMatches } from "../../api/entityMentions";
import { usePhoneticMatches } from "../usePhoneticMatches";
import type { PhoneticMatch } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  fetchPhoneticMatches: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchPhoneticMatches);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makePhoneticMatch(
  overrides: Partial<PhoneticMatch> = {}
): PhoneticMatch {
  return {
    original_text: "noam chomski",
    proposed_correction: "Noam Chomsky",
    confidence: 0.8,
    evidence_description: "Phonetic similarity via double metaphone",
    video_id: "video-uuid-001",
    segment_id: 42,
    video_title: "Chomsky on Language",
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

describe("usePhoneticMatches", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Basic fetch behaviour
  // -------------------------------------------------------------------------

  it("fetches phonetic matches for an entity and returns data on success", async () => {
    const match = makePhoneticMatch({ confidence: 0.8 });
    mockedFetch.mockResolvedValueOnce([match]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
          displayThreshold: 0.5,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.original_text).toBe("noam chomski");
  });

  it("calls fetchPhoneticMatches with entityId and serverFloor", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.4,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch).toHaveBeenCalledWith(
      "entity-uuid-001",
      0.4,
      expect.any(AbortSignal)
    );
  });

  // -------------------------------------------------------------------------
  // Client-side displayThreshold filtering
  // -------------------------------------------------------------------------

  it("filters out matches below displayThreshold on the client side", async () => {
    const matches = [
      makePhoneticMatch({ confidence: 0.9, original_text: "high-confidence" }),
      makePhoneticMatch({ confidence: 0.55, original_text: "mid-confidence" }),
      makePhoneticMatch({ confidence: 0.3, original_text: "low-confidence" }),
    ];
    mockedFetch.mockResolvedValueOnce(matches);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
          displayThreshold: 0.6,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Only the 0.9-confidence match should pass the 0.6 display threshold
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.original_text).toBe("high-confidence");
  });

  it("keeps all matches when displayThreshold is 0", async () => {
    const matches = [
      makePhoneticMatch({ confidence: 0.9 }),
      makePhoneticMatch({ confidence: 0.3 }),
    ];
    mockedFetch.mockResolvedValueOnce(matches);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0,
          displayThreshold: 0,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(2);
  });

  it("includes matches exactly at the displayThreshold boundary", async () => {
    const match = makePhoneticMatch({ confidence: 0.5 });
    mockedFetch.mockResolvedValueOnce([match]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
          displayThreshold: 0.5,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // Query key — serverFloor included, displayThreshold excluded
  // -------------------------------------------------------------------------

  it("does not issue a new fetch when only displayThreshold changes", async () => {
    const matches = [makePhoneticMatch({ confidence: 0.8 })];
    mockedFetch.mockResolvedValue(matches);

    const { result, rerender } = renderHook(
      ({ threshold }: { threshold: number }) =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
          displayThreshold: threshold,
        }),
      {
        wrapper: createWrapper(queryClient),
        initialProps: { threshold: 0.5 },
      }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedFetch).toHaveBeenCalledTimes(1);

    // Change only displayThreshold — no new fetch should occur
    rerender({ threshold: 0.7 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Still only one fetch
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("issues a new fetch when serverFloor changes", async () => {
    // Use separate QueryClients to avoid cache hits from the same query client.
    // displayThreshold must be >= serverFloor in both hooks to avoid the
    // bump logic triggering additional fetches that would confuse the assertion.
    const qcA = createQueryClient();
    const qcB = createQueryClient();

    mockedFetch.mockResolvedValue([]);

    // First hook: serverFloor=0.3, displayThreshold=0.3 (no bump needed)
    const { result: resultA } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
          displayThreshold: 0.3,
        }),
      { wrapper: createWrapper(qcA) }
    );

    await waitFor(() => expect(resultA.current.isSuccess).toBe(true));
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch).toHaveBeenCalledWith(
      "entity-uuid-001",
      0.3,
      expect.any(AbortSignal)
    );

    // Second hook: serverFloor=0.6, displayThreshold=0.6 (no bump needed)
    const { result: resultB } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.6,
          displayThreshold: 0.6,
        }),
      { wrapper: createWrapper(qcB) }
    );

    await waitFor(() => expect(resultB.current.isSuccess).toBe(true));
    expect(mockedFetch).toHaveBeenCalledTimes(2);
    expect(mockedFetch).toHaveBeenLastCalledWith(
      "entity-uuid-001",
      0.6,
      expect.any(AbortSignal)
    );
  });

  // -------------------------------------------------------------------------
  // Lazy loading: enabled=false
  // -------------------------------------------------------------------------

  it("does not fetch when enabled is false", () => {
    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          enabled: false,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedFetch).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
  });

  it("starts fetching when enabled flips from false to true", async () => {
    mockedFetch.mockResolvedValueOnce([makePhoneticMatch()]);

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          enabled,
        }),
      {
        wrapper: createWrapper(queryClient),
        initialProps: { enabled: false },
      }
    );

    expect(mockedFetch).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();

    rerender({ enabled: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(result.current.data).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // Server floor bumping when displayThreshold < serverFloor
  // -------------------------------------------------------------------------

  it("bumps effectiveServerFloor up when displayThreshold falls below serverFloor", async () => {
    mockedFetch.mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.5,
          displayThreshold: 0.2, // below serverFloor
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // effectiveServerFloor should be bumped to displayThreshold (0.2)
    expect(result.current.effectiveServerFloor).toBe(0.2);
    expect(mockedFetch).toHaveBeenCalledWith(
      "entity-uuid-001",
      0.2,
      expect.any(AbortSignal)
    );
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("exposes isError=true and error when fetch rejects", async () => {
    mockedFetch.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBeInstanceOf(Error);
  });

  // -------------------------------------------------------------------------
  // Empty results
  // -------------------------------------------------------------------------

  it("returns an empty array when API returns no matches", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          displayThreshold: 0.5,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("exposes isLoading=true while fetch is in progress", () => {
    mockedFetch.mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
        }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // Default parameter values
  // -------------------------------------------------------------------------

  it("uses default serverFloor of 0.3 when not provided", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedFetch).toHaveBeenCalledWith(
      "entity-uuid-001",
      0.3,
      expect.any(AbortSignal)
    );
  });

  it("filters with default displayThreshold of 0.5 when not provided", async () => {
    const matches = [
      makePhoneticMatch({ confidence: 0.8, original_text: "above-threshold" }),
      makePhoneticMatch({ confidence: 0.3, original_text: "below-threshold" }),
    ];
    mockedFetch.mockResolvedValueOnce(matches);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
          serverFloor: 0.3,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Default displayThreshold is 0.5, so 0.3 confidence should be filtered
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.original_text).toBe("above-threshold");
  });

  // -------------------------------------------------------------------------
  // AbortSignal forwarding
  // -------------------------------------------------------------------------

  it("passes AbortSignal to fetchPhoneticMatches", async () => {
    mockedFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(
      () =>
        usePhoneticMatches({
          entityId: "entity-uuid-001",
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const callArgs = mockedFetch.mock.calls[0];
    expect(callArgs?.[2]).toBeInstanceOf(AbortSignal);
  });
});
