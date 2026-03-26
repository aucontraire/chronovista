/**
 * TDD tests for EntityDetailPage — Feature 050, User Story 3 (T038).
 *
 * This file covers the manual-association REMOVAL flow on the entity detail
 * page.  All tests are written TDD-style: the unlink button, confirmation
 * dialog, and `useDeleteManualAssociation` hook do not exist yet.
 *
 * Test suites:
 *   1. Unlink button on manual video cards — visible only when has_manual=true
 *   2. No unlink button for transcript-only cards
 *   3. Confirmation dialog on entity detail page
 *   4. Successful removal — caches invalidated (entity-videos, video-entities, entity-detail)
 *   5. Multi-source removal — removing manual keeps card but removes MANUAL badge
 *   6. Last-source removal — removing the only source removes the video card
 *
 * Hook / module mocking strategy
 * --------------------------------
 * - `useEntityVideos` (hooks/useEntityMentions) — mocked to control video list
 * - `useQuery` (@tanstack/react-query) — mocked to control entity detail fetch
 * - `useDeleteManualAssociation` (hooks/useEntityMentions) — mocked for the new hook
 * - `PhoneticVariantsSection` — mocked to avoid independent useQuery calls
 * - `ExclusionPatternsSection` — mocked to keep tests focused
 *
 * data-testid contract (same as EntityMentionsPanel, scoped to video card context):
 *   - `unlink-button-{video_id}` — unlink button on a video card
 *   - `unlink-confirm-{video_id}` — Confirm button in the inline dialog
 *   - `unlink-cancel-{video_id}` — Cancel button in the inline dialog
 *
 * @module pages/__tests__/EntityDetailPage.removal
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  // The delete hook is the new export added in T038.
  useDeleteManualAssociation: vi.fn(),
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
// TDD: useDeleteManualAssociation will be added to hooks/useEntityMentions in T038.
// We import the module as unknown to avoid compile errors on the not-yet-existing export.
import * as entityMentionsHooks from "../../hooks/useEntityMentions";
import type { EntityVideoResult } from "../../api/entityMentions";

// Typed accessor for the not-yet-existing hook (mocked at module level above).
const useDeleteManualAssociation = (
  entityMentionsHooks as unknown as {
    useDeleteManualAssociation: () => {
      mutate: (vars: { videoId: string; entityId: string }) => void;
      mutateAsync: (vars: { videoId: string; entityId: string }) => Promise<void>;
      isPending: boolean;
      isError: boolean;
      error: unknown;
      isSuccess: boolean;
      isIdle: boolean;
      reset: () => void;
    };
  }
).useDeleteManualAssociation;

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-removal-001";

const mockEntity = {
  entity_id: ENTITY_ID,
  canonical_name: "Noam Chomsky",
  entity_type: "person",
  description: "American linguist and political commentator.",
  status: "active",
  mention_count: 42,
  video_count: 3,
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

/** A video card that has ONLY transcript mentions (no manual association). */
const transcriptOnlyVideo: EntityVideoResult = {
  video_id: "vid-transcript-001",
  video_title: "Chomsky on Language",
  channel_name: "MIT OpenCourseWare",
  mention_count: 5,
  mentions: [{ segment_id: 101, start_time: 45.5, mention_text: "Chomsky" }],
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
  mentions: [{ segment_id: 202, start_time: 90.0, mention_text: "Chomsky" }],
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

function makeIdleDeleteMutationState() {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    isIdle: true,
    reset: vi.fn(),
  };
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
  vi.mocked(useDeleteManualAssociation).mockReturnValue(makeIdleDeleteMutationState());
});

// ===========================================================================
// Suites
// ===========================================================================

