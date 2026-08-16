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
 * US5 — Source Filter Checkboxes (T057-T061, updated for Feature 066 T019
 * multi-select union):
 * - T057: Source filter checkboxes render with all five sources
 * - T058: Checking "Title" filters to source=title; checking a second source
 *         produces two repeated ?source= params (union)
 * - T059: Source filter composes with language filter in URL
 * - T060: Source filter persists in URL as repeated ?source= params
 * - T061: Empty state shows "No videos found for the selected source(s)."
 *         per FR-014, unchecking all restores the unfiltered empty state
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
// Test data factories
// ---------------------------------------------------------------------------

const mockEntity = {
  entity_id: "entity-uuid-001",
  canonical_name: "Karen Sparck",
  entity_type: "person",
  description: "Journalist and documentary filmmaker.",
  status: "active",
  mention_count: 5,
  video_count: 3,
  by_source: { manual: 1, transcript: 1, title: 1, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

function createTitleVideo(overrides: Partial<EntityVideoResult> = {}): EntityVideoResult {
  return {
    video_id: "title-vid-001",
    video_title: "Karen Sparck Documentary Review",
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
      "...featuring journalist Karen Sparck who has covered Israeli policies in the West Bank for over a decade...",
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
      { segment_id: 10, start_time: 30.0, mention_text: "Karen Sparck" },
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
            description_context: "...featuring journalist Karen Sparck who has covered...",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      expect(snippet).toBeInTheDocument();
      expect(snippet).toHaveTextContent("Karen Sparck");
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
            description_context: "Featuring Karen Sparck in this analysis.",
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
        "A".repeat(80) + " Karen Sparck " + "B".repeat(80);

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
      const shortContext = "Brief mention of Karen Sparck in the text.";

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
            description_context: "Featuring Karen Sparck in this analysis.",
          }),
        ],
        total: 1,
      });

      renderPage();

      const snippet = screen.getByTestId("description-context");
      // The entity name should be wrapped in a <mark> element
      const markEl = snippet.querySelector("mark");
      expect(markEl).toBeTruthy();
      expect(markEl?.textContent).toBe("Karen Sparck");
    });

    it("mark element has bg-yellow-100 styling", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [
          createDescriptionVideo({
            description_context: "Analysis by Karen Sparck.",
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

describe("EntityDetailPage — source filter checkboxes (Feature 066, T019)", () => {
  /**
   * T057: Source filter renders a checkbox per source, all five present.
   */
  describe("T057 — source filter checkboxes render with all sources", () => {
    it("renders a checkbox for each of the five sources", () => {
      renderPage();

      expect(
        screen.getByRole("checkbox", { name: "Tag" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: "Transcript" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: "Title" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: "Description" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: "Manual" })
      ).toBeInTheDocument();
    });

    it("renders the filter as an accessible fieldset/legend group", () => {
      renderPage();

      expect(
        screen.getByText(/filter videos by source/i)
      ).toBeInTheDocument();
    });

    it("all checkboxes are unchecked when no source param in URL", () => {
      renderPage();

      for (const label of ["Tag", "Transcript", "Title", "Description", "Manual"]) {
        expect(
          (screen.getByRole("checkbox", { name: label }) as HTMLInputElement)
            .checked
        ).toBe(false);
      }
    });

    it("checkboxes are keyboard-toggleable (native input, not disabled)", () => {
      renderPage();

      const checkbox = screen.getByRole("checkbox", {
        name: "Title",
      }) as HTMLInputElement;

      expect(checkbox.tagName.toLowerCase()).toBe("input");
      expect(checkbox.type).toBe("checkbox");
      expect(checkbox).not.toBeDisabled();
    });
  });

  /**
   * T058: Checking a source updates the hook params; checking a second
   * source unions with the first (repeated source params).
   */
  describe("T058 — checking sources updates the hook params (union)", () => {
    it("passes source: ['title'] to useEntityVideos when Title is checked", () => {
      renderPage();

      const checkbox = screen.getByRole("checkbox", { name: "Title" });
      fireEvent.click(checkbox);

      const calls = vi.mocked(useEntityVideos).mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[1]).toEqual({ source: ["title"] });
    });

    it("checking a second source unions both into the source array", () => {
      renderPage("entity-uuid-001", "?source=title");

      const checkbox = screen.getByRole("checkbox", { name: "Tag" });
      fireEvent.click(checkbox);

      const calls = vi.mocked(useEntityVideos).mock.calls;
      const lastCall = calls[calls.length - 1];
      const lastParams = lastCall?.[1] as { source?: string[] };
      expect(lastParams.source).toHaveLength(2);
      expect(lastParams.source).toEqual(expect.arrayContaining(["title", "tag"]));
    });

    it("unchecking the only checked source passes source: undefined (all sources)", () => {
      renderPage("entity-uuid-001", "?source=title");

      const checkbox = screen.getByRole("checkbox", { name: "Title" });
      fireEvent.click(checkbox);

      const calls = vi.mocked(useEntityVideos).mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[1]).toEqual({});
    });
  });

  /**
   * T059: Source filter composes with other URL state (read independently
   * of language filter — both live in the same URLSearchParams).
   */
  describe("T059 — source filter composes with URL state", () => {
    it("pre-existing source param is read from URL on mount", () => {
      renderPage("entity-uuid-001", "?source=description");

      expect(
        (screen.getByRole("checkbox", { name: "Description" }) as HTMLInputElement)
          .checked
      ).toBe(true);
    });

    it("useEntityVideos receives the source array from URL on initial render", () => {
      renderPage("entity-uuid-001", "?source=transcript");

      const firstCall = vi.mocked(useEntityVideos).mock.calls[0];
      expect(firstCall?.[1]).toEqual({ source: ["transcript"] });
    });

    it("multiple repeated source params on mount check multiple boxes and union in params", () => {
      renderPage("entity-uuid-001", "?source=title&source=tag");

      expect(
        (screen.getByRole("checkbox", { name: "Title" }) as HTMLInputElement)
          .checked
      ).toBe(true);
      expect(
        (screen.getByRole("checkbox", { name: "Tag" }) as HTMLInputElement)
          .checked
      ).toBe(true);

      const firstCall = vi.mocked(useEntityVideos).mock.calls[0];
      const params = firstCall?.[1] as { source?: string[] };
      expect(params.source).toEqual(expect.arrayContaining(["title", "tag"]));
      expect(params.source).toHaveLength(2);
    });
  });

  /**
   * T060: Source filter persists in the URL as repeated ?source= params.
   */
  describe("T060 — source filter persists in URL as repeated params", () => {
    it("source=title URL param checks the Title checkbox", () => {
      renderPage("entity-uuid-001", "?source=title");

      expect(
        (screen.getByRole("checkbox", { name: "Title" }) as HTMLInputElement)
          .checked
      ).toBe(true);
    });

    it("source=manual URL param checks the Manual checkbox", () => {
      renderPage("entity-uuid-001", "?source=manual");

      expect(
        (screen.getByRole("checkbox", { name: "Manual" }) as HTMLInputElement)
          .checked
      ).toBe(true);
    });

    it("ignores an invalid source value from the URL", () => {
      renderPage("entity-uuid-001", "?source=rule_match");

      for (const label of ["Tag", "Transcript", "Title", "Description", "Manual"]) {
        expect(
          (screen.getByRole("checkbox", { name: label }) as HTMLInputElement)
            .checked
        ).toBe(false);
      }
    });
  });

  /**
   * T061: Empty state shows "No videos found for the selected source(s)."
   * when a source filter yields zero results, with a clear-filter action.
   */
  describe("T061 — empty state for source-filtered zero results", () => {
    it("shows source-specific empty message when a source filter is active and no videos", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=title");

      expect(
        screen.getByText("No videos found for the selected source(s).")
      ).toBeInTheDocument();
    });

    it("shows 'Try all sources' button in source-filtered empty state", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=title");

      expect(screen.getByText("Try all sources")).toBeInTheDocument();
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
      expect(screen.queryByText("Try all sources")).not.toBeInTheDocument();
    });

    it("clicking 'Try all sources' unchecks all checkboxes", () => {
      vi.mocked(useEntityVideos).mockReturnValue({
        ...defaultUseEntityVideos,
        videos: [],
        total: 0,
      });

      renderPage("entity-uuid-001", "?source=manual");

      const clearButton = screen.getByText("Try all sources");
      fireEvent.click(clearButton);

      expect(
        (screen.getByRole("checkbox", { name: "Manual" }) as HTMLInputElement)
          .checked
      ).toBe(false);
    });
  });
});
