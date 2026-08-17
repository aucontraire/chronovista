/**
 * Tests for EntityDetailPage — entity enrichment section (Feature 067, US2).
 *
 * Coverage:
 * - Grounded entity renders properties (humanized key + joined values) and
 *   identifier links, with a "verified" indicator for verified identifiers
 * - Ungrounded entity (grounded: false, or missing enrichment) renders the
 *   "Not grounded" empty state
 * - Identifier links point at `url`, open in a new tab (target="_blank"), and
 *   carry rel="noopener noreferrer"
 *
 * Mock strategy follows the existing EntityDetailPage.source-badges.test.tsx
 * pattern: `useEntityVideos` and `useQuery` are mocked to control the entity
 * detail fetch, `PhoneticVariantsSection` and `ExclusionPatternsSection` are
 * stubbed to keep the tests focused.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";
import type { EntityEnrichment } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(),
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

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const baseEntity = {
  entity_id: "entity-uuid-067",
  canonical_name: "Test Entity",
  entity_type: "person",
  description: "An example entity used for testing.",
  status: "active",
  mention_count: 5,
  video_count: 3,
  by_source: { manual: 1, transcript: 1, title: 1, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

const groundedEnrichment: EntityEnrichment = {
  grounded: true,
  properties: {
    occupation: { values: ["journalist"], qids: ["Q1930187"] },
    country: { values: ["Testland", "Exampleland"], qids: ["Q1", "Q2"] },
  },
  identifiers: [
    {
      source: "wikidata",
      id: "Q42",
      url: "https://www.wikidata.org/wiki/Q42",
      verified: true,
    },
    {
      source: "dbpedia",
      id: "http://dbpedia.org/resource/Test_Entity",
      url: "http://dbpedia.org/resource/Test_Entity",
      verified: false,
    },
  ],
};

const defaultUseEntityVideos = {
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
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(entityId = "entity-uuid-067") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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

function mockEntityQuery(entity: unknown) {
  vi.mocked(useQuery).mockReturnValue({
    data: entity,
    isLoading: false,
    isError: false,
    error: null,
    status: "success",
    isFetching: false,
    isPending: false,
    isSuccess: true,
    isRefetching: false,
    isLoadingError: false,
    isRefetchError: false,
    isPaused: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: Date.now(),
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    fetchStatus: "idle" as const,
    isFetched: true,
    isFetchedAfterMount: true,
    isInitialLoading: false,
    isEnabled: true,
    refetch: vi.fn(),
    promise: Promise.resolve(entity),
  } as ReturnType<typeof useQuery>);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityDetailPage — enrichment section (Feature 067, US2)", () => {
  it("renders humanized property keys and joined values for a grounded entity", () => {
    mockEntityQuery({ ...baseEntity, enrichment: groundedEnrichment });

    renderPage();

    expect(screen.getByText("Occupation")).toBeInTheDocument();
    expect(screen.getByText("journalist")).toBeInTheDocument();
    expect(screen.getByText("Country")).toBeInTheDocument();
    expect(screen.getByText("Testland, Exampleland")).toBeInTheDocument();
  });

  it("renders an identifier link per identifier for a grounded entity", () => {
    mockEntityQuery({ ...baseEntity, enrichment: groundedEnrichment });

    renderPage();

    const wikidataLink = screen.getByRole("link", { name: /wikidata/i });
    expect(wikidataLink).toHaveAttribute(
      "href",
      "https://www.wikidata.org/wiki/Q42"
    );

    const dbpediaLink = screen.getByRole("link", { name: /dbpedia/i });
    expect(dbpediaLink).toHaveAttribute(
      "href",
      "http://dbpedia.org/resource/Test_Entity"
    );
  });

  it("shows a verified indicator only for verified identifiers", () => {
    mockEntityQuery({ ...baseEntity, enrichment: groundedEnrichment });

    renderPage();

    const wikidataLink = screen.getByRole("link", { name: /wikidata/i });
    const dbpediaLink = screen.getByRole("link", { name: /dbpedia/i });

    expect(
      within(wikidataLink).getByLabelText("human-verified")
    ).toBeInTheDocument();
    expect(within(dbpediaLink).queryByLabelText("human-verified")).toBeNull();
  });

  it("identifier links open in a new tab with noopener/noreferrer", () => {
    mockEntityQuery({ ...baseEntity, enrichment: groundedEnrichment });

    renderPage();

    const wikidataLink = screen.getByRole("link", { name: /wikidata/i });
    expect(wikidataLink).toHaveAttribute("target", "_blank");
    const rel = wikidataLink.getAttribute("rel") ?? "";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });

  it("renders the 'Not grounded' empty state when grounded is false", () => {
    mockEntityQuery({
      ...baseEntity,
      enrichment: { grounded: false, properties: {}, identifiers: [] },
    });

    renderPage();

    expect(screen.getByTestId("enrichment-not-grounded")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /wikidata/i })).toBeNull();
  });

  it("renders the 'Not grounded' empty state when enrichment is missing entirely", () => {
    mockEntityQuery({ ...baseEntity });

    renderPage();

    expect(screen.getByTestId("enrichment-not-grounded")).toBeInTheDocument();
  });

  it("renders the 'Not grounded' empty state when grounded is true but properties and identifiers are empty", () => {
    mockEntityQuery({
      ...baseEntity,
      enrichment: { grounded: true, properties: {}, identifiers: [] },
    });

    renderPage();

    expect(screen.getByTestId("enrichment-not-grounded")).toBeInTheDocument();
  });
});
