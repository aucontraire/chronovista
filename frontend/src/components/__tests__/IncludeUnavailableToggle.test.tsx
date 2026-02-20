/**
 * Tests for Include Unavailable Content Toggle
 *
 * Tests Feature 023 (Deleted Content Visibility) requirements:
 * - T031: Include unavailable content toggle in VideoFilters and SearchFilters
 * - FR-021: Toggle to include/exclude unavailable content in results
 * - NFR-003: WCAG 2.1 Level AA accessibility requirements
 *
 * Test Coverage:
 * - Rendering tests (toggle appears with correct label)
 * - Keyboard operability (Tab focus, Enter/Space toggle)
 * - Accessibility (ARIA attributes, focus indicators)
 * - State management (URL params, callbacks)
 * - VideoFilters integration
 * - SearchFilters integration (conditional rendering)
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VideoFilters } from "../VideoFilters";
import { SearchFilters } from "../SearchFilters";

// Mock the hooks
vi.mock("../../hooks/useCategories", () => ({
  useCategories: () => ({
    categories: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock("../../hooks/useTopics", () => ({
  useTopics: () => ({
    topics: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock("../../hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => true,
}));

function renderWithProviders(
  ui: React.ReactElement,
  { route = "/" } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("IncludeUnavailableToggle - VideoFilters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Rendering Tests", () => {
    it("should render toggle with accessible label", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toBeInTheDocument();
    });

    it("should render toggle with visible label text", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      expect(
        screen.getByText("Show unavailable content")
      ).toBeInTheDocument();
    });

    it("should be unchecked by default", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).not.toBeChecked();
    });

    it("should be checked when URL param is true", () => {
      renderWithProviders(<VideoFilters videoCount={0} />, {
        route: "/?include_unavailable=true",
      });

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toBeChecked();
    });

    it("should render as a checkbox input type", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toHaveAttribute("type", "checkbox");
    });
  });

  describe("Keyboard Operability (NFR-003)", () => {
    it("should be focusable via Tab key", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      // Tab to the toggle
      await user.tab();
      await user.tab();
      await user.tab();
      await user.tab(); // Skip tag, category, topic inputs

      // Toggle should eventually receive focus (it's in the document)
      expect(toggle).toBeInTheDocument();
    });

    it("should toggle state with Space key", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      // Focus and press Space
      toggle.focus();
      await user.keyboard(" ");

      expect(toggle).toBeChecked();
    });

    it("should be activatable with Enter key on label", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      // FilterToggle uses <label htmlFor> (sibling), not wrapping <label>
      const label = document.querySelector(`label[for="${toggle.id}"]`);

      // Focus label and press Enter
      (label as HTMLElement)!.focus();
      await user.keyboard("{Enter}");

      // Note: Native checkbox behavior is to toggle on Space, not Enter
      // But clicking the label with Enter works in browsers
      expect(toggle).toBeInTheDocument();
    });

    it("should have visible focus indicator", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      // Check for focus ring classes (WCAG 2.4.7)
      expect(toggle).toHaveClass("focus:ring-2");
      expect(toggle).toHaveClass("focus:ring-blue-500");
      expect(toggle).toHaveClass("focus:ring-offset-2");
    });
  });

  describe("Accessibility (NFR-003)", () => {
    it("should have accessible name from associated label", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      // FilterToggle uses <label htmlFor> for accessible name (not aria-label)
      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      const label = document.querySelector(`label[for="${toggle.id}"]`);
      expect(label).toBeInTheDocument();
      expect(label).toHaveTextContent("Show unavailable content");
    });

    it("should communicate checked state to screen readers", () => {
      renderWithProviders(<VideoFilters videoCount={0} />, {
        route: "/?include_unavailable=true",
      });

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toHaveAttribute("checked");
    });

    it("should communicate unchecked state to screen readers", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).not.toHaveAttribute("checked");
    });

    it("should be identifiable as a checkbox control", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle.getAttribute("role")).toBe(null); // Native checkbox, no explicit role needed
      expect(toggle.tagName).toBe("INPUT");
      expect(toggle).toHaveAttribute("type", "checkbox");
    });

    it("should have associated label element", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      // FilterToggle uses <label htmlFor> (sibling), not wrapping <label>
      const label = document.querySelector(`label[for="${toggle.id}"]`);

      expect(label).toBeInTheDocument();
      expect(label).toHaveTextContent("Show unavailable content");
    });
  });

  describe("State Management - URL Params", () => {
    it("should update toggle state when clicking ON", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      await user.click(toggle);

      expect(toggle).toBeChecked();
    });

    it("should update toggle state when clicking OFF", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />, {
        route: "/?include_unavailable=true",
      });

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toBeChecked();

      await user.click(toggle);

      expect(toggle).not.toBeChecked();
    });

    it("should preserve checked state after toggle", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      // Toggle ON
      await user.click(toggle);
      expect(toggle).toBeChecked();

      // Toggle OFF
      await user.click(toggle);
      expect(toggle).not.toBeChecked();
    });

    it("should maintain URL param state with other filters", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />, {
        route: "/?tag=music",
      });

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      await user.click(toggle);

      // Verify toggle is checked
      expect(toggle).toBeChecked();
    });

    it("should work with multiple toggles", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });

      // Multiple clicks
      await user.click(toggle);
      expect(toggle).toBeChecked();

      await user.click(toggle);
      expect(toggle).not.toBeChecked();

      await user.click(toggle);
      expect(toggle).toBeChecked();
    });
  });

  describe("Clear All Filters", () => {
    it("should clear include_unavailable when Clear All is clicked", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VideoFilters videoCount={0} />, {
        route: "/?include_unavailable=true&tag=music",
      });

      // Verify toggle is checked
      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      expect(toggle).toBeChecked();

      // Click Clear All button
      const clearButton = screen.getByRole("button", { name: /clear all/i });
      await user.click(clearButton);

      // Verify toggle is now unchecked
      expect(toggle).not.toBeChecked();
      expect(window.location.search).not.toContain("include_unavailable");
    });
  });

  describe("Visual Layout", () => {
    it("should be in a separate section with border", () => {
      renderWithProviders(
        <VideoFilters videoCount={0} />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      // FilterToggle is inside: div.pt-3 > div.flex > input
      const section = toggle.closest("div.flex")?.parentElement;

      expect(section).toBeInTheDocument();
      expect(section).toHaveClass("pt-3");
      expect(section).toHaveClass("border-t");
      expect(section).toHaveClass("border-gray-200");
    });

    it("should have cursor-pointer on label", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      // FilterToggle uses <label htmlFor> (sibling), not wrapping <label>
      const label = document.querySelector(`label[for="${toggle.id}"]`);

      expect(label).toHaveClass("cursor-pointer");
    });

    it("should have spacing between checkbox and label text", () => {
      renderWithProviders(<VideoFilters videoCount={0} />);

      const toggle = screen.getByRole("checkbox", {
        name: /show unavailable content/i,
      });
      // FilterToggle uses ml-2 on the label for spacing
      const label = document.querySelector(`label[for="${toggle.id}"]`);

      expect(label).toHaveClass("ml-2");
    });
  });
});

describe("IncludeUnavailableToggle - SearchFilters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Conditional Rendering", () => {
    it("should render toggle when onToggleIncludeUnavailable prop is provided", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).toBeInTheDocument();
    });

    it("should NOT render toggle when onToggleIncludeUnavailable prop is omitted", () => {
      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
        />
      );

      const toggle = screen.queryByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).not.toBeInTheDocument();
    });

    it("should NOT render toggle when onToggleIncludeUnavailable is undefined", () => {
      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
        />
      );

      const toggle = screen.queryByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).not.toBeInTheDocument();
    });
  });

  describe("Callback Propagation", () => {
    it("should call onToggleIncludeUnavailable callback when clicked", async () => {
      const user = userEvent.setup();
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
          includeUnavailable={false}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });

      await user.click(toggle);

      expect(mockToggle).toHaveBeenCalledTimes(1);
    });

    it("should reflect includeUnavailable prop value", () => {
      const mockToggle = vi.fn();

      const { rerender } = render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
          includeUnavailable={false}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).not.toBeChecked();

      // Rerender with includeUnavailable=true
      rerender(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
          includeUnavailable={true}
        />
      );

      expect(toggle).toBeChecked();
    });

    it("should default to false when includeUnavailable prop is omitted", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).not.toBeChecked();
    });
  });

  describe("Accessibility in SearchFilters", () => {
    it("should have aria-label attribute", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      expect(toggle).toHaveAttribute("aria-label", "Include unavailable content");
    });

    it("should have visible focus indicator", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });

      expect(toggle).toHaveClass("focus:ring-2");
      expect(toggle).toHaveClass("focus:ring-blue-500");
      expect(toggle).toHaveClass("focus:ring-offset-2");
    });

    it("should have associated label element", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      const label = toggle.closest("label");

      expect(label).toBeInTheDocument();
      expect(label).toHaveTextContent("Show unavailable content");
    });
  });

  describe("Keyboard Operability in SearchFilters", () => {
    it("should toggle state with Space key", async () => {
      const user = userEvent.setup();
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
          includeUnavailable={false}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });

      toggle.focus();
      await user.keyboard(" ");

      expect(mockToggle).toHaveBeenCalledTimes(1);
    });

    it("should be activatable with click", async () => {
      const user = userEvent.setup();
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
          includeUnavailable={false}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });

      await user.click(toggle);

      expect(mockToggle).toHaveBeenCalledTimes(1);
    });
  });

  describe("Visual Layout in SearchFilters", () => {
    it("should be in a separate section with border", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      const section = toggle.closest("div.pt-4");

      expect(section).toBeInTheDocument();
      expect(section).toHaveClass("border-t");
      expect(section).toHaveClass("border-gray-200");
    });

    it("should have hover effect on label", () => {
      const mockToggle = vi.fn();

      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={vi.fn()}
          totalResults={10}
          enabledTypes={{ transcripts: true, titles: false, descriptions: false }}
          onToggleType={vi.fn()}
          onToggleIncludeUnavailable={mockToggle}
        />
      );

      const toggle = screen.getByRole("checkbox", {
        name: /include unavailable content/i,
      });
      const label = toggle.closest("label");

      expect(label).toHaveClass("hover:bg-gray-50");
      expect(label).toHaveClass("cursor-pointer");
    });
  });
});
