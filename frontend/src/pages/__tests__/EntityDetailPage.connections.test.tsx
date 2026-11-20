/**
 * EntityDetailPage — "See connections" pre-seeds the Connection Explorer (Feature 115, FR-016).
 * Setup mirrors the sibling EntityDetailPage suites (useQuery is globally stubbed).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

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

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

// The page's PhoneticVariantsSection reads through the globally-mocked
// useQuery and expects an array. Stubbing it keeps these tests focused on the
// appears-with panel, matching the sibling suites' approach.
vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => <section aria-label="Phonetic variants stub" />,
}));

const cooccurringMock = vi.fn();
vi.mock("../../hooks/useCooccurringEntities", async () => {
  const actual = await vi.importActual<
    typeof import("../../hooks/useCooccurringEntities")
  >("../../hooks/useCooccurringEntities");
  return {
    ...actual,
    useCooccurringEntities: (...args: unknown[]) => cooccurringMock(...args),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";

const mockEntity = {
  entity_id: "entity-uuid-062",
  canonical_name: "Ada Lovelace",
  entity_type: "person",
  description: "Fixture entity.",
  status: "active",
  mention_count: 42,
  video_count: 3,
  by_source: { manual: 0, transcript: 3, title: 0, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
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

function renderPage(entityId = "entity-uuid-062") {
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

beforeEach(() => {
  vi.clearAllMocks();

  vi.mocked(useQuery).mockReturnValue({
    data: mockEntity,
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
    dataUpdatedAt: 0,
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
    promise: Promise.resolve(mockEntity),
  } as ReturnType<typeof useQuery>);

  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
});

describe("EntityDetailPage — see connections (Feature 115)", () => {
  it("links to the explorer with this entity as endpoint A", () => {
    cooccurringMock.mockReturnValue({ partners: [], isLoading: false, isError: false, error: null });
    renderPage();
    const link = screen.getByRole("link", { name: /see connections/i });
    expect(link).toHaveAttribute("href", "/connections?a=entity-uuid-062");
  });
});