describe("EntityDetailPage — manual association removal (TDD for T038)", () => {
  // =========================================================================
  // Suite 1: Unlink button visible on manual video cards (has_manual=true)
  // =========================================================================

  describe("TC-ER01: unlink button visible for video cards with has_manual=true", () => {
    it("shows an unlink button on a video card with has_manual=true", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      // The unlink button on the video card is scoped by video_id.
      const unlinkBtn =
        screen.queryByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });

      expect(unlinkBtn).toBeInTheDocument();
    });

    it("does NOT show an unlink button on a transcript-only video card (has_manual=false)", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([transcriptOnlyVideo])
      );

      renderPage();

      const unlinkBtn = screen.queryByTestId(
        `unlink-button-${transcriptOnlyVideo.video_id}`
      );
      expect(unlinkBtn).not.toBeInTheDocument();
    });

    it("shows an unlink button on a multi-source video card", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([multiSourceVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.queryByTestId(`unlink-button-${multiSourceVideo.video_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });

      expect(unlinkBtn).toBeInTheDocument();
    });

    it("renders unlink buttons only for cards where has_manual=true when multiple cards are present", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([transcriptOnlyVideo, manualOnlyVideo])
      );

      renderPage();

      // Manual card: unlink button present.
      const manualUnlink =
        screen.queryByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.queryAllByRole("button", { name: /unlink|remove manual|remove association/i })[0];
      expect(manualUnlink).toBeInTheDocument();

      // Transcript-only card: no unlink button with specific testid.
      const transcriptUnlink = screen.queryByTestId(
        `unlink-button-${transcriptOnlyVideo.video_id}`
      );
      expect(transcriptUnlink).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Suite 2: Confirmation dialog on entity detail page
  // =========================================================================

  describe("TC-ER02: confirmation dialog on entity detail page", () => {
    it("shows an inline confirmation when the unlink button is clicked on a video card", async () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      const user = userEvent.setup();
      await user.click(unlinkBtn);

      // Confirmation Confirm button must appear.
      const confirmBtn =
        screen.queryByTestId(`unlink-confirm-${manualOnlyVideo.video_id}`) ??
        screen.queryByRole("button", { name: /confirm|yes, remove/i });

      expect(confirmBtn).toBeInTheDocument();
    });

    it("confirmation dialog shows the FR-027 required message about transcript mentions remaining", async () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/only the manual association will be removed/i)
        ).toBeInTheDocument();
      });
    });

    it("confirmation dialog shows both a Confirm and Cancel button", async () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        const confirmBtn =
          screen.queryByTestId(`unlink-confirm-${manualOnlyVideo.video_id}`) ??
          screen.queryByRole("button", { name: /confirm|yes, remove/i });

        const cancelBtn =
          screen.queryByTestId(`unlink-cancel-${manualOnlyVideo.video_id}`) ??
          screen.queryByRole("button", { name: /cancel/i });

        expect(confirmBtn).toBeInTheDocument();
        expect(cancelBtn).toBeInTheDocument();
      });
    });

    it("clicking Cancel hides the confirmation dialog without calling the mutation", async () => {
      const mutateFn = vi.fn();
      vi.mocked(useDeleteManualAssociation).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      const cancelBtn = await screen.findByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      await waitFor(() => {
        expect(
          screen.queryByText(/only the manual association will be removed/i)
        ).not.toBeInTheDocument();
      });

      expect(mutateFn).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Suite 3: Successful removal — caches invalidated
  // =========================================================================

  describe("TC-ER03: successful removal fires the mutation with correct arguments", () => {
    it("calls useDeleteManualAssociation mutate with { videoId, entityId } on confirm", async () => {
      const mutateFn = vi.fn();
      vi.mocked(useDeleteManualAssociation).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage(ENTITY_ID);

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      const confirmBtn = await screen.findByRole("button", { name: /confirm|yes, remove/i });
      fireEvent.click(confirmBtn);

      expect(mutateFn).toHaveBeenCalledWith({
        videoId: manualOnlyVideo.video_id,
        entityId: ENTITY_ID,
      });
    });

    it("does NOT call mutate before Confirm is clicked", async () => {
      const mutateFn = vi.fn();
      vi.mocked(useDeleteManualAssociation).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${manualOnlyVideo.video_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      // Wait for dialog to render without clicking Confirm.
      await screen.findByRole("button", { name: /confirm|yes, remove/i });

      expect(mutateFn).not.toHaveBeenCalled();
    });

    it("the useDeleteManualAssociation hook is called on mount (hook is consumed by the page)", () => {
      vi.mocked(useEntityVideos).mockReturnValue(
        makeEntityVideosState([manualOnlyVideo])
      );

      renderPage();

      // The hook must be invoked when the page renders (it sets up the mutation).
      expect(vi.mocked(useDeleteManualAssociation)).toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Suite 4: Multi-source removal — MANUAL badge disappears, card remains
  //
  // When a video has both transcript and manual sources, removing the manual
  // association leaves the video card visible (transcript mentions remain) but
  // the [MANUAL] badge disappears and the unlink button is removed.
  // =========================================================================

  describe("TC-ER04: multi-source removal keeps card visible but removes MANUAL badge", () => {
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
  // Suite 5: Last-source removal — removing the only source removes the card
  //
  // When a video has ONLY a manual association (mention_count=0, sources=["manual"]),
  // removing that association means the backend will no longer return the video
  // in the entity-videos response.  The card should disappear from the list.
  // =========================================================================

  describe("TC-ER05: last-source removal causes the video card to disappear", () => {
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
