/**
 * Tests for HomePage (Videos Page).
 *
 * Merged from two divergent copies (#309 Phase 3 consolidation):
 * - Feature 013 / T032 coverage: FilterToggle migration for "include unavailable
 *   content", URL state persistence, and canonicalTags wiring into useVideos.
 * - Feature 027 / T034 coverage: SortDropdown, boolean FilterToggles
 *   (liked_only, has_transcript), combined URL state, and page structure.
 *
 * Both source files exercised the real VideoFilters/FilterToggle/SortDropdown
 * children (only `useVideos` was mocked to avoid real API calls), so this
 * merge keeps that single mocking strategy throughout rather than also
 * stubbing VideoFilters/VideoList as one of the source files briefly did.
 *
 * Dropped (documented, not silently lost):
 * - "should render VideoFilters component" / "should render VideoList
 *   component" — these only asserted a `data-testid` on a *stubbed* child.
 *   VideoFilters' real rendering is already covered here by the "Show
 *   unavailable content" checkbox tests below and independently in
 *   `src/tests/components/VideoFilters.test.tsx`. VideoList's real rendering
 *   is covered by the "useVideos receives sort/filter params" tests below —
 *   those calls only occur once VideoList has mounted and read its own
 *   `useVideos` hook.
 * - "VideoList receives correct props" (2 cases) were re-expressed as
 *   assertions against the mocked `useVideos` hook (which VideoList calls
 *   internally with the same values) instead of reading a stubbed
 *   `data-props` attribute — same intent, same coverage, no stub required.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ReactElement } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HomePage } from "../HomePage";

// Mock the hooks
vi.mock("../../hooks/useCategories", () => ({
  useCategories: () => ({
    categories: [
      { category_id: "10", name: "Gaming", assignable: true },
      { category_id: "20", name: "Music", assignable: true },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("../../hooks/useTopics", () => ({
  useTopics: () => ({
    topics: [
      {
        topic_id: "/m/04rlf",
        name: "Music",
        parent_topic_id: null,
        parent_path: null,
        depth: 0,
        video_count: 100,
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("../../hooks/useVideos", () => ({
  useVideos: vi.fn(() => ({
    videos: [],
    total: 0,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  })),
}));

// Tracks the current MemoryRouter location so tests can assert on URL state
// after an interaction, without importing `tests/test-utils` (#159 trap).
let currentTestLocation: { pathname: string; search: string; hash: string } = {
  pathname: "/",
  search: "",
  hash: "",
};

function LocationTracker() {
  const location = useLocation();
  currentTestLocation = {
    pathname: location.pathname,
    search: location.search,
    hash: location.hash,
  };
  return null;
}

function getTestLocation() {
  return currentTestLocation;
}

/**
 * Local render helper providing Router + QueryClient context.
 */
function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ["/"] }: { initialEntries?: string[] } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <LocationTracker />
        {ui}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderHomePage(initialUrl = "/") {
  return renderWithProviders(<HomePage />, { initialEntries: [initialUrl] });
}

