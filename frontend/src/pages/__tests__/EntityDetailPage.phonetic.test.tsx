/**
 * Tests verifying that PhoneticVariantsSection is rendered within EntityDetailPage.
 *
 * Coverage (Feature 046, T024):
 * - PhoneticVariantsSection is rendered between Aliases and Videos sections
 * - The "Suspected ASR Variants" disclosure button is visible
 * - Section is absent when entityId is not defined (null entity state)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

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
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

// Mock PhoneticVariantsSection to keep tests simple and focused on integration.
vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: ({ entityId }: { entityId: string }) => (
    <section aria-label="Suspected ASR Variants mock">
      <button type="button" aria-expanded="false">
        Suspected ASR Variants
      </button>
      <span data-testid="phonetic-entity-id">{entityId}</span>
    </section>
  ),
}));

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockEntity = {
  entity_id: "entity-uuid-001",
  canonical_name: "Noam Chomsky",
  entity_type: "person",
  description: "American linguist and political commentator.",
  status: "active",
  mention_count: 42,
  video_count: 3,
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

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(entityId = "entity-uuid-001") {
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
    promise: Promise.resolve(mockEntity),
  } as ReturnType<typeof useQuery>);

  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityDetailPage — PhoneticVariantsSection integration", () => {
  it("renders the PhoneticVariantsSection disclosure button when entity is loaded", () => {
    renderPage();
    expect(
      screen.getByRole("button", { name: /suspected asr variants/i })
    ).toBeInTheDocument();
  });

  it("renders the PhoneticVariantsSection between Aliases and Videos sections", () => {
    renderPage();

    // Get key landmarks by their headings.
    const aliasesHeading = screen.getByRole("heading", { name: /aliases/i });
    const phoneticButton = screen.getByRole("button", {
      name: /suspected asr variants/i,
    });
    const videosHeading = screen.getByRole("heading", { name: /videos/i });

    // Verify DOM ordering: aliases < phonetic < videos
    const position = (el: Element) =>
      Array.from(document.body.querySelectorAll("*")).indexOf(el);

    expect(position(aliasesHeading)).toBeLessThan(position(phoneticButton));
    expect(position(phoneticButton)).toBeLessThan(position(videosHeading));
  });

  it("passes the entityId to PhoneticVariantsSection", () => {
    renderPage("entity-uuid-001");
    expect(screen.getByTestId("phonetic-entity-id")).toHaveTextContent(
      "entity-uuid-001"
    );
  });

  it("does not render PhoneticVariantsSection in the 404 state", () => {
    vi.mocked(useQuery).mockReturnValue({
      ...({} as ReturnType<typeof useQuery>),
      data: null,
      isLoading: false,
      isError: false,
      error: null,
      status: "success",
      isPending: false,
      isSuccess: true,
      isFetching: false,
      fetchStatus: "idle" as const,
    } as ReturnType<typeof useQuery>);

    renderPage();

    expect(
      screen.queryByRole("button", { name: /suspected asr variants/i })
    ).not.toBeInTheDocument();
  });

  it("does not render PhoneticVariantsSection in the loading skeleton state", () => {
    vi.mocked(useQuery).mockReturnValue({
      ...({} as ReturnType<typeof useQuery>),
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      status: "pending",
      isPending: true,
      isSuccess: false,
      isFetching: true,
      fetchStatus: "fetching" as const,
    } as ReturnType<typeof useQuery>);

    renderPage();

    expect(
      screen.queryByRole("button", { name: /suspected asr variants/i })
    ).not.toBeInTheDocument();
  });
});
