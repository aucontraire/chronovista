/**
 * Tests for EntityDetailPage — Feature 054, Phases 7-8 (US4, US5).
 *
 * Coverage (T045-T061):
 *
 * US4 — Per-Video Combined Source Badges (T045-T049):
 * - T045: Video with sources: ["title"] renders amber TITLE badge
 * - T046: Video with sources: ["description"] renders slate DESC badge with context snippet
 * - T047: Video with sources: ["title", "transcript", "tag"] renders all badges in quality order
 * - T048: TITLE and DESC badges are non-clickable with title attributes per FR-035
 * - T049: Description context snippet is italic, truncated to 150 chars with ellipsis,
 *         entity text highlighted with <mark> per FR-034
 *
 * US5 — Source Filter Dropdown (T057-T061):
 * - T057: Source filter dropdown renders with all options
 * - T058: Selecting "Title" filter shows only title-sourced videos
 * - T059: Source filter composes with language filter in URL
 * - T060: Source filter persists in URL ?source=title
 * - T061: Empty state shows "No videos found for this source type." per FR-032
 *
 * Mock strategy follows the existing EntityDetailPage.tag-videos.test.tsx pattern:
 * - `useEntityVideos` (hooks/useEntityMentions) — mocked to control video list
 * - `useQuery` (@tanstack/react-query) — mocked to control entity detail fetch
 * - `PhoneticVariantsSection` — mocked to avoid independent useQuery calls
 * - `ExclusionPatternsSection` — mocked to keep tests focused
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
// Test data factories
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

function createTitleVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "title-vid-001",
    video_title: "David Sheen Documentary Review",
    channel_name: "Test Channel",
    mention_count: 0,
    mentions: [],
    sources: ["title"],
    has_manual: false,
    first_mention_time: null,
    upload_date: "2024-08-01T00:00:00+00:00",
    description_context: null,
    ...overrides,
  };
}

function createDescriptionVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "desc-vid-001",
    video_title: "Middle East Analysis 2024",
    channel_name: "Test Channel",
    mention_count: 0,
    mentions: [],
    sources: ["description"],
    has_manual: false,
    first_mention_time: null,
    upload_date: "2024-07-15T00:00:00+00:00",
    description_context:
      "...featuring journalist David Sheen who has covered Israeli policies in the West Bank for over a decade...",
    ...overrides,
  };
}

function createMultiSourceVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "multi-source-vid-001",
    video_title: "Multi Source Video",
    channel_name: "Test Channel",
    mention_count: 2,
    mentions: [
      { segment_id: 10, start_time: 30.0, mention_text: "David Sheen" },
    ],
    sources: ["title", "transcript", "tag"],
    has_manual: false,
    first_mention_time: 30.0,
    upload_date: "2024-09-01T00:00:00+00:00",
    description_context: null,
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
// Render helpers
// ---------------------------------------------------------------------------

function renderPage(
  entityId = "entity-uuid-001",
  initialSearch = ""
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const initialEntry = `/entities/${entityId}${initialSearch}`;
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
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
// US4 Tests — Per-Video Combined Source Badges (T045-T049)
// ---------------------------------------------------------------------------

describe("EntityDetailPage — source badges (Feature 054, US4)", () => {
  /**
   * T045: Video with sources: ["title"] renders amber TITLE badge.
   */
  describe("T045 — TITLE badge", () => {
    it("renders amber TITLE badge when sources includes 'title'", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTitleVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("title-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("TITLE");
    });

    it("TITLE badge has amber styling classes", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTitleVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("title-badge");
      expect(badge.className).toContain("bg-amber-100");
      expect(badge.className).toContain("text-amber-700");
    });

    it("does NOT render a TRANSCRIPT badge for title-only video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTitleVideo()],
        total: 1,
      });

      renderPage();

      expect(screen.queryByTestId("transcript-badge")).not.toBeInTheDocument();
    });
  });

  /**
   * T046: Video with sources: ["description"] renders slate DESC badge
   * and a description context snippet.
   */
  describe("T046 — DESC badge with context snippet", () => {
    it("renders slate DESC badge when sources includes 'description'", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createDescriptionVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("desc-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("DESC");
    });

    it("DESC badge has slate styling classes", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createDescriptionVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("desc-badge");
      expect(badge.className).toContain("bg-slate-200");
      expect(badge.className).toContain("text-slate-700");
    });

    it("renders description context snippet when description_context is present", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            description_context: "...featuring journalist David Sheen who has covered...",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      expect(snippet).toBeInTheDocument();
      expect(snippet).toHaveTextContent("David Sheen");
    });

    it("does NOT render context snippet when description_context is null", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createDescriptionVideo({ description_context: null })],
        total: 1,
      });

      renderPage();

      expect(screen.queryByTestId("description-context")).not.toBeInTheDocument();
    });
  });

  /**
   * T047: Video with sources: ["title", "transcript", "tag"] renders all badges
   * in quality hierarchy order: TITLE → TRANSCRIPT → TAG.
   */
  describe("T047 — multi-source video with all badges in quality order", () => {
    it("renders TITLE, TRANSCRIPT, and TAG badges for multi-source video", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMultiSourceVideo({ mention_count: 2 })],
        total: 1,
      });

      renderPage();

      expect(screen.getByTestId("title-badge")).toBeInTheDocument();
      expect(screen.getByTestId("transcript-badge")).toBeInTheDocument();
      expect(screen.getByTestId("tag-badge")).toBeInTheDocument();
    });

    it("TITLE badge appears before TRANSCRIPT badge in DOM order", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMultiSourceVideo({ mention_count: 2 })],
        total: 1,
      });

      renderPage();

      const titleBadge = screen.getByTestId("title-badge");
      const transcriptBadge = screen.getByTestId("transcript-badge");

      // compareDocumentPosition: 4 means DOCUMENT_POSITION_FOLLOWING
      // (transcriptBadge follows titleBadge => titleBadge comes first)
      const position = titleBadge.compareDocumentPosition(transcriptBadge);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("TRANSCRIPT badge appears before TAG badge in DOM order", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createMultiSourceVideo({ mention_count: 2 })],
        total: 1,
      });

      renderPage();

      const transcriptBadge = screen.getByTestId("transcript-badge");
      const tagBadge = screen.getByTestId("tag-badge");

      const position = transcriptBadge.compareDocumentPosition(tagBadge);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("renders DESC badge before MANUAL badge in DOM order", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            video_id: "desc-manual-vid",
            sources: ["description", "manual"],
            has_manual: true,
          }),
        ],
        total: 1,
      });

      renderPage();

      const descBadge = screen.getByTestId("desc-badge");
      const manualBadge = screen.getByTestId("manual-badge");

      const position = descBadge.compareDocumentPosition(manualBadge);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
  });

  /**
   * T048: TITLE and DESC badges are non-clickable (no href, no cursor-pointer)
   * with title attributes per FR-035.
   */
  describe("T048 — TITLE and DESC badges are non-clickable with title attributes", () => {
    it("TITLE badge is not a link element", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTitleVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("title-badge");
      expect(badge.tagName.toLowerCase()).not.toBe("a");
      expect(badge).not.toHaveAttribute("href");
    });

    it("TITLE badge has title attribute per FR-035", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createTitleVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("title-badge");
      expect(badge).toHaveAttribute("title", "Entity found in video title");
    });

    it("DESC badge is not a link element", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createDescriptionVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("desc-badge");
      expect(badge.tagName.toLowerCase()).not.toBe("a");
      expect(badge).not.toHaveAttribute("href");
    });

    it("DESC badge has title attribute per FR-035", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [createDescriptionVideo()],
        total: 1,
      });

      renderPage();

      const badge = screen.getByTestId("desc-badge");
      expect(badge).toHaveAttribute("title", "Entity found in video description");
    });
  });

  /**
   * T049: Description context snippet is italic, truncated to 150 chars with
   * ellipsis, entity text highlighted with <mark> per FR-034.
   */
  describe("T049 — description context snippet formatting", () => {
    it("context snippet paragraph has italic styling", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            description_context: "Featuring David Sheen in this analysis.",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      expect(snippet.className).toContain("italic");
    });

    it("context snippet is truncated at 150 chars with ellipsis for long text", () => {
      // Create a description context that is clearly over 150 chars
      const longContext =
        "A".repeat(80) + " David Sheen " + "B".repeat(80);

      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({ description_context: longContext }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      // The rendered text content should end with "..."
      expect(snippet.textContent).toMatch(/\.\.\.$/);
      // Full text (without the ellipsis) should not exceed 153 chars
      expect(snippet.textContent!.length).toBeLessThanOrEqual(153);
    });

    it("context snippet does NOT add ellipsis for text under 150 chars", () => {
      const shortContext = "Brief mention of David Sheen in the text.";

      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({ description_context: shortContext }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      expect(snippet.textContent).not.toMatch(/\.\.\.$/);
    });

    it("entity name is highlighted with <mark> inside the context snippet", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            description_context: "Featuring David Sheen in this analysis.",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      // The entity name should be wrapped in a <mark> element
      const markEl = snippet.querySelector("mark");
      expect(markEl).toBeTruthy();
      expect(markEl?.textContent).toBe("David Sheen");
    });

    it("mark element has bg-yellow-100 styling", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            description_context: "Analysis by David Sheen.",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      const markEl = snippet.querySelector("mark");
      expect(markEl?.className).toContain("bg-yellow-100");
    });
  });
});