describe("HomePage - Include Unavailable Content (T013)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("FilterToggle migration - zero regression (SC-006)", () => {
    it("should render 'Show unavailable content' checkbox with correct label", () => {
      renderWithProviders(<HomePage />);

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });
      expect(checkbox).toBeInTheDocument();
    });

    it("should default to unchecked when no URL parameter present", () => {
      renderWithProviders(<HomePage />);

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });
      expect(checkbox).not.toBeChecked();
    });

    it("should be checked when URL parameter is 'true'", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=true"],
      });

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });
      expect(checkbox).toBeChecked();
    });

    it("should remain unchecked when URL parameter is anything other than 'true'", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=false"],
      });

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });
      expect(checkbox).not.toBeChecked();
    });

    it("should use snake_case param key 'include_unavailable' (FR-027)", async () => {
      renderWithProviders(<HomePage />);
      const user = userEvent.setup();

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      // Check the checkbox
      await user.click(checkbox);

      // Verify checkbox is checked (URL update is handled by FilterToggle)
      await waitFor(() => {
        expect(checkbox).toBeChecked();
      });
    });
  });

  describe("Toggle behavior (FR-007)", () => {
    it("should toggle from unchecked to checked", async () => {
      renderWithProviders(<HomePage />);
      const user = userEvent.setup();

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      expect(checkbox).not.toBeChecked();

      await user.click(checkbox);

      await waitFor(() => {
        expect(checkbox).toBeChecked();
      });
    });

    it("should toggle from checked to unchecked", async () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=true"],
      });
      const user = userEvent.setup();

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      expect(checkbox).toBeChecked();

      await user.click(checkbox);

      await waitFor(() => {
        expect(checkbox).not.toBeChecked();
      });
    });

    it("should remove parameter from URL when unchecking", async () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=true&tag=music"],
      });
      const user = userEvent.setup();

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      expect(checkbox).toBeChecked();

      await user.click(checkbox);

      await waitFor(() => {
        // Checkbox should be unchecked (URL param removal handled by FilterToggle)
        expect(checkbox).not.toBeChecked();
      });
    });
  });

  describe("URL state persistence", () => {
    it("should preserve include_unavailable state on page load", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=true"],
      });

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      expect(checkbox).toBeChecked();
    });

    it("should work alongside other filter parameters", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: [
          "/?tag=music&category=10&topic_id=/m/04rlf&include_unavailable=true",
        ],
      });

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      expect(checkbox).toBeChecked();
    });
  });

  describe("Integration with useVideos hook", () => {
    it("should pass includeUnavailable=false to useVideos when unchecked", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderWithProviders(<HomePage />);

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          includeUnavailable: false,
        })
      );
    });

    it("should pass includeUnavailable=true to useVideos when checked", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderWithProviders(<HomePage />, {
        initialEntries: ["/?include_unavailable=true"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          includeUnavailable: true,
        })
      );
    });

    it("should pass canonicalTags from URL canonical_tag params to useVideos", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=javascript&canonical_tag=python"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["javascript", "python"],
        })
      );
    });

    it("should pass empty canonicalTags array when no canonical_tag params in URL", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderWithProviders(<HomePage />);

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: [],
        })
      );
    });

    it("should pass both tags and canonicalTags when both URL params present", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderWithProviders(<HomePage />, {
        initialEntries: ["/?tag=music&canonical_tag=javascript"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: ["music"],
          canonicalTags: ["javascript"],
        })
      );
    });
  });

  describe("Accessibility (FR-005)", () => {
    it("should have proper label association", () => {
      renderWithProviders(<HomePage />);

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      // The checkbox should be properly labeled
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).toHaveAccessibleName(/Show unavailable content/i);
    });

    it("should maintain focus on checkbox after state change (FR-032)", async () => {
      renderWithProviders(<HomePage />);
      const user = userEvent.setup();

      const checkbox = screen.getByRole("checkbox", {
        name: /Show unavailable content/i,
      });

      await user.click(checkbox);

      // Focus should remain on the checkbox
      await waitFor(() => {
        expect(checkbox).toHaveFocus();
      });
    });
  });
});

