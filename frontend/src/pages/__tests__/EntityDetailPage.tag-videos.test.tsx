/**
 * Tests for EntityDetailPage — Feature 053, Phase 5 (User Story 3).
 *
 * Coverage (T021-T024): Source Distinction Frontend Badges
 * - T021: Video with sources: ["transcript"] renders mention count badge with timestamp link
 * - T022: Video with sources: ["tag"] renders teal TAG badge without timestamp link
 * - T023: Video with sources: ["transcript", "tag"] renders both badges
 * - T024: Tag-only videos appear after transcript-mention videos in default sort
 *
 * Mock strategy follows the existing EntityDetailPage.test.tsx pattern:
 * - `useEntityVideos` (hooks/useEntityMentions) — mocked to control video list
 * - `useQuery` (@tanstack/react-query) — mocked to control entity detail fetch
 * - `PhoneticVariantsSection` — mocked to avoid independent useQuery calls
 * - `ExclusionPatternsSection` — mocked to keep tests focused
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
import type { EntityVideoResult } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockEntity = {
  entity_id: "entity-uuid-001",
  canonical_name: "David Sheen",
  entity_type: "person",
  description: "Journalist and documentary filmmaker.",
  status: "active",
  mention_count: 5,
  video_count: 3,
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

function createTranscriptVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "transcript-vid-001",
    video_title: "Transcript Video",
    channel_name: "Test Channel",
    mention_count: 3,
    mentions: [
      { segment_id: 42, start_time: 120.0, mention_text: "David Sheen" },
    ],
    sources: ["transcript"],
    has_manual: false,
    first_mention_time: 120.0,
    upload_date: "2024-06-20T00:00:00+00:00",
    ...overrides,
  };
}

function createTagOnlyVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "tag-only-vid-001",
    video_title: "Tag Only Video",
    channel_name: "Test Channel",
    mention_count: 0,
    mentions: [],
    sources: ["tag"],
    has_manual: false,
    first_mention_time: null,
    upload_date: "2024-05-10T00:00:00+00:00",
    ...overrides,
  };
}

function createMixedSourceVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "mixed-vid-001",
    video_title: "Mixed Source Video",
    channel_name: "Test Channel",
    mention_count: 2,
    mentions: [
      { segment_id: 55, start_time: 60.0, mention_text: "David Sheen" },
    ],
    sources: ["transcript", "tag"],
    has_manual: false,
    first_mention_time: 60.0,
    upload_date: "2024-07-01T00:00:00+00:00",
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
// Tests — T021-T024
// ---------------------------------------------------------------------------

describe("EntityDetailPage — source distinction badges (Feature 053, US3)", () => {
  /**
   * T021: Video with sources: ["transcript"] renders mention count badge
   * and a deep-link to the transcript timestamp.
   */
  describe("T021 — transcript-only video", () => {
    it("renders the TRANSCRIPT badge with mention count", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTranscriptVideo({ mention_count: 3 })],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("transcript-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("TRANSCRIPT");
      expect(badge).toHaveTextContent("3");
    });

    it("video card link includes timestamp deep-link params", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createTranscriptVideo({
            video_id: "transcript-vid-001",
            mentions: [{ segment_id: 42, start_time: 120.0, mention_text: "David Sheen" }],
            first_mention_time: 120.0,
          }),
        ],
        total: 1,
      });

      renderPage();

      const link = screen.getByRole("link", { name: /Transcript Video/i });
      expect(link).toHaveAttribute("href", expect.stringContaining("/videos/transcript-vid-001"));
      expect(link).toHaveAttribute("href", expect.stringContaining("seg=42"));
      expect(link).toHaveAttribute("href", expect.stringContaining("t=120"));
    });

    it("does NOT render a TAG badge for transcript-only video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTranscriptVideo()],
        total: 1,
      });

      renderPage();

      expect(screen.queryByTestId("tag-badge")).not.toBeInTheDocument();
    });
  });

  /**
   * T022: Video with sources: ["tag"] renders teal TAG badge.
   * - No timestamp link (link goes to /videos/{id} without params)
   * - No transcript badge
   */
  describe("T022 — tag-only video", () => {
    it("renders the TAG badge", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTagOnlyVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("tag-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("TAG");
    });

    it("TAG badge has teal styling classes", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTagOnlyVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("tag-badge");
      expect(badge.className).toContain("bg-teal-100");
      expect(badge.className).toContain("text-teal-700");
    });

    it("TAG badge is not a link (no href attribute)", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTagOnlyVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("tag-badge");
      expect(badge.tagName.toLowerCase()).not.toBe("a");
      expect(badge).not.toHaveAttribute("href");
    });

    it("video card link goes to /videos/{id} without timestamp params for tag-only video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTagOnlyVideo({ video_id: "tag-only-vid-001" })],
        total: 1,
      });

      renderPage();

      const link = screen.getByRole("link", { name: /Tag Only Video/i });
      expect(link).toHaveAttribute("href", "/videos/tag-only-vid-001");
      // No segment or timestamp query params
      expect(link).not.toHaveAttribute("href", expect.stringContaining("seg="));
      expect(link).not.toHaveAttribute("href", expect.stringContaining("t="));
    });

    it("does NOT render a TRANSCRIPT badge for tag-only video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTagOnlyVideo()],
        total: 1,
      });

      renderPage();

      expect(screen.queryByTestId("transcript-badge")).not.toBeInTheDocument();
    });
  });

  /**
   * T023: Video with sources: ["transcript", "tag"] renders both badges.
   * - Transcript badge shows mention count
   * - TAG badge shown alongside
   * - Deep link includes timestamp (transcript source is present)
   */
  describe("T023 — mixed-source video (transcript + tag)", () => {
    it("renders both TRANSCRIPT and TAG badges", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMixedSourceVideo({ mention_count: 2 })],
        total: 1,
      });

      renderPage();

      expect(screen.getByTestId("transcript-badge")).toBeInTheDocument();
      expect(screen.getByTestId("tag-badge")).toBeInTheDocument();
    });

    it("TRANSCRIPT badge shows the mention count", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMixedSourceVideo({ mention_count: 2 })],
        total: 1,
      });

      renderPage();

      const transcriptBadge = screen.getByTestId("transcript-badge");
      expect(transcriptBadge).toHaveTextContent("TRANSCRIPT");
      expect(transcriptBadge).toHaveTextContent("2");
    });

    it("video card link includes timestamp deep-link for mixed-source video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createMixedSourceVideo({
            video_id: "mixed-vid-001",
            mentions: [{ segment_id: 55, start_time: 60.0, mention_text: "David Sheen" }],
            first_mention_time: 60.0,
          }),
        ],
        total: 1,
      });

      renderPage();

      const link = screen.getByRole("link", { name: /Mixed Source Video/i });
      expect(link).toHaveAttribute("href", expect.stringContaining("/videos/mixed-vid-001"));
      expect(link).toHaveAttribute("href", expect.stringContaining("seg=55"));
      expect(link).toHaveAttribute("href", expect.stringContaining("t=60"));
    });
  });

  /**
   * T024: Tag-only videos appear after transcript-mention videos in default sort.
   *
   * The backend is responsible for the actual sort order, but we verify that
   * the frontend renders videos in the order returned by the hook (no client-side
   * reordering).  We supply a list with transcript videos first and tag-only
   * videos last, matching the expected backend sort, and verify the DOM order.
   */
  describe("T024 — render order: transcript-mention videos before tag-only videos", () => {
    it("renders transcript videos before tag-only videos as received from the hook", () => {
      const transcriptVideo = createTranscriptVideo({
        video_id: "t-vid",
        video_title: "Transcript Video First",
        mention_count: 5,
        upload_date: "2024-06-20T00:00:00+00:00",
      });
      const tagOnlyVideo = createTagOnlyVideo({
        video_id: "tag-vid",
        video_title: "Tag Only Video Second",
        upload_date: "2024-05-10T00:00:00+00:00",
      });

      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [transcriptVideo, tagOnlyVideo],
        total: 2,
      });

      renderPage();

      const transcriptTitle = screen.getByText("Transcript Video First");
      const tagTitle = screen.getByText("Tag Only Video Second");

      // compareDocumentPosition: 4 means "following" (tagTitle appears after transcriptTitle)
      const position = transcriptTitle.compareDocumentPosition(tagTitle);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("transcript video has TRANSCRIPT badge; tag-only video has TAG badge (not swapped)", () => {
      const transcriptVideo = createTranscriptVideo({
        video_id: "t-vid",
        video_title: "Transcript Video",
        mention_count: 3,
      });
      const tagOnlyVideo = createTagOnlyVideo({
        video_id: "tag-vid",
        video_title: "Tag Only Video",
      });

      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [transcriptVideo, tagOnlyVideo],
        total: 2,
      });

      renderPage();

      // Transcript video card should have transcript badge
      const transcriptBadges = screen.getAllByTestId("transcript-badge");
      expect(transcriptBadges).toHaveLength(1);

      // Tag-only video card should have TAG badge
      const tagBadges = screen.getAllByTestId("tag-badge");
      expect(tagBadges).toHaveLength(1);
    });

    it("all three source types render correctly side by side", () => {
      const transcriptVideo = createTranscriptVideo({
        video_id: "t-vid",
        video_title: "Transcript Only",
        mention_count: 4,
      });
      const mixedVideo = createMixedSourceVideo({
        video_id: "mix-vid",
        video_title: "Both Sources",
        mention_count: 2,
      });
      const tagOnlyVideo = createTagOnlyVideo({
        video_id: "tag-vid",
        video_title: "Tag Only",
      });

      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [transcriptVideo, mixedVideo, tagOnlyVideo],
        total: 3,
      });

      renderPage();

      // 2 transcript badges (transcript-only + mixed)
      expect(screen.getAllByTestId("transcript-badge")).toHaveLength(2);
      // 2 tag badges (mixed + tag-only)
      expect(screen.getAllByTestId("tag-badge")).toHaveLength(2);
    });
  });
});
