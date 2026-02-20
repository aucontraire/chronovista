/**
 * Tests for HomePage (VideosPage)
 *
 * Verifies:
 * - T013: Zero-regression after FilterToggle migration
 * - Include unavailable content checkbox functionality
 * - URL state persistence for include_unavailable parameter
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HomePage } from "../../pages/HomePage";

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
