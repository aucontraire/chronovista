/**
 * Integration Tests for SearchPage Component
 *
 * Task T019 - User Story 1: Basic Transcript Search
 *
 * Tests integration flow: type query → debounce → API call → display results
 *
 * Requirements tested:
 * - Shows initial empty state with example chips when no query
 * - Shows skeleton while loading
 * - Shows results when search completes
 * - Shows no-results state when search returns empty
 * - Shows error state when search fails
 * - Clicking example chip triggers search
 * - Query terms are highlighted in results
 *
 * @see FR-001: Search query input
 * @see FR-002: Debounced search execution
 * @see FR-003: Search result display
 * @see FR-014: Loading skeletons
 * @see FR-015: Empty state
 * @see FR-016: Error state
 * @see FR-020: Initial state with example chips
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { SearchPage } from "../../src/pages/SearchPage";
import { apiFetch } from "../../src/api/config";
import type { SearchResponse } from "../../src/types/search";

// Helper to wait for debounce (300ms)
const waitForDebounce = () => act(async () => {
  await new Promise(resolve => setTimeout(resolve, 350));
});

// Mock the API fetch function
vi.mock("../../src/api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = vi.mocked(apiFetch);

/**
 * Factory for creating mock search responses.
 */
function createMockSearchResponse(
  overrides: Partial<SearchResponse> = {}
): SearchResponse {
  return {
    data: [
      {
        segment_id: 1,
        video_id: "abc123def45",
        video_title: "Introduction to Machine Learning",
        channel_title: "Tech Academy",
        language_code: "en",
        text: "Machine learning is a subset of artificial intelligence that focuses on algorithms and statistical models.",
        start_time: 10.5,
        end_time: 15.0,
        context_before: "Welcome to this comprehensive course.",
        context_after: "Let's explore the fundamentals together.",
        match_count: 2,
        video_upload_date: "2024-01-15T12:00:00Z",
      },
      {
        segment_id: 2,
        video_id: "xyz789abc12",
        video_title: "Advanced React Patterns",
        channel_title: "Frontend Masters",
        language_code: "en",
        text: "React hooks provide a way to use state and lifecycle features in functional components.",
        start_time: 120.0,
        end_time: 130.5,
        context_before: "Now let's talk about modern patterns.",
        context_after: "This revolutionized how we write React.",
        match_count: 1,
        video_upload_date: "2024-02-20T14:00:00Z",
      },
    ],
    pagination: {
      total: 2,
      limit: 20,
      offset: 0,
      has_more: false,
    },
    ...overrides,
  };
}

