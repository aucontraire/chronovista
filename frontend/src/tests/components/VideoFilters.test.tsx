/**
 * Tests for VideoFilters component
 *
 * Verifies:
 * - T044: Filter panel layout and integration
 * - T045: TagAutocomplete integration
 * - T047: URL state sync
 * - T048: Clear All functionality
 * - T042b: Filter limit validation
 * - FR-034: Filter limits enforcement
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VideoFilters } from "../../components/VideoFilters";

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
      {
        topic_id: "/m/02mscn",
        name: "Rock Music",
        parent_topic_id: "/m/04rlf",
        parent_path: "Music",
        depth: 1,
        video_count: 50,
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

// Helper to render with Router and QueryClient
function renderWithProviders(
  ui: React.ReactElement,
  { initialEntries = ["/"] } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VideoFilters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Rendering and layout (T044)", () => {
    it("should render all filter components", () => {
      renderWithProviders(<VideoFilters />);

      // Check for filter controls by their placeholder text (more reliable)
      expect(screen.getByPlaceholderText(/Type to search tags/)).toBeInTheDocument();
      expect(screen.getByLabelText("Category")).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Type to search topics/)).toBeInTheDocument();
    });

    it("should show no active filters message when no filters applied", () => {
      renderWithProviders(<VideoFilters />);

      expect(
        screen.getByText(
          /No active filters. Select tags, categories, or topics to filter videos./
        )
      ).toBeInTheDocument();
    });

    it("should display video count when provided", () => {
      renderWithProviders(<VideoFilters videoCount={47} />, {
        initialEntries: ["/?tag=music"],
      });

      expect(screen.getByText(/Showing 47 videos/)).toBeInTheDocument();
    });

    it("should handle null video count gracefully", () => {
      renderWithProviders(<VideoFilters videoCount={null} />);

      expect(screen.queryByText(/Showing/)).not.toBeInTheDocument();
    });
  });

  describe("URL state sync (T047)", () => {
    it("should read tags from URL parameters", async () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music&tag=tutorial"],
      });

      // Tags should appear in FilterPills or labels (use getAllByText since tags appear multiple times)
      await waitFor(() => {
        const musicElements = screen.getAllByText("music");
        expect(musicElements.length).toBeGreaterThan(0);
        const tutorialElements = screen.getAllByText("tutorial");
        expect(tutorialElements.length).toBeGreaterThan(0);
      });
    });

    it("should read category from URL parameters", async () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?category=10"],
      });

      // Category should appear in FilterPills (may appear multiple times)
      await waitFor(() => {
        const gamingElements = screen.getAllByText("Gaming");
        expect(gamingElements.length).toBeGreaterThan(0);
      });
    });

    it("should read topic IDs from URL parameters", async () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?topic_id=/m/04rlf"],
      });

      // Topic should appear in FilterPills (may appear multiple times)
      await waitFor(() => {
        const musicElements = screen.getAllByText("Music");
        expect(musicElements.length).toBeGreaterThan(0);
      });
    });

    it("should read multiple filter types from URL", async () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music&category=10&topic_id=/m/04rlf"],
      });

      await waitFor(() => {
        const musicElements = screen.getAllByText("music");
        expect(musicElements.length).toBeGreaterThan(0);
        const gamingElements = screen.getAllByText("Gaming");
        expect(gamingElements.length).toBeGreaterThan(0);
        // There might be multiple "Music" (tag and topic), so use getAllByText
        const musicLabels = screen.getAllByText("Music");
        expect(musicLabels.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Filter limit validation (T042b, FR-034)", () => {
    it("should show warning when approaching total filter limit", async () => {
      // Create 8 tags (80% of 10) which should trigger the warning
      const tags = Array.from({ length: 8 }, (_, i) => `tag${i}`).join("&tag=");
      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?tag=${tags}`],
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Approaching filter limits/)
        ).toBeInTheDocument();
      });
    });

    it("should show warning when max tags limit reached", () => {
      // Create 10 tags (max limit)
      const tags = Array.from({ length: 10 }, (_, i) => `tag${i}`).join("&tag=");
      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?tag=${tags}`],
      });

      expect(
        screen.getByText(/Maximum tag limit reached/)
      ).toBeInTheDocument();
    });

    it("should show warning when max topics limit reached", () => {
      // Create 10 topics (max limit)
      const topics = Array.from({ length: 10 }, (_, i) => `/m/topic${i}`).join(
        "&topic_id="
      );
      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?topic_id=${topics}`],
      });

      expect(
        screen.getByText(/Maximum topic limit reached/)
      ).toBeInTheDocument();
    });

    it("should show warning when max total filters reached", () => {
      // Create 15 filters total (max limit)
      const tags = Array.from({ length: 8 }, (_, i) => `tag${i}`).join("&tag=");
      const topics = Array.from({ length: 7 }, (_, i) => `/m/topic${i}`).join(
        "&topic_id="
      );
      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?tag=${tags}&topic_id=${topics}`],
      });

      expect(
        screen.getByText(/Maximum filter limit reached/)
      ).toBeInTheDocument();
    });
  });

  describe("Clear All functionality (T048)", () => {
    it("should show Clear All button when filters are active", () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music"],
      });

      expect(
        screen.getByRole("button", { name: "Clear All" })
      ).toBeInTheDocument();
    });

    it("should not show Clear All button when no filters active", () => {
      renderWithProviders(<VideoFilters />);

      expect(
        screen.queryByRole("button", { name: "Clear All" })
      ).not.toBeInTheDocument();
    });

    it("should clear all filters when Clear All clicked", async () => {
      const user = userEvent.setup();

      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music&category=10&topic_id=/m/04rlf"],
      });

      // Verify filters are present
      const musicElements = screen.getAllByText("music");
      expect(musicElements.length).toBeGreaterThan(0);
      const gamingElements = screen.getAllByText("Gaming");
      expect(gamingElements.length).toBeGreaterThan(0);

      const clearAllButton = screen.getByRole("button", { name: "Clear All" });
      await user.click(clearAllButton);

      // Filters should be removed (this is a simplification - in real tests,
      // you'd check URL params or verify the filters are no longer visible)
      await waitFor(() => {
        expect(
          screen.getByText(
            /No active filters. Select tags, categories, or topics to filter videos./
          )
        ).toBeInTheDocument();
      });
    });
  });

  describe("Active filters display", () => {
    it("should show filter count in header", () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music&tag=tutorial&category=10"],
      });

      expect(screen.getByText("Active Filters (3)")).toBeInTheDocument();
    });

    it("should display FilterPills for active filters", () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: ["/?tag=music&category=10"],
      });

      // Check that FilterPills are rendered (they have role="list")
      const filterList = screen.getByRole("list", { name: "Active filters" });
      expect(filterList).toBeInTheDocument();
    });
  });

  describe("Integration with filter components (T045)", () => {
    it("should render TagAutocomplete component", () => {
      renderWithProviders(<VideoFilters />);

      // TagAutocomplete has a specific placeholder
      expect(
        screen.getByPlaceholderText(/Type to search tags/)
      ).toBeInTheDocument();
    });

    it("should render CategoryDropdown component", () => {
      renderWithProviders(<VideoFilters />);

      expect(screen.getByLabelText("Category")).toBeInTheDocument();
    });

    it("should render TopicCombobox component", () => {
      renderWithProviders(<VideoFilters />);

      // TopicCombobox has a specific placeholder
      expect(
        screen.getByPlaceholderText(/Type to search topics/)
      ).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA structure", () => {
      const { container } = renderWithProviders(<VideoFilters />);

      // Check for main container with appropriate structure
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it("should announce warning messages with role=alert", () => {
      renderWithProviders(<VideoFilters />, {
        initialEntries: [`/?${Array.from({ length: 12 }, (_, i) => `tag=tag${i}`).join("&")}`],
      });

      const alert = screen.getByRole("alert");
      expect(alert).toHaveAttribute("aria-live", "polite");
      expect(alert).toHaveTextContent(/Warning/);
    });

    it("should announce video count with aria-live", async () => {
      renderWithProviders(<VideoFilters videoCount={47} />, {
        initialEntries: ["/?tag=music"],
      });

      // Use getByText to find the video count announcement
      await waitFor(() => {
        expect(screen.getByText(/Showing 47 videos/)).toBeInTheDocument();
      });

      // Verify it has the proper ARIA live region - the <p> tag itself has role="status"
      const status = screen.getByText(/Showing 47 videos/);
      expect(status).toHaveAttribute("role", "status");
      expect(status).toHaveAttribute("aria-live", "polite");
    });
  });

  describe("Responsive layout", () => {
    it("should use grid layout for filter controls", () => {
      const { container } = renderWithProviders(<VideoFilters />);

      // Check for grid layout classes (Tailwind classes)
      const filterControls = container.querySelector(".grid.grid-cols-1.md\\:grid-cols-3");
      expect(filterControls).toBeInTheDocument();
    });
  });
});
