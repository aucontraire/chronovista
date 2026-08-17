/**
 * Tests for EntityDetailPage — bounded auto-refetch for background-fetched
 * enrichment properties (Feature 068, FR-005a).
 *
 * Backend Feature 068 fetches an entity's Wikidata properties in the
 * background after a grounded create/classify. Immediately afterward the
 * entity detail response has `enrichment.grounded === true` with
 * `enrichment.properties === {}`; moments later the background fetch
 * completes and `properties` becomes populated. The detail query in
 * EntityDetailPage.tsx polls a short, bounded number of times
 * (ENRICH_POLL_MAX_ATTEMPTS at ENRICH_POLL_INTERVAL_MS) while that condition
 * holds, so the page surfaces the properties without a manual reload —
 * and it must stop as soon as properties appear, or once the attempt cap is
 * reached, never polling indefinitely.
 *
 * Coverage:
 * - A later refetch that populates properties is reflected in the UI without
 *   a manual reload (manual-refetch-trigger pattern, mirrors
 *   useScanHooks.test.tsx, to avoid asserting on exact interval timing)
 * - Polling stops automatically once the attempt cap is reached, even though
 *   properties never arrive (real interval scheduling via fake timers)
 * - No polling at all for an ungrounded entity, or one whose properties are
 *   already present on the first response
 *
 * This file intentionally does NOT mock `@tanstack/react-query` (unlike
 * EntityDetailPage.enrichment.test.tsx) — the real QueryClient must run so
 * the `refetchInterval` callback actually executes. Only `apiFetch` (the
 * detail query's sole data source in this component) is mocked.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";
import type { EntityDetail } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mock dependencies (mirrors EntityDetailPage.enrichment.test.tsx)
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(() => ({
    videos: [],
    total: null,
    pagination: null,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
  })),
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
  useDeleteManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  })),
  useScanEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useScanVideoEntities: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useUpdateEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    reset: vi.fn(),
  })),
}));

vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));

vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../../api/config";

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-068";
const DETAIL_ENDPOINT = `/entities/${ENTITY_ID}`;

const baseEntity: EntityDetail = {
  entity_id: ENTITY_ID,
  canonical_name: "Newly Grounded Entity",
  entity_type: "person",
  description: null,
  status: "active",
  mention_count: 1,
  video_count: 1,
  by_source: { manual: 1, transcript: 0, title: 0, description: 0, tag: 0 },
  aliases: [],
  exclusion_patterns: [],
};

function groundedButEmpty(): EntityDetail {
  return {
    ...baseEntity,
    enrichment: { grounded: true, properties: {}, identifiers: [] },
  };
}

function groundedWithProperties(): EntityDetail {
  return {
    ...baseEntity,
    enrichment: {
      grounded: true,
      properties: { occupation: { values: ["journalist"] } },
      identifiers: [],
    },
  };
}

function notGrounded(): EntityDetail {
  return {
    ...baseEntity,
    enrichment: { grounded: false, properties: {}, identifiers: [] },
  };
}

// ---------------------------------------------------------------------------
// apiFetch dispatcher
//
// EntityDetailPage renders sibling sections (tags, co-occurring) that also
// go through the mocked `apiFetch` — via fetchEntityTags/fetchCooccurringEntities
// in api/entityMentions.ts, which import `apiFetch` from the same mocked
// module. Dispatching by endpoint keeps the detail-query call count (what
// this file asserts on) uncontaminated by those unrelated sibling fetches.
// ---------------------------------------------------------------------------

/**
 * Wires the mocked apiFetch to serve `responses` (in order, repeating the
 * last one once exhausted) for the entity-detail endpoint, and safe empty
 * defaults for every other endpoint this page's sibling sections call.
 */
function mockDetailResponses(...responses: EntityDetail[]) {
  let callIndex = 0;
  mockedApiFetch.mockImplementation((endpoint: unknown) => {
    const path = typeof endpoint === "string" ? endpoint : "";
    if (path === DETAIL_ENDPOINT) {
      const data = responses[Math.min(callIndex, responses.length - 1)];
      callIndex += 1;
      return Promise.resolve({ data });
    }
    if (path === `${DETAIL_ENDPOINT}/tags`) {
      return Promise.resolve({
        data: { linked_tags: [], needs_attention: false },
      });
    }
    // Co-occurring panel and anything else — a safe empty list.
    return Promise.resolve({ data: [] });
  });
}

/** Calls to the entity-detail endpoint specifically, excluding sibling-section fetches. */
function detailCallCount(): number {
  return mockedApiFetch.mock.calls.filter(
    ([endpoint]) => endpoint === DETAIL_ENDPOINT
  ).length;
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(queryClient: QueryClient, entityId = "entity-uuid-068") {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/entities/${entityId}`]}>
        <Routes>
          <Route path="/entities/:entityId" element={<EntityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityDetailPage — bounded enrichment polling (Feature 068, FR-005a)", () => {
  it("shows properties once a later refetch populates them, without a manual reload", async () => {
    mockDetailResponses(groundedButEmpty(), groundedWithProperties());

    const queryClient = createQueryClient();
    renderPage(queryClient);

    expect(
      await screen.findByTestId("enrichment-not-grounded")
    ).toBeInTheDocument();
    expect(detailCallCount()).toBe(1);

    // Simulate the bounded interval firing (mirrors the manual-trigger
    // pattern in useScanHooks.test.tsx — avoids asserting on exact 1500ms
    // timing while still exercising the real query/render pipeline).
    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ["entity-detail"],
        exact: false,
      });
    });

    expect(await screen.findByText("Occupation")).toBeInTheDocument();
    expect(screen.getByText("journalist")).toBeInTheDocument();
    expect(screen.queryByTestId("enrichment-not-grounded")).toBeNull();
    expect(detailCallCount()).toBe(2);
  });

  it("does not poll an ungrounded entity", async () => {
    mockDetailResponses(notGrounded());

    const queryClient = createQueryClient();
    renderPage(queryClient);

    expect(
      await screen.findByTestId("enrichment-not-grounded")
    ).toBeInTheDocument();

    // Give any (incorrectly) scheduled interval a chance to fire.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(detailCallCount()).toBe(1);
  });

  it("does not poll once properties are already present on the first response", async () => {
    mockDetailResponses(groundedWithProperties());

    const queryClient = createQueryClient();
    renderPage(queryClient);

    expect(await screen.findByText("Occupation")).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(detailCallCount()).toBe(1);
  });

  describe("attempt cap (real interval scheduling)", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("stops polling once the attempt cap is reached, even though properties never arrive", async () => {
      // Properties never populate for this entity — every response stays
      // grounded+empty, so only the attempt cap can end the polling.
      mockDetailResponses(groundedButEmpty());

      const queryClient = createQueryClient();
      renderPage(queryClient);

      // Initial fetch (dataUpdateCount -> 1).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(detailCallCount()).toBe(1);

      // ENRICH_POLL_MAX_ATTEMPTS is 5: four more 1500ms ticks land exactly
      // on the cap.
      for (let i = 0; i < 4; i++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1500);
        });
      }
      expect(detailCallCount()).toBe(5);

      // Further ticks must NOT trigger another fetch — the cap silences
      // refetchInterval permanently for this query.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(detailCallCount()).toBe(5);
    });
  });
});
