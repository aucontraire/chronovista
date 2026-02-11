/**
 * Phase 6 Tests for SearchPage Component
 *
 * T036: Parallel Loading Tests
 * T037: ARIA Announcement Tests
 * T038: Static Results Tests
 *
 * Tests independent section rendering, ARIA announcements, and static vs. infinite scroll behavior.
 *
 * @see FR-005: Independent section loading
 * @see FR-006: Section loading indicators
 * @see FR-007: Section error handling
 * @see FR-018: Per-type result announcements
 * @see FR-026: ARIA live region announcements
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { SearchPage } from "../../src/pages/SearchPage";
import { apiFetch } from "../../src/api/config";
import type {
  SearchResponse,
  TitleSearchResponse,
  DescriptionSearchResponse,
} from "../../src/types/search";

// Helper to wait for debounce (300ms)
const waitForDebounce = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 350));
  });

// Mock the API fetch function
vi.mock("../../src/api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = vi.mocked(apiFetch);

/**
 * Factory for creating mock segment search responses.
 */
function createMockSegmentResponse(
  overrides: Partial<SearchResponse> = {}
): SearchResponse {
  return {
    data: [
      {
        segment_id: 1,
        video_id: "abc123",
        video_title: "Machine Learning Basics",
        channel_title: "Tech Academy",
        language_code: "en",
        text: "Machine learning is a subset of artificial intelligence.",
        start_time: 10.0,
        end_time: 15.0,
        context_before: null,
        context_after: null,
        match_count: 1,
        video_upload_date: "2024-01-15T12:00:00Z",
      },
    ],
    pagination: {
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
    available_languages: ["en"],
    ...overrides,
  };
}

/**
 * Factory for creating mock title search responses.
 */
function createMockTitleResponse(
  overrides: Partial<TitleSearchResponse> = {}
): TitleSearchResponse {
  return {
    data: [
      {
        video_id: "title123",
        title: "Introduction to Machine Learning",
        channel_title: "ML Channel",
        upload_date: "2024-01-10T10:00:00Z",
      },
    ],
    total_count: 1,
    ...overrides,
  };
}

/**
 * Factory for creating mock description search responses.
 */
function createMockDescriptionResponse(
  overrides: Partial<DescriptionSearchResponse> = {}
): DescriptionSearchResponse {
  return {
    data: [
      {
        video_id: "desc123",
        title: "Python Machine Learning Tutorial",
        channel_title: "Code Channel",
        upload_date: "2024-01-12T14:00:00Z",
        snippet: "Learn machine learning with Python...",
      },
    ],
    total_count: 1,
    ...overrides,
  };
}

describe("SearchPage Phase 6 Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockReset();
  });

  describe("T036: Parallel Loading Tests", () => {
    it("should render sections independently when one loads faster than others", async () => {
      // Title search returns immediately, transcript search is slow
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ total_count: 3 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ total_count: 12 });
        }
        if (url.includes("/search/segments")) {
          // Slow response
          await new Promise((resolve) => setTimeout(resolve, 500));
          return createMockSegmentResponse({
            pagination: { total: 847, limit: 20, offset: 0, has_more: true },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");
      await waitForDebounce();

      // Title and description sections should render with results while transcripts still loading
      await waitFor(() => {
        expect(
          screen.getByRole("heading", {
            name: /Introduction to Machine Learning/i,
          })
        ).toBeInTheDocument();
      });
      expect(
        screen.getByRole("heading", {
          name: /Python Machine Learning Tutorial/i,
        })
      ).toBeInTheDocument();

      // Transcripts section should show loading
      expect(screen.getByText("Searching transcripts...")).toBeInTheDocument();

      // Wait for transcript results
      await waitFor(
        () => {
          expect(screen.getByText("Machine Learning Basics")).toBeInTheDocument();
        },
        { timeout: 1000 }
      );

      // Loading state should be gone
      expect(
        screen.queryByText("Searching transcripts...")
      ).not.toBeInTheDocument();
    });

    it("should display correct loading indicator per section", async () => {
      // All slow, but different speeds
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          await new Promise((resolve) => setTimeout(resolve, 200));
          return createMockTitleResponse();
        }
        if (url.includes("/search/descriptions")) {
          await new Promise((resolve) => setTimeout(resolve, 300));
          return createMockDescriptionResponse();
        }
        if (url.includes("/search/segments")) {
          await new Promise((resolve) => setTimeout(resolve, 400));
          return createMockSegmentResponse();
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // All three should show loading initially
      await waitFor(() => {
        expect(screen.getByText("Searching titles...")).toBeInTheDocument();
      });
      expect(screen.getByText("Searching descriptions...")).toBeInTheDocument();
      expect(screen.getByText("Searching transcripts...")).toBeInTheDocument();

      // Title should finish first
      await waitFor(
        () => {
          expect(
            screen.queryByText("Searching titles...")
          ).not.toBeInTheDocument();
        },
        { timeout: 500 }
      );

      // Description should still be loading
      expect(screen.getByText("Searching descriptions...")).toBeInTheDocument();

      // Wait for all to complete
      await waitFor(
        () => {
          expect(
            screen.queryByText("Searching descriptions...")
          ).not.toBeInTheDocument();
          expect(
            screen.queryByText("Searching transcripts...")
          ).not.toBeInTheDocument();
        },
        { timeout: 1000 }
      );
    });

    it("should show error in one section without blocking others", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error",
        status: undefined,
      };

      // Title search fails, but description and transcript succeed
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          throw mockError;
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse();
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse();
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Title section should show error
      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load video titles results/)
        ).toBeInTheDocument();
      });

      // Description and transcript sections should show results
      expect(
        screen.getByRole("heading", {
          name: /Python Machine Learning Tutorial/i,
        })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: /Machine Learning Basics/i })
      ).toBeInTheDocument();
    });

    it("should retry only the failed section when retry is clicked", async () => {
      const mockError = {
        type: "server" as const,
        message: "Server error",
        status: 500,
      };

      let titleCallCount = 0;

      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          titleCallCount++;
          if (titleCallCount === 1) {
            throw mockError;
          }
          // Second call (after retry) succeeds
          return createMockTitleResponse();
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse();
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse();
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for error to appear
      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load video titles results/)
        ).toBeInTheDocument();
      });

      // Find and click retry button in title section
      const retryButtons = screen.getAllByRole("button", { name: /retry/i });
      const titleRetryButton = retryButtons.find((btn) => {
        const section = btn.closest("section");
        return section?.textContent?.includes("Video Titles");
      });

      expect(titleRetryButton).toBeDefined();
      await user.click(titleRetryButton!);

      // Title section should now show results
      await waitFor(() => {
        expect(
          screen.getByRole("heading", {
            name: /Introduction to Machine Learning/i,
          })
        ).toBeInTheDocument();
      });

      // Should not have re-fetched description or transcripts
      const descriptionCalls = mockApiFetch.mock.calls.filter((call) =>
        call[0].includes("/search/descriptions")
      );
      const segmentCalls = mockApiFetch.mock.calls.filter((call) =>
        call[0].includes("/search/segments")
      );

      // Each non-failed endpoint called exactly once
      expect(descriptionCalls).toHaveLength(1);
      expect(segmentCalls).toHaveLength(1);

      // Title called twice (initial fail + retry)
      expect(titleCallCount).toBe(2);
    });
  });

  describe("T037: ARIA Announcement Tests", () => {
    it("should announce combined per-type counts after all sections resolve", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ total_count: 3 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ total_count: 12 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            pagination: { total: 847, limit: 20, offset: 0, has_more: true },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");
      await waitForDebounce();

      // Wait for all results to load
      await waitFor(() => {
        expect(
          screen.getByRole("heading", {
            name: /Introduction to Machine Learning/i,
          })
        ).toBeInTheDocument();
      });

      // Check ARIA live region announcement
      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();

      // Should announce: "Found 3 title, 12 description, and 847 transcript matches for 'machine learning'"
      await waitFor(() => {
        const text = liveRegion?.textContent || "";
        expect(text).toContain("3 title");
        expect(text).toContain("12 description");
        expect(text).toContain("847 transcript");
        expect(text).toContain("machine learning");
      });
    });

    it("should exclude disabled types from announcement", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ total_count: 5 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ total_count: 10 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            pagination: { total: 20, limit: 20, offset: 0, has_more: false },
          });
        }
        return createMockSegmentResponse();
      });

      // Initialize with titles disabled
      const { user } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search?types=descriptions,transcripts"],
        path: "/search",
      });

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for results
      await waitFor(() => {
        expect(
          screen.getByRole("heading", {
            name: /Python Machine Learning Tutorial/i,
          })
        ).toBeInTheDocument();
      });

      const liveRegion = document.querySelector('[aria-live="polite"]');

      // Should NOT mention title count
      await waitFor(() => {
        const text = liveRegion?.textContent || "";
        expect(text).not.toContain("title");
        expect(text).toContain("10 description");
        expect(text).toContain("20 transcript");
      });
    });

    it("should announce no results when all sections return empty", async () => {
      // All endpoints return zero results
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0, has_more: false },
            available_languages: [],
          });
        }
        return createMockSegmentResponse({
          data: [],
          pagination: { total: 0, limit: 20, offset: 0, has_more: false },
        });
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "nonexistent");
      await waitForDebounce();

      // Wait for no-results state
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      const liveRegion = document.querySelector('[aria-live="polite"]');

      // Should announce no results
      await waitFor(() => {
        const text = liveRegion?.textContent || "";
        expect(text).toContain("No results found");
        expect(text).toContain("nonexistent");
      });
    });

    it("should announce loading state during initial search", async () => {
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      const liveRegion = document.querySelector('[aria-live="polite"]');

      // Should announce searching state
      await waitFor(() => {
        const text = liveRegion?.textContent || "";
        expect(text).toContain("Searching");
      });
    });
  });

  describe("T038: Static Results Tests", () => {
    it("should show all title results at once without load more button", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({
            data: [
              {
                video_id: "vid1",
                title: "Video One",
                channel_title: "Channel A",
                upload_date: "2024-01-01T10:00:00Z",
              },
              {
                video_id: "vid2",
                title: "Video Two",
                channel_title: "Channel B",
                upload_date: "2024-01-02T10:00:00Z",
              },
            ],
            total_count: 2,
          });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0, has_more: false },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for title results
      await waitFor(() => {
        expect(screen.getByText("Video One")).toBeInTheDocument();
      });
      expect(screen.getByText("Video Two")).toBeInTheDocument();

      // Should NOT have infinite scroll sentinel in title section
      const titleHeading = screen.getByRole("heading", {
        name: /Video Titles/,
      });
      const titleSection = titleHeading.closest("section");
      expect(titleSection).toBeInTheDocument();

      // No infinite scroll sentinel (title section uses static display)
      const sentinel = screen.queryByTestId("infinite-scroll-sentinel");
      expect(sentinel).not.toBeInTheDocument();
    });

    it("should show Showing N of M header when results are capped", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          // Return 50 results but total is 75
          const mockData = Array.from({ length: 50 }, (_, i) => ({
            video_id: `vid${i}`,
            title: `Video ${i}`,
            channel_title: "Channel",
            upload_date: "2024-01-01T10:00:00Z",
          }));
          return createMockTitleResponse({
            data: mockData,
            total_count: 75,
          });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0, has_more: false },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for results
      await waitFor(() => {
        expect(screen.getByText("Video 0")).toBeInTheDocument();
      });

      // Section header should show "Showing 50 of 75"
      expect(
        screen.getByText("Video Titles - Showing 50 of 75")
      ).toBeInTheDocument();
    });

    it("should show description results statically without infinite scroll", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({
            data: [
              {
                video_id: "desc1",
                title: "Description Video 1",
                channel_title: "Channel",
                upload_date: "2024-01-01T10:00:00Z",
                snippet: "This is a snippet...",
              },
              {
                video_id: "desc2",
                title: "Description Video 2",
                channel_title: "Channel",
                upload_date: "2024-01-02T10:00:00Z",
                snippet: "Another snippet...",
              },
            ],
            total_count: 2,
          });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0, has_more: false },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for description results
      await waitFor(() => {
        expect(screen.getByText("Description Video 1")).toBeInTheDocument();
      });
      expect(screen.getByText("Description Video 2")).toBeInTheDocument();

      // Should NOT have infinite scroll sentinel in description section
      const descHeading = screen.getByRole("heading", {
        name: /Descriptions/,
      });
      const descSection = descHeading.closest("section");
      expect(descSection).toBeInTheDocument();

      // No infinite scroll sentinel (description section uses static display)
      const sentinel = screen.queryByTestId("infinite-scroll-sentinel");
      expect(sentinel).not.toBeInTheDocument();
    });

    it("should use infinite scroll for transcript section only", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [
              {
                segment_id: 1,
                video_id: "abc123",
                video_title: "Test Video",
                channel_title: "Channel",
                language_code: "en",
                text: "Transcript segment",
                start_time: 10.0,
                end_time: 15.0,
                context_before: null,
                context_after: null,
                match_count: 1,
                video_upload_date: "2024-01-01T10:00:00Z",
              },
            ],
            pagination: { total: 100, limit: 20, offset: 0, has_more: true },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for transcript results
      await waitFor(() => {
        expect(screen.getByText("Test Video")).toBeInTheDocument();
      });

      // Transcript section should have infinite scroll sentinel (from SearchResultList)
      await waitFor(() => {
        expect(
          screen.getByTestId("infinite-scroll-sentinel")
        ).toBeInTheDocument();
      });
    });

    it("should show total count in header when all results fit on page", async () => {
      mockApiFetch.mockImplementation(async (url: string) => {
        if (url.includes("/search/titles")) {
          return createMockTitleResponse({
            data: [
              {
                video_id: "vid1",
                title: "Video One",
                channel_title: "Channel",
                upload_date: "2024-01-01T10:00:00Z",
              },
            ],
            total_count: 1,
          });
        }
        if (url.includes("/search/descriptions")) {
          return createMockDescriptionResponse({ data: [], total_count: 0 });
        }
        if (url.includes("/search/segments")) {
          return createMockSegmentResponse({
            data: [],
            pagination: { total: 0, limit: 20, offset: 0, has_more: false },
          });
        }
        return createMockSegmentResponse();
      });

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      // Wait for results
      await waitFor(() => {
        expect(screen.getByText("Video One")).toBeInTheDocument();
      });

      // Header should show simple count format (use heading role to avoid matching filter checkbox label)
      expect(screen.getByRole("heading", { name: "Video Titles (1)" })).toBeInTheDocument();
    });
  });
});
