/**
 * EntityDetailPage — appears-with panel integration (Feature 062, US3, T064).
 *
 * Asserts the two properties FR-037 and FR-038 are about: the panel does not
 * block the page's initial render, and a panel failure leaves the page usable.
 *
 * The panel is the feature's slowest query — roughly ten times the
 * intersection itself. Computing it synchronously would dominate load time for
 * exactly the entities users open most, the well-connected ones. These tests
 * pin that it does not.
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

describe("EntityDetailPage — appears-with panel (Feature 062)", () => {
  it("renders the entity's own content while the panel is still loading (FR-037)", () => {
    cooccurringMock.mockReturnValue({
      partners: [],
      isLoading: true,
      isError: false,
      error: null,
    });
    renderPage();

    // The page's primary content is present even though the panel has not
    // resolved — the panel is not on the critical render path.
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByTestId("cooccurring-loading")).toBeInTheDocument();
  });

  it("leaves the page usable when the panel fails (FR-038)", () => {
    cooccurringMock.mockReturnValue({
      partners: [],
      isLoading: false,
      isError: true,
      error: new Error("panel exploded"),
    });
    renderPage();

    // A panel-level error, not a page-level one.
    expect(screen.getByTestId("cooccurring-error")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("mounts the panel with the entity from the route", () => {
    cooccurringMock.mockReturnValue({
      partners: [],
      isLoading: false,
      isError: false,
      error: null,
    });
    renderPage();

    expect(screen.getByTestId("cooccurring-panel")).toBeInTheDocument();
    expect(cooccurringMock).toHaveBeenCalledWith(
      "entity-uuid-062",
      expect.any(Number),
      undefined
    );
  });

  it("renders partners once they arrive", () => {
    cooccurringMock.mockReturnValue({
      partners: [
        {
          entity_id: "partner-1",
          entity_type: "place",
          canonical_name: "Bletchley Park",
          shared_video_count: 7,
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    });
    renderPage();

    expect(screen.getByText("Bletchley Park")).toBeInTheDocument();
    expect(screen.getByText("7 videos")).toBeInTheDocument();
  });
});
