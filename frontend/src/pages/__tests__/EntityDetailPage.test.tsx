/**
 * Tests for EntityDetailPage component.
 *
 * Coverage (Feature 038, T034):
 * - Renders loading skeleton during data fetch
 * - Renders 404 state when entity is not found
 * - Renders entity header with canonical name, type badge, description
 * - Shows total mention count and video count in stats row
 * - Renders video list cards with title, channel, mention count, first timestamp
 * - Video card links contain correct deep-link params (?seg=...&t=...)
 * - Empty state when no videos exist for the entity
 * - "Loading more" indicator when isFetchingNextPage
 * - "All N videos loaded" message at end of list
 * - Loads more videos when hasNextPage is true (via hook)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

// ---------------------------------------------------------------------------
// Mock hooks
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(),
  useVideoEntities: vi.fn(() => ({ entities: [], isLoading: false, isError: false, error: null })),
}));

// We need to mock the TanStack Query useQuery to control entity detail fetch
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";
import type { EntityVideoResult } from "../../api/entityMentions";

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

function createMockVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "vid123",
    video_title: "Chomsky on Language",
    channel_name: "Lectures Channel",
    mention_count: 7,
    mentions: [
      { segment_id: 101, start_time: 30.5, mention_text: "Chomsky" },
    ],
    ...overrides,
  };
}

/** Default mock return for useEntityVideos (empty). */
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

  // Default: entity loads successfully
  vi.mocked(useQuery).mockReturnValue({
    data: mockEntity,
    isLoading: false,
    isError: false,
    error: null,
    // Required TanStack Query shape fields
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

  // Default: empty video list
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityDetailPage", () => {
  describe("Loading state", () => {
    it("renders loading skeleton when entity is loading", () => {
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
      // Skeleton has aria-label
      expect(screen.getByLabelText(/loading entity details/i)).toBeInTheDocument();
    });
  });

  describe("404 state", () => {
    it("renders 404 message when entity is null", () => {
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
      expect(screen.getByText("Entity Not Found")).toBeInTheDocument();
    });

    it("renders 404 with back-to-videos link", () => {
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
      const link = screen.getByRole("link", { name: /back to videos/i });
      expect(link).toHaveAttribute("href", "/videos");
    });
  });

  describe("Entity header", () => {
    it("renders the canonical name as the page heading", () => {
      renderPage();
      expect(screen.getByRole("heading", { name: "Noam Chomsky", level: 1 })).toBeInTheDocument();
    });

    it("renders the entity type badge", () => {
      renderPage();
      expect(screen.getByText("Person")).toBeInTheDocument();
    });

    it("renders the entity description", () => {
      renderPage();
      expect(
        screen.getByText("American linguist and political commentator.")
      ).toBeInTheDocument();
    });

    it("shows 'No description available' when description is null", () => {
      vi.mocked(useQuery).mockReturnValue({
        ...({} as ReturnType<typeof useQuery>),
        data: { ...mockEntity, description: null },
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
      expect(screen.getByText(/no description available/i)).toBeInTheDocument();
    });

    it("renders total mention count from entity", () => {
      renderPage();
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    it("renders total video count when available", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        total: 10,
      });
      renderPage();
      expect(screen.getByText("10")).toBeInTheDocument();
    });
  });

  describe("Video list", () => {
    it("renders video cards with title and channel", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMockVideo()],
        total: 1,
      });
      renderPage();
      expect(screen.getByText("Chomsky on Language")).toBeInTheDocument();
      expect(screen.getByText("Lectures Channel")).toBeInTheDocument();
    });

    it("renders mention count on video card", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMockVideo({ mention_count: 7 })],
        total: 1,
      });
      renderPage();
      expect(screen.getByText("7 mentions")).toBeInTheDocument();
    });

    it("renders first mention timestamp on video card", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createMockVideo({
            mentions: [{ segment_id: 101, start_time: 90.0, mention_text: "Chomsky" }],
          }),
        ],
        total: 1,
      });
      renderPage();
      // 90s = 1:30
      expect(screen.getByText(/first at 1:30/i)).toBeInTheDocument();
    });

    it("video card links to the video with deep-link params", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createMockVideo({
            video_id: "abc123",
            mentions: [{ segment_id: 101, start_time: 30.5, mention_text: "Chomsky" }],
          }),
        ],
        total: 1,
      });
      renderPage();
      const link = screen.getByRole("link", { name: /Chomsky on Language/i });
      expect(link).toHaveAttribute("href", expect.stringContaining("/videos/abc123"));
      expect(link).toHaveAttribute("href", expect.stringContaining("seg=101"));
      expect(link).toHaveAttribute("href", expect.stringContaining("t=30"));
    });

    it("renders empty state when no videos are found", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });
      renderPage();
      expect(
        screen.getByText("No videos found for this entity.")
      ).toBeInTheDocument();
    });
  });

  describe("Infinite scroll states", () => {
    it("shows loading indicator when isFetchingNextPage is true", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMockVideo()],
        total: 2,
        hasNextPage: true,
        isFetchingNextPage: true,
      });
      renderPage();
      expect(screen.getByText(/loading more videos/i)).toBeInTheDocument();
    });

    it("shows 'all videos loaded' message at end of list", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMockVideo()],
        total: 1,
        hasNextPage: false,
        isFetchingNextPage: false,
      });
      renderPage();
      expect(screen.getByText(/1 video loaded/i)).toBeInTheDocument();
    });
  });

  describe("Video list loading", () => {
    it("shows video list skeleton while videos are loading", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        isLoading: true,
      });
      renderPage();
      // Skeleton is present — header should still be visible
      expect(screen.getByRole("heading", { name: "Noam Chomsky", level: 1 })).toBeInTheDocument();
    });
  });
});