// ---------------------------------------------------------------------------
// US5 Tests — Source Filter Dropdown (T057-T061)
// ---------------------------------------------------------------------------

describe("EntityDetailPage — source filter dropdown (Feature 054, US5)", () => {
  /**
   * T057: Source filter dropdown renders with all expected options.
   */
  describe("T057 — source filter dropdown renders with all options", () => {
    it("renders a source filter dropdown", () => {
      renderPage();

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      });
      expect(dropdown).toBeInTheDocument();
    });

    it("dropdown has All sources, Title, Transcript, Tag, Description, Manual options", () => {
      renderPage();

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      });

      const options = Array.from(
        (dropdown as HTMLSelectElement).options
      ).map((o) => o.text);

      expect(options).toContain("All sources");
      expect(options).toContain("Title");
      expect(options).toContain("Transcript");
      expect(options).toContain("Tag");
      expect(options).toContain("Description");
      expect(options).toContain("Manual");
    });

    it("dropdown defaults to 'All sources' when no source param in URL", () => {
      renderPage();

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      }) as HTMLSelectElement;

      expect(dropdown.value).toBe("");
    });
  });

  /**
   * T058: Selecting "Title" filter shows only title-sourced videos.
   * (We verify the hook is called with the correct param.)
   */
  describe("T058 — selecting a source filter updates the hook params", () => {
    it("passes source='title' to useEntityVideos when Title option selected", () => {
      renderPage();

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      });

      fireEvent.change(dropdown, { target: { value: "title" } });

      // Verify the hook was called with source param
      const calls = vi.mocked(useEntityVideos).mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[1]).toEqual({ source: "title" });
    });

    it("passes no source param to useEntityVideos when All sources selected", () => {
      // Start with a source filter set
      renderPage("entity-uuid-001", "?source=title");

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      });

      fireEvent.change(dropdown, { target: { value: "" } });

      const calls = vi.mocked(useEntityVideos).mock.calls;
      const lastCall = calls[calls.length - 1];
      // When cleared, params should be empty object (no source key)
      expect(lastCall?.[1]).toEqual({});
    });
  });

  /**
   * T059: Source filter composes with language filter (both live in URL params).
   */
  describe("T059 — source filter composes with language filter in URL", () => {
    it("pre-existing source param is read from URL on mount", () => {
      // Render with ?source=description in the URL
      renderPage("entity-uuid-001", "?source=description");

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      }) as HTMLSelectElement;

      expect(dropdown.value).toBe("description");
    });

    it("useEntityVideos receives the source from URL on initial render", () => {
      renderPage("entity-uuid-001", "?source=transcript");

      // The first call to useEntityVideos should include source: "transcript"
      const firstCall = vi.mocked(useEntityVideos).mock.calls[0];
      expect(firstCall?.[1]).toEqual({ source: "transcript" });
    });
  });

  /**
   * T060: Source filter persists in URL query parameter ?source=title.
   * (Verified by checking dropdown value reflects URL state.)
   */
  describe("T060 — source filter persists in URL", () => {
    it("source=title URL param sets dropdown to Title", () => {
      renderPage("entity-uuid-001", "?source=title");

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      }) as HTMLSelectElement;

      expect(dropdown.value).toBe("title");
    });

    it("source=manual URL param sets dropdown to Manual", () => {
      renderPage("entity-uuid-001", "?source=manual");

      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      }) as HTMLSelectElement;

      expect(dropdown.value).toBe("manual");
    });
  });

  /**
   * T061: Empty state shows "No videos found for this source type."
   * when source filter yields zero results, with "Try All sources" link.
   */
  describe("T061 — empty state for source-filtered zero results", () => {
    it("shows source-specific empty message when source filter active and no videos", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=title");

      expect(
        screen.getByText("No videos found for this source type.")
      ).toBeInTheDocument();
    });

    it("shows 'Try All sources' button in source-filtered empty state", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=title");

      expect(screen.getByText("Try All sources")).toBeInTheDocument();
    });

    it("shows generic empty message when no source filter is active", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage(); // no source filter

      expect(
        screen.getByText("No videos found for this entity.")
      ).toBeInTheDocument();
      expect(screen.queryByText("Try All sources")).not.toBeInTheDocument();
    });

    it("clicking 'Try All sources' clears the source filter", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=manual");

      const clearButton = screen.getByText("Try All sources");
      fireEvent.click(clearButton);

      // After clicking, dropdown should be back to "All sources"
      const dropdown = screen.getByRole("combobox", {
        name: /filter videos by source/i,
      }) as HTMLSelectElement;

      expect(dropdown.value).toBe("");
    });
  });
});