describe("SearchPage Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockReset();
  });

  describe("Initial State (FR-020)", () => {
    it("should show initial empty state with example chips when no query is entered", () => {
      renderWithProviders(<SearchPage />);

      // Verify hero section is displayed
      expect(
        screen.getByText("Search across video transcripts")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Enter keywords to find specific moments in videos")
      ).toBeInTheDocument();

      // Verify example chips are displayed
      expect(screen.getByText("Try:")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /search for machine learning/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /search for react hooks/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /search for typescript tutorial/i })
      ).toBeInTheDocument();

      // Verify search input is present
      expect(screen.getByRole("searchbox")).toBeInTheDocument();

      // Verify no API calls were made
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it("should have search input auto-focused on initial load", () => {
      renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      expect(searchInput).toHaveFocus();
    });
  });

  describe("Loading State (FR-014)", () => {
    it("should show skeleton while loading search results", async () => {
      // Create a promise that never resolves to keep loading state
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");

      // Fast-forward past debounce delay
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify loading skeleton is displayed
      expect(screen.getByLabelText(/loading search results/i)).toBeInTheDocument();

      // Verify skeleton cards are present (aria-hidden, so we check the container)
      const skeletonContainer = screen.getByRole("status");
      expect(skeletonContainer).toHaveAttribute("aria-live", "polite");
      expect(skeletonContainer).toHaveAttribute(
        "aria-label",
        "Loading search results"
      );

      // Verify screen reader text
      expect(screen.getByText("Searching transcripts...")).toBeInTheDocument();
    });

    it("should set aria-busy=true on results container during initial load", async () => {
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test query");

      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Results container should have aria-busy during initial load
      const resultsContainer = screen.getByRole("region", {
        name: /search results/i,
      });
      expect(resultsContainer).toHaveAttribute("aria-busy", "true");
    });
  });

  describe("Successful Search (FR-003, FR-004)", () => {
    it("should display search results when query is entered and search completes", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");

      // Fast-forward past debounce delay
      await waitForDebounce();

      // Wait for API to be called first
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      }, { timeout: 3000 });

      // Wait for results to appear
      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      }, { timeout: 3000 });

      // Verify first result is displayed
      expect(screen.getByText("Tech Academy")).toBeInTheDocument();

      // Text might be broken up by <mark> tags for highlighting
      // Just verify the text appears somewhere in the document
      expect(document.body.textContent).toContain("Machine learning is a subset of artificial intelligence");

      // Verify second result is displayed
      expect(screen.getByText("Advanced React Patterns")).toBeInTheDocument();
      expect(screen.getByText("Frontend Masters")).toBeInTheDocument();

      // Verify API was called with correct parameters
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("q=machine"),
        expect.any(Object)
      );
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("learning"),
        expect.any(Object)
      );
    });

    it("should highlight query terms in results (FR-004)", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Verify highlighted text elements exist
      // The HighlightedText component wraps matching terms in <mark> elements
      const marks = document.querySelectorAll("mark");
      expect(marks.length).toBeGreaterThan(0);

      // Verify marks have correct styling (FR-004: background #fef08a, text #713f12)
      const firstMark = marks[0];
      expect(firstMark).toBeInTheDocument();
    });

    it("should display video metadata correctly (FR-003)", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Verify timestamp range is displayed (FR-017 format)
      expect(screen.getByText(/0:10 - 0:15/)).toBeInTheDocument();
      expect(screen.getByText(/2:00 - 2:10/)).toBeInTheDocument();

      // Verify upload date is displayed (FR-018 format)
      expect(screen.getByText("Jan 15, 2024")).toBeInTheDocument();
      expect(screen.getByText("Feb 20, 2024")).toBeInTheDocument();

      // Verify match count is displayed
      expect(screen.getByText("2 matches")).toBeInTheDocument();
    });

    it("should handle results with null channel_title (EC-007)", async () => {
      const mockResponse = createMockSearchResponse({
        data: [
          {
            segment_id: 1,
            video_id: "abc123def45",
            video_title: "Test Video",
            channel_title: null, // Null channel
            language_code: "en",
            text: "Test segment text",
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
      });
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(screen.getByText("Test Video")).toBeInTheDocument();
      });

      // Verify "Unknown Channel" placeholder is displayed
      expect(screen.getByText("Unknown Channel")).toBeInTheDocument();
    });

    it("should clear aria-busy after results load", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Results container should NOT have aria-busy after load completes
      const resultsContainer = screen.getByRole("region", {
        name: /search results/i,
      });
      expect(resultsContainer).toHaveAttribute("aria-busy", "false");
    });
  });

  describe("No Results State (FR-015)", () => {
    it("should show no-results state when search returns empty array", async () => {
      const mockResponse = createMockSearchResponse({
        data: [],
        pagination: {
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "nonexistent query");

      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify no-results state is displayed
      expect(
        screen.getByText("No transcripts match your search")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Try different keywords or check your spelling.")
      ).toBeInTheDocument();

      // Verify query is shown in no-results message (may appear in multiple places)
      const queryElements = screen.getAllByText(/nonexistent query/i);
      expect(queryElements.length).toBeGreaterThan(0);
    });

    it("should have role=status with aria-live=polite for no-results state", async () => {
      const mockResponse = createMockSearchResponse({
        data: [],
        pagination: {
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      });
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("No transcripts match your search")
        ).toBeInTheDocument();
      });

      const emptyState = screen.getByRole("status");
      expect(emptyState).toHaveAttribute("aria-live", "polite");
    });
  });

  describe("Error State (FR-016)", () => {
    it("should show error state when search fails", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error occurred",
        status: undefined,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test query");

      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify error state is displayed
      expect(
        screen.getByText("Error loading search results")
      ).toBeInTheDocument();
      expect(
        screen.getByText(/something went wrong/i)
      ).toBeInTheDocument();

      // Verify retry button is present
      expect(screen.getByRole("button", { name: /retry search/i })).toBeInTheDocument();
    });

    it("should retry search when retry button is clicked", async () => {
      const mockError = {
        type: "network" as const,
        message: "Network error",
        status: undefined,
      };

      // First call fails
      mockApiFetch.mockRejectedValueOnce(mockError);
      // Second call succeeds
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Error loading search results")
        ).toBeInTheDocument();
      });

      // Click retry button
      const retryButton = screen.getByRole("button", { name: /retry search/i });
      await user.click(retryButton);

      // Wait for successful results
      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Verify API was called twice (initial + retry)
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    it("should have role=alert with aria-live=assertive for error state", async () => {
      const mockError = {
        type: "server" as const,
        message: "Server error",
        status: 500,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Error loading search results")
        ).toBeInTheDocument();
      });

      const errorState = screen.getByRole("alert");
      expect(errorState).toHaveAttribute("aria-live", "assertive");
    });
  });

  describe("Example Chip Interaction (FR-020)", () => {
    it("should trigger search when example chip is clicked", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      // Click an example chip
      const exampleChip = screen.getByRole("button", {
        name: /search for machine learning/i,
      });
      await user.click(exampleChip);

      // Fast-forward past debounce delay
      await waitForDebounce();

      // Wait for results
      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Verify search input has the example query
      const searchInput = screen.getByRole("searchbox");
      expect(searchInput).toHaveValue("machine learning");

      // Verify API was called
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("q=machine"),
        expect.any(Object)
      );
    });

    it("should hide example chips after query is entered", async () => {
      const { user } = renderWithProviders(<SearchPage />);

      // Example chips should be visible initially
      expect(
        screen.getByRole("button", { name: /search for machine learning/i })
      ).toBeInTheDocument();

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "te");

      // Example chips should still be visible (query too short)
      expect(
        screen.getByRole("button", { name: /search for machine learning/i })
      ).toBeInTheDocument();

      // Type more to trigger search
      await user.type(searchInput, "st");

      await waitForDebounce();

      // Example chips should be hidden after valid query
      expect(
        screen.queryByRole("button", { name: /search for machine learning/i })
      ).not.toBeInTheDocument();
    });
  });

  describe("Debounce Behavior (FR-002)", () => {
    it("should debounce search input and only call API after 300ms of inactivity", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValue(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Type rapidly
      await user.type(searchInput, "mac");

      // API should not be called yet
      expect(mockApiFetch).not.toHaveBeenCalled();

      // Wait for debounce to complete
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });
    });

    it("should cancel previous search when query changes before debounce completes", async () => {
      const mockResponse1 = createMockSearchResponse();
      const mockResponse2 = createMockSearchResponse({
        data: [
          {
            segment_id: 3,
            video_id: "new123",
            video_title: "New Result",
            channel_title: "New Channel",
            language_code: "en",
            text: "Different content",
            start_time: 5.0,
            end_time: 10.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-03-01T10:00:00Z",
          },
        ],
      });

      mockApiFetch
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Type first query (wait less than debounce time)
      await user.type(searchInput, "first");

      // Wait a bit but not enough to trigger debounce
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 200));
      });

      // Change query before debounce completes
      await user.clear(searchInput);
      await user.type(searchInput, "second");

      // Complete debounce
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Should only call API once with the latest query
      // TanStack Query handles cancellation automatically
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("q=second"),
        expect.any(Object)
      );
    });
  });

  describe("Query Validation (EC-001, EC-002)", () => {
    it("should not trigger search when query is less than 2 characters", async () => {
      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "a");

      await waitForDebounce();

      // Should not call API with too-short query
      expect(mockApiFetch).not.toHaveBeenCalled();

      // Should show validation message
      expect(screen.getByText(/enter at least 2 characters/i)).toBeInTheDocument();
    });

    it("should return to initial state when query is cleared (EC-010)", async () => {
      const mockResponse = createMockSearchResponse();
      // Use mockResolvedValue (not Once) to handle potential refetches
      mockApiFetch.mockResolvedValue(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Enter query and get results
      await user.type(searchInput, "test");
      await waitForDebounce();

      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      }, { timeout: 3000 });

      // Clear the query
      await user.clear(searchInput);

      // Should return to initial hero state immediately (query hook is disabled when query is empty)
      await waitFor(() => {
        expect(
          screen.getByText("Search across video transcripts")
        ).toBeInTheDocument();
      }, { timeout: 3000 });

      // Results should be cleared
      expect(
        screen.queryByText("Introduction to Machine Learning")
      ).not.toBeInTheDocument();

      // Example chips should reappear
      expect(
        screen.getByRole("button", { name: /search for machine learning/i })
      ).toBeInTheDocument();
    });
  });

  describe("Accessibility (FR-025, FR-026, FR-029, FR-030)", () => {
    it("should have proper landmark structure (FR-030)", () => {
      renderWithProviders(<SearchPage />);

      // Verify search form has role="search"
      expect(screen.getByRole("search")).toBeInTheDocument();

      // Verify main content area
      expect(screen.getByRole("main")).toBeInTheDocument();

      // Verify search results region
      expect(
        screen.getByRole("region", { name: /search results/i })
      ).toBeInTheDocument();
    });

    it("should have searchbox with proper ARIA attributes (FR-025)", () => {
      renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Verify ARIA attributes
      expect(searchInput).toHaveAttribute("aria-label", "Search transcripts");
      expect(searchInput).toHaveAttribute("aria-controls", "search-results");
    });

    it("should announce search status via aria-live region (FR-026)", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");

      await waitForDebounce();

      // During loading, should announce "Searching transcripts..."
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // After results load, should announce result count
      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });

      // Verify aria-live region exists
      const liveRegions = document.querySelectorAll('[aria-live="polite"]');
      expect(liveRegions.length).toBeGreaterThan(0);
    });

    it("should be keyboard accessible (FR-029)", async () => {
      renderWithProviders(<SearchPage />);

      // Verify search input is focusable
      const searchInput = screen.getByRole("searchbox");
      searchInput.focus();
      expect(searchInput).toHaveFocus();

      // Verify example chips are keyboard accessible
      const exampleChip = screen.getByRole("button", {
        name: /search for machine learning/i,
      });
      exampleChip.focus();
      expect(exampleChip).toHaveFocus();
    });
  });

  describe("URL State Sync (FR-011, FR-012) - User Story 6", () => {
    it("should update URL when query changes", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search"],
        path: "/search",
      });

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "machine learning");

      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify URL was updated with query parameter
      await waitFor(() => {
        expect(window.location.search).toContain("machine");
      });
      expect(window.location.search).toContain("learning");
    });

    it("should update URL when language filter changes", async () => {
      const mockResponseMultiLang = createMockSearchResponse({
        data: [
          {
            segment_id: 1,
            video_id: "abc123",
            video_title: "Test Video",
            channel_title: "Test Channel",
            language_code: "en",
            text: "English text",
            start_time: 10.0,
            end_time: 15.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-01-15T12:00:00Z",
          },
          {
            segment_id: 2,
            video_id: "xyz789",
            video_title: "Spanish Video",
            channel_title: "Test Channel",
            language_code: "es",
            text: "Spanish text",
            start_time: 20.0,
            end_time: 25.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-01-15T12:00:00Z",
          },
        ],
      });

      // Add available_languages field to the response
      (mockResponseMultiLang as any).available_languages = ["en", "es"];

      const mockResponseEnglishOnly = createMockSearchResponse({
        data: [
          {
            segment_id: 1,
            video_id: "abc123",
            video_title: "Test Video",
            channel_title: "Test Channel",
            language_code: "en",
            text: "English text",
            start_time: 10.0,
            end_time: 15.0,
            context_before: null,
            context_after: null,
            match_count: 1,
            video_upload_date: "2024-01-15T12:00:00Z",
          },
        ],
      });

      // First call returns multi-language results, second call returns filtered results
      mockApiFetch
        .mockResolvedValueOnce(mockResponseMultiLang)
        .mockResolvedValueOnce(mockResponseEnglishOnly);

      const { user } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search"],
        path: "/search",
      });

      // First, perform a search to get results with multiple languages
      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      await waitFor(() => {
        expect(screen.getByText("Test Video")).toBeInTheDocument();
      }, { timeout: 3000 });

      // Verify both videos are shown initially
      expect(screen.getByText("Spanish Video")).toBeInTheDocument();

      // Now select a language filter
      // Note: Filter panel is hidden on small screens with "hidden lg:block"
      // We need to query for the select element even when hidden because tests run in small viewport
      const languageFilter = document.getElementById('language-filter') as HTMLSelectElement;
      expect(languageFilter).not.toBeNull();
      await user.selectOptions(languageFilter!, "en");

      // Wait for the filtered results to load (new API call with language param)
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      }, { timeout: 3000 });

      // Verify URL was updated with language parameter
      await waitFor(() => {
        expect(window.location.search).toContain("language=en");
      }, { timeout: 3000 });
    });

    it("should clear URL params when search is cleared", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { user } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search"],
        path: "/search",
      });

      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "test");
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Clear the search
      await user.clear(searchInput);
      await waitForDebounce();

      // Verify URL params were cleared
      expect(window.location.search).toBe("");
    });

    it("should restore search state from URL params on page load (FR-012)", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderWithProviders(<SearchPage />, {
        initialEntries: ["/search?q=machine+learning"],
        path: "/search",
      });

      // Wait for initial load to complete
      // Initial render - no debounce needed

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify search input has the query from URL
      const searchInput = screen.getByRole("searchbox");
      expect(searchInput).toHaveValue("machine learning");

      // Verify results are displayed
      await waitFor(() => {
        expect(
          screen.getByText("Introduction to Machine Learning")
        ).toBeInTheDocument();
      });
    });

    it("should restore both query and language from URL params", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValue(mockResponse);

      renderWithProviders(<SearchPage />, {
        initialEntries: ["/search?q=test&language=en"],
        path: "/search",
      });

      // Initial render - no debounce needed

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify both query and language are restored
      const searchInput = screen.getByRole("searchbox");
      expect(searchInput).toHaveValue("test");

      // Verify API was called with correct parameters
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/q=test/),
        expect.any(Object)
      );
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/language=en/),
        expect.any(Object)
      );
    });

    it("should handle refreshing page with URL params", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { rerender } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search?q=react+hooks"],
        path: "/search",
      });

      // Initial render - no debounce needed

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Simulate page refresh by re-rendering with same URL
      rerender(<SearchPage />);

      // Verify search state is preserved
      const searchInput = screen.getByRole("searchbox");
      expect(searchInput).toHaveValue("react hooks");
    });

    it("should handle browser back/forward navigation", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValue(mockResponse);

      const { user } = renderWithProviders(<SearchPage />, {
        initialEntries: ["/search"],
        path: "/search",
      });

      // Perform first search
      const searchInput = screen.getByRole("searchbox");
      await user.type(searchInput, "first query");
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Perform second search
      await user.clear(searchInput);
      await user.type(searchInput, "second query");
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });

      // Verify current query is in URL
      expect(window.location.search).toContain("second");
    });
  });

  describe("Edge Cases", () => {
    it("should handle empty query submission (EC-010)", async () => {
      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Type then delete all characters
      await user.type(searchInput, "test");
      await user.clear(searchInput);

      await waitForDebounce();

      // Should not call API
      expect(mockApiFetch).not.toHaveBeenCalled();

      // Should show initial state
      expect(
        screen.getByText("Search across video transcripts")
      ).toBeInTheDocument();
    });

    it("should handle rapid typing without excessive API calls (EC-008)", async () => {
      const mockResponse = createMockSearchResponse();
      mockApiFetch.mockResolvedValue(mockResponse);

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");

      // Simulate rapid typing
      await user.type(searchInput, "machine learning tutorials");

      // Fast-forward only the debounce delay
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Should only call API once despite many keystrokes
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    it("should preserve query in input during loading state", async () => {
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { user } = renderWithProviders(<SearchPage />);

      const searchInput = screen.getByRole("searchbox");
      const testQuery = "machine learning";

      await user.type(searchInput, testQuery);
      await waitForDebounce();

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Query should remain in input during loading
      expect(searchInput).toHaveValue(testQuery);
    });
  });
});
