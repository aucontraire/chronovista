/**
 * Tests for EntityDetailPage — manual-association display after Feature 091.
 *
 * The manual-unlink flow (unlink button, inline confirmation,
 * `useDeleteManualAssociation`) was removed from this page; the "Not about
 * this?" exclude control is the single remove control on each video row. The
 * surgical manual-unlink remains on the video detail page (EntityMentionsPanel).
 *
 * Test suites:
 *   1. No unlink control; exactly one (exclude) remove control per card
 *   2. Multi-source cards keep the MANUAL badge and transcript badge
 *   3. Manual-only cards: badge, label, and empty state
 *
 * Hook / module mocking strategy
 * --------------------------------
 * - `useEntityVideos` (hooks/useEntityMentions) — mocked to control video list
 * - `useQuery` (@tanstack/react-query) — mocked to control entity detail fetch
 * - `PhoneticVariantsSection` — mocked to avoid independent useQuery calls
 * - `ExclusionPatternsSection` — mocked to keep tests focused
 *
 * @module pages/__tests__/EntityDetailPage.removal
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
import type { EntityVideoResult } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-removal-001";

const mockEntity = {
  entity_id: ENTITY_ID,
  canonical_name: "Ada Lovelace",
  entity_type: "person",
  description: "American linguist and political commentator.",
  status: "active",
  mention_count: 42,
  video_count: 3,
  by_source: { manual: 0, transcript: 3, title: 0, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

/** A video card that has ONLY transcript mentions (no manual association). */
const transcriptOnlyVideo: EntityVideoResult = {
  video_id: "vid-transcript-001",
  video_title: "Lovelace on Language",
  channel_name: "MIT OpenCourseWare",
  mention_count: 5,
  mentions: [{ segment_id: 101, start_time: 45.5, mention_text: "Lovelace" }],
  sources: ["transcript"],
  has_manual: false,
  first_mention_time: 45.5,
  upload_date: "2023-06-01T00:00:00Z",
};

/** A video card that has ONLY a manual association (no transcript hits). */
const manualOnlyVideo: EntityVideoResult = {
  video_id: "vid-manual-only-002",
  video_title: "Philosophy of Language",
  channel_name: "Test Channel",
  mention_count: 0,
  mentions: [],
  sources: ["manual"],
  has_manual: true,
  first_mention_time: null,
  upload_date: "2023-07-01T00:00:00Z",
};