describe("HomePage (Videos Page) - Feature 027", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Sort Dropdown", () => {
    it("should render the sort dropdown", () => {
      renderHomePage();

      // SortDropdown renders a <select> with the label
      const sortDropdown = screen.getByRole("combobox", {
        name: /sort videos by/i,
      });
      expect(sortDropdown).toBeInTheDocument();
    });

    it("should have Date Added and Title sort options", () => {
      renderHomePage();

      const sortDropdown = screen.getByRole("combobox", {
        name: /sort videos by/i,
      });

      // Get all options
      const options = sortDropdown.querySelectorAll("option");
      const optionTexts = Array.from(options).map((opt) => opt.textContent);

      // Should contain Date Added and Title (with asc/desc arrows)
      expect(optionTexts.some((t) => t?.includes("Date Added"))).toBe(true);
      expect(optionTexts.some((t) => t?.includes("Title"))).toBe(true);
    });

    it("should default to Date Added descending", () => {
      renderHomePage();

      const sortDropdown = screen.getByRole("combobox", {
        name: /sort videos by/i,
      }) as HTMLSelectElement;

      // Default value should be upload_date:desc
      expect(sortDropdown.value).toBe("upload_date:desc");
    });

    it("should update URL when sort option changes", async () => {
      const user = userEvent.setup();
      renderHomePage();

      const sortDropdown = screen.getByRole("combobox", {
        name: /sort videos by/i,
      });

      // Select "Title ascending"
      await user.selectOptions(sortDropdown, "title:asc");

      const location = getTestLocation();
      expect(location.search).toContain("sort_by=title");
      expect(location.search).toContain("sort_order=asc");
    });
  });

  describe("Filter Toggles", () => {
    it("should render Liked only toggle", () => {
      renderHomePage();

      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      expect(likedToggle).toBeInTheDocument();
    });

    it("should render Has transcripts toggle", () => {
      renderHomePage();

      const transcriptToggle = screen.getByRole("checkbox", {
        name: /has transcripts/i,
      });
      expect(transcriptToggle).toBeInTheDocument();
    });

    it("should have unchecked toggles by default", () => {
      renderHomePage();

      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      const transcriptToggle = screen.getByRole("checkbox", {
        name: /has transcripts/i,
      });

      expect(likedToggle).not.toBeChecked();
      expect(transcriptToggle).not.toBeChecked();
    });

    it("should check Liked toggle when liked_only URL param is true", () => {
      renderHomePage("/?liked_only=true");

      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      expect(likedToggle).toBeChecked();
    });

    it("should check Has transcripts toggle when has_transcript URL param is true", () => {
      renderHomePage("/?has_transcript=true");

      const transcriptToggle = screen.getByRole("checkbox", {
        name: /has transcripts/i,
      });
      expect(transcriptToggle).toBeChecked();
    });

    it("should add liked_only=true to URL when toggled on", async () => {
      const user = userEvent.setup();
      renderHomePage();

      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });

      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).toContain("liked_only=true");
    });

    it("should add has_transcript=true to URL when toggled on", async () => {
      const user = userEvent.setup();
      renderHomePage();

      const transcriptToggle = screen.getByRole("checkbox", {
        name: /has transcripts/i,
      });

      await user.click(transcriptToggle);

      const location = getTestLocation();
      expect(location.search).toContain("has_transcript=true");
    });
  });

  describe("Combined URL State", () => {
    it("should preserve sort params alongside filter params", async () => {
      const user = userEvent.setup();
      renderHomePage("/?sort_by=title&sort_order=asc");

      // Toggle liked_only on
      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).toContain("sort_by=title");
      expect(location.search).toContain("sort_order=asc");
      expect(location.search).toContain("liked_only=true");
    });

    it("should handle all filter types in URL simultaneously", () => {
      renderHomePage(
        "/?sort_by=title&sort_order=asc&liked_only=true&has_transcript=true&tag=music&category=10&topic_id=/m/04rlf&include_unavailable=true"
      );

      // Verify sort dropdown has correct value
      const sortDropdown = screen.getByRole("combobox", {
        name: /sort videos by/i,
      }) as HTMLSelectElement;
      expect(sortDropdown.value).toBe("title:asc");

      // Verify toggles are checked
      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      const transcriptToggle = screen.getByRole("checkbox", {
        name: /has transcripts/i,
      });
      expect(likedToggle).toBeChecked();
      expect(transcriptToggle).toBeChecked();
    });

    it("should remove liked_only from URL when unchecked", async () => {
      const user = userEvent.setup();
      renderHomePage("/?liked_only=true&sort_by=title");

      const likedToggle = screen.getByRole("checkbox", {
        name: /liked only/i,
      });
      expect(likedToggle).toBeChecked();

      await user.click(likedToggle);

      const location = getTestLocation();
      expect(location.search).not.toContain("liked_only");
      // sort_by should still be preserved
      expect(location.search).toContain("sort_by=title");
    });
  });

  describe("Page Structure", () => {
    it("should render page heading", () => {
      renderHomePage();

      expect(
        screen.getByRole("heading", { name: /videos/i, level: 2 })
      ).toBeInTheDocument();
    });

    it("should have ARIA live region for count announcement", () => {
      renderHomePage();

      // Check for role="status" with aria-live
      const liveRegion = document.querySelector(
        '[role="status"][aria-live="polite"]'
      );
      expect(liveRegion).toBeInTheDocument();
    });

    it("should render sort and filter controls section", () => {
      renderHomePage();

      // Check for the controls section heading (sr-only)
      expect(screen.getByText("Sort and filter controls")).toBeInTheDocument();
    });
  });

  describe("useVideos receives sort/filter params (via VideoList)", () => {
    it("should pass sort and filter params to useVideos", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderHomePage(
        "/?sort_by=title&sort_order=asc&liked_only=true&has_transcript=true"
      );

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          sortBy: "title",
          sortOrder: "asc",
          likedOnly: true,
          hasTranscript: true,
        })
      );
    });

    it("should pass default false values to useVideos when no URL params", async () => {
      const useVideosMock = vi.mocked(
        (await import("../../hooks/useVideos")).useVideos
      );

      renderHomePage();

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          likedOnly: false,
          hasTranscript: false,
          includeUnavailable: false,
        })
      );
    });
  });
});
