/**
 * Tests for the entity description fallback on EntityDetailPage: the curated
 * description wins; otherwise the Wikidata one-liner is shown with a
 * "from Wikidata" hint.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

// ---------------------------------------------------------------------------
// Mock hooks used by EntityDetailPage
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
  useUpdateEntity: vi.fn(),
}));

// Mock PhoneticVariantsSection / ExclusionPatternsSection to avoid them
// issuing independent useQuery calls, which would conflict with the global
// useQuery mock below.
vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));
vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));

// Mock TanStack Query useQuery so we can control the entity detail fetch.
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos, useUpdateEntity } from "../../hooks/useEntityMentions";


// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-edit-001";

const mockEntity: Record<string, unknown> = {
  entity_id: ENTITY_ID,
  canonical_name: "Sample Org",
  entity_type: "organization",
  description: "An AI lab.",
  status: "active",
  mention_count: 12,
  video_count: 4,
  by_source: { manual: 0, transcript: 4, title: 0, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
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

function makeSuccessQuery(data: Record<string, unknown>): ReturnType<typeof useQuery> {
  return {
    data,
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
    promise: Promise.resolve(data),
  } as ReturnType<typeof useQuery>;
}

/** Builds a minimal-but-typed useUpdateEntity mutation return value. */
function makeUpdateEntityMock(
  mutate: ReturnType<typeof vi.fn>,
  isPending = false
): ReturnType<typeof useUpdateEntity> {
  return {
    mutate,
    mutateAsync: vi.fn(),
    isPending,
    isError: false,
    error: null,
    isSuccess: false,
    isIdle: !isPending,
    status: isPending ? "pending" : "idle",
    data: undefined,
    variables: undefined,
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateEntity>;
}

function renderPage(entityId = ENTITY_ID) {
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

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------


const enrichment = {
  grounded: true,
  identifiers: [],
  properties: {
    wikidata_description: {
      source: "wikidata",
      set_at: "2026-01-01T00:00:00Z",
      values: ["a placeholder wikidata description"],
    },
  },
};

function setEntity(over: Record<string, unknown>) {
  vi.mocked(useQuery).mockReturnValue(makeSuccessQuery({ ...mockEntity, ...over }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
  vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(vi.fn()));
});

describe("EntityDetailPage description fallback", () => {
  it("shows the wikidata description with a hint when description is empty", () => {
    setEntity({
      description: "",
      fallback_description: "a placeholder wikidata description",
      enrichment,
    });
    renderPage();
    const hint = screen.getByTestId("description-wikidata-hint");
    expect(hint).toHaveTextContent("from Wikidata");
    expect(hint.parentElement).toHaveTextContent(/a placeholder wikidata description/);
  });

  it("shows the curated description, without the hint, when present", () => {
    setEntity({
      description: "A curated description.",
      fallback_description: "a placeholder wikidata description",
      enrichment,
    });
    renderPage();
    expect(screen.getByText("A curated description.")).toBeInTheDocument();
    expect(screen.queryByTestId("description-wikidata-hint")).not.toBeInTheDocument();
  });

  it("keeps the empty state when neither description exists", () => {
    setEntity({ description: null });
    renderPage();
    expect(screen.getByText("No description available.")).toBeInTheDocument();
    expect(screen.queryByTestId("description-wikidata-hint")).not.toBeInTheDocument();
  });
});