/** A video card with BOTH transcript and manual sources. */
const multiSourceVideo: EntityVideoResult = {
  video_id: "vid-multi-source-003",
  video_title: "Multi Source Video",
  channel_name: "Tech Talk",
  mention_count: 3,
  mentions: [{ segment_id: 202, start_time: 90.0, mention_text: "Lovelace" }],
  sources: ["transcript", "manual"],
  has_manual: true,
  first_mention_time: 90.0,
  upload_date: "2023-08-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Default empty hook state for useEntityVideos. */
function makeEntityVideosState(videos: EntityVideoResult[] = []) {
  return {
    videos,
    total: videos.length,
    pagination: null,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
  };
}

/** Builds a TanStack Query useQuery success return value for entity detail. */
function makeSuccessQuery(
  data: typeof mockEntity
): ReturnType<typeof useQuery> {
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

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

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

beforeEach(() => {
  vi.clearAllMocks();

  vi.mocked(useQuery).mockReturnValue(makeSuccessQuery(mockEntity));
  vi.mocked(useEntityVideos).mockReturnValue(makeEntityVideosState());
});

// ===========================================================================
// Suites
// ===========================================================================

describe("EntityDetailPage — manual associations (no unlink control)", () => {
  // =========================================================================
  // Suite 1: The manual-unlink flow no longer exists on this page. The
  // "Not about this?" exclude control is the single remove control per row.
  // =========================================================================

  describe("TC-ER01: no manual-unlink control on the entity detail page", () => {
    it("renders no unlink button on a has_manual=true card", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo, multiSourceVideo])
      );

      renderPage();

      expect(
        screen.queryByTestId(`unlink-button-${manualOnlyVideo.video_id}`)
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId(`unlink-button-${multiSourceVideo.video_id}`)
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /remove manual association/i })
      ).not.toBeInTheDocument();
    });

    it("shows exactly one remove control per card: the exclude button", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo, transcriptOnlyVideo])
      );

      renderPage();

      expect(
        screen.getByTestId(`exclude-button-${manualOnlyVideo.video_id}`)
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`exclude-button-${transcriptOnlyVideo.video_id}`)
      ).toBeInTheDocument();
      expect(screen.getAllByText("Not about this?")).toHaveLength(2);
    });
  });

  // =========================================================================
  // Suite 2: Multi-source removal — MANUAL badge disappears, card remains
  //
  // When a video has both transcript and manual sources, removing the manual
  // association leaves the video card visible (transcript mentions remain) but
  // the [MANUAL] badge disappears and the unlink button is removed.
  // =========================================================================

  describe("TC-ER02: multi-source removal keeps card visible but removes MANUAL badge", () => {
    it("MANUAL badge is present on a multi-source video card before removal", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([multiSourceVideo])
      );

      renderPage();

      expect(screen.getByTestId("manual-badge")).toBeInTheDocument();
    });

    it("transcript badge is also present on a multi-source video card", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([multiSourceVideo])
      );

      renderPage();

      expect(screen.getByTestId("transcript-badge")).toBeInTheDocument();
    });

    it("video card stays visible after simulated removal of the manual association", () => {
      const { rerender } = renderPage();

      // Before: multi-source video present.
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([multiSourceVideo])
      );

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("Multi Source Video")).toBeInTheDocument();

      // Simulate post-deletion: has_manual is now false.
      const afterRemoval = {
        ...multiSourceVideo,
        has_manual: false,
        sources: ["transcript"],
      };

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([afterRemoval])
      );

      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Card still visible (transcript mentions remain).
      expect(screen.getByText("Multi Source Video")).toBeInTheDocument();
    });

    it("MANUAL badge disappears after simulated removal (has_manual becomes false)", () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      const afterRemoval = {
        ...multiSourceVideo,
        has_manual: false,
        sources: ["transcript"],
      };

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([afterRemoval])
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.queryByTestId("manual-badge")).not.toBeInTheDocument();
    });

    it("transcript badge remains visible after simulated removal of the manual association", () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      const afterRemoval = {
        ...multiSourceVideo,
        has_manual: false,
        sources: ["transcript"],
      };

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([afterRemoval])
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Transcript badge should still be present.
      expect(screen.getByTestId("transcript-badge")).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Suite 3: Last-source removal — removing the only source removes the card
  //
  // When a video has ONLY a manual association (mention_count=0, sources=["manual"]),
  // removing that association means the backend will no longer return the video
  // in the entity-videos response.  The card should disappear from the list.
  // =========================================================================

  describe("TC-ER03: last-source removal causes the video card to disappear", () => {
    it("manual-only video card is visible before removal", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      expect(screen.getByText("Philosophy of Language")).toBeInTheDocument();
    });

    it("video card disappears from list after simulated last-source removal", () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      // Start with the manual-only video visible.
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("Philosophy of Language")).toBeInTheDocument();

      // Simulate: backend no longer returns this video (manual was the only source).
      vi.mocked(useEntityVideos).mockReturnValue(makeEntityVideosState([]));

      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
            <Routes>
              <Route path="/entities/:entityId" element={<EntityDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.queryByText("Philosophy of Language")).not.toBeInTheDocument();
    });

    it("shows the empty state message when all videos have been removed", () => {
      vi.mocked(useEntityVideos).mockReturnValue(makeEntityVideosState([]));

      renderPage();

      expect(
        screen.getByText(/no videos found for this entity/i)
      ).toBeInTheDocument();
    });

    it("the MANUAL badge is shown for a manual-only card before it is removed", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      // Manual-only video cards should show the MANUAL badge.
      expect(screen.getByTestId("manual-badge")).toBeInTheDocument();
    });

    it("'Manually linked' label appears for manual-only video cards", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      expect(screen.getByText(/manually linked/i)).toBeInTheDocument();
    });
  });
});
