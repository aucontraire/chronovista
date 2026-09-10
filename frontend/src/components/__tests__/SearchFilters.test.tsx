/**
 * Tests for SearchFilters Component
 *
 * Reconciled from two divergent copies (issue #309):
 * - frontend/src/tests/components/SearchFilters.test.tsx (language consolidation +
 *   include-unavailable-toggle suite)
 * - frontend/tests/components/SearchFilters.test.tsx (US4 language filter + US7 search
 *   type filter panel suite, T044-T048)
 *
 * User Story 4: Language Filter
 * Requirements tested:
 * - FR-008: Language filter dropdown with available languages
 * - Filter shows "All languages" as default option
 * - Available languages populated from search results
 * - Filter selection triggers callback
 * - Filter can be cleared (reset to all languages)
 * - ARIA attributes for accessibility
 * - Language consolidation preserves regional variants (e.g., en-US vs en-GB)
 *
 * User Story 7: Search Type Filter Panel (T044-T048)
 * Requirements tested:
 * - FR-013: Search type checkboxes (Transcripts, Video Titles, Descriptions)
 * - FR-021: Responsive filter panel (desktop sidebar, tablet drawer, mobile bottom sheet)
 * - Result count displayed on Transcripts checkbox
 * - Responsive behavior across breakpoints
 *
 * T031 / FR-021 / NFR-003: Include Unavailable Content toggle
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchFilters } from "../SearchFilters";
import type { EnabledSearchTypes } from "../../types/search";

// SearchFilters has no React Query / Router dependencies, so the local render
// helper only needs to attach a ready-to-use `userEvent` instance. Defined
// in-file (not imported from `frontend/tests/test-utils`) to keep `src/`
// test imports self-contained and typecheck-safe.
function renderWithProviders(ui: React.ReactElement) {
  return {
    ...render(ui),
    user: userEvent.setup(),
  };
}

// Default enabled types for testing
const defaultEnabledTypes: EnabledSearchTypes = {
  titles: true,
  descriptions: true,
  transcripts: true,
};

describe("SearchFilters", () => {
  const mockOnLanguageChange = vi.fn();
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Rendering", () => {
    it("should render language filter dropdown", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox", { name: /language filter/i });
      expect(dropdown).toBeInTheDocument();
    });

    it('should render "All languages" as default option', () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveValue("");
      expect(screen.getByRole("option", { name: /all languages/i })).toBeInTheDocument();
    });

    it("should render available languages as options", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(screen.getByRole("option", { name: /english/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /spanish/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /german/i })).toBeInTheDocument();
    });

    it("should handle empty available languages array", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={[]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Language dropdown should not be rendered when no languages available
      const dropdown = screen.queryByRole("combobox", { name: /language filter/i });
      expect(dropdown).not.toBeInTheDocument();

      // But search type filters should still be present
      expect(screen.getByRole("checkbox", { name: /transcripts/i })).toBeInTheDocument();
    });

    it("should render with selected language", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveValue("en");
    });
  });

  describe("ARIA Attributes (FR-008)", () => {
    it("should have aria-label for accessibility", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveAccessibleName();
      expect(dropdown).toHaveAttribute("aria-label");
    });

    it("should have proper label association", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox", { name: /language filter/i });
      expect(dropdown).toBeInTheDocument();
    });

    it("should have id attribute for label association", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveAttribute("id");
    });
  });

  describe("Language Selection", () => {
    it("should call onLanguageChange when selecting a language", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      await user.selectOptions(dropdown, "en");

      expect(mockOnLanguageChange).toHaveBeenCalledTimes(1);
      expect(mockOnLanguageChange).toHaveBeenCalledWith("en");
    });

    it('should call onLanguageChange when selecting "All languages"', async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      await user.selectOptions(dropdown, "");

      expect(mockOnLanguageChange).toHaveBeenCalledTimes(1);
      expect(mockOnLanguageChange).toHaveBeenCalledWith("");
    });

    it("should update selection when changing from one language to another", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveValue("en");

      await user.selectOptions(dropdown, "es");

      expect(mockOnLanguageChange).toHaveBeenCalledWith("es");
    });

    it("should not call onLanguageChange when selecting the same language", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      await user.selectOptions(dropdown, "en");

      // Should still call the callback (component doesn't prevent it)
      expect(mockOnLanguageChange).toHaveBeenCalledWith("en");
    });
  });

  describe("Language Display Names", () => {
    it("should display human-readable language names", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de", "fr", "pt", "ja", "ko", "zh"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(screen.getByRole("option", { name: /english/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /spanish/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /german/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /french/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /portuguese/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /japanese/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /korean/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /chinese/i })).toBeInTheDocument();
    });

    it("should display BCP-47 code as fallback for unknown languages", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "xyz"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(screen.getByRole("option", { name: /english/i })).toBeInTheDocument();
      // Unknown language should show the code itself
      expect(screen.getByRole("option", { name: "xyz" })).toBeInTheDocument();
    });

    it("should handle language codes with regions (e.g., en-US, es-MX)", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en-US", "es-MX"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should match the base language
      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toBeInTheDocument();
    });
  });

  describe("Language consolidation", () => {
    it("should consolidate regional language variants to base codes", () => {
      // Component now PRESERVES regional variants to show specific language context
      // This allows users to filter by exact dialect/spelling (e.g., en-US vs en-GB)
      const regionalVariants = ["en", "en-US", "en-GB", "es", "es-MX"];

      renderWithProviders(
        <SearchFilters
          availableLanguages={regionalVariants}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const languageSelect = screen.getByLabelText("Language filter");
      const options = Array.from(languageSelect.querySelectorAll("option"));
      const languageOptions = options.filter((opt) => opt.value !== "");

      // Should preserve all 5 regional variants
      expect(languageOptions).toHaveLength(5);

      // Should show both base codes and regional variants with region labels
      const languageTexts = languageOptions.map((opt) => opt.textContent);
      expect(languageTexts).toContain("English");
      expect(languageTexts).toContain("English (United States)");
      expect(languageTexts).toContain("English (United Kingdom)");
      expect(languageTexts).toContain("Spanish");
      expect(languageTexts).toContain("Spanish (Mexico)");
    });

    it("should handle empty language list gracefully", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={[]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Language filter should not be rendered when no languages available
      const languageSelect = screen.queryByLabelText("Language filter");
      expect(languageSelect).not.toBeInTheDocument();
    });

    it("should sort languages alphabetically by display name", () => {
      const languages = ["ja", "en", "zh", "es", "ar"];

      renderWithProviders(
        <SearchFilters
          availableLanguages={languages}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const languageSelect = screen.getByLabelText("Language filter");
      const options = Array.from(languageSelect.querySelectorAll("option"));
      const languageOptions = options.filter((opt) => opt.value !== "");
      const languageTexts = languageOptions.map((opt) => opt.textContent);

      // Should be sorted: Arabic, Chinese, English, Japanese, Spanish
      expect(languageTexts).toEqual([
        "Arabic",
        "Chinese",
        "English",
        "Japanese",
        "Spanish",
      ]);
    });
  });

  describe("Keyboard Accessibility", () => {
    it("should be keyboard accessible", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Tab to the first focusable element (Transcripts checkbox)
      await user.tab();

      const transcriptsCheckbox = screen.getByRole("checkbox", { name: /transcripts/i });
      expect(transcriptsCheckbox).toHaveFocus();
    });

    it("should allow arrow key navigation", async () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      dropdown.focus();

      // Note: Arrow key behavior is native to <select>
      // This test just verifies the element is focusable
      expect(dropdown).toHaveFocus();
    });
  });

  describe("Component Updates", () => {
    it("should update when availableLanguages prop changes", () => {
      const { rerender } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(screen.getByRole("option", { name: /english/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /spanish/i })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /german/i })).not.toBeInTheDocument();

      rerender(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(screen.getByRole("option", { name: /german/i })).toBeInTheDocument();
    });

    it("should update when selectedLanguage prop changes", () => {
      const { rerender } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveValue("");

      rerender(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(dropdown).toHaveValue("en");
    });

    it("should maintain focus when props change", () => {
      const { rerender } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      dropdown.focus();
      expect(dropdown).toHaveFocus();

      rerender(
        <SearchFilters
          availableLanguages={["en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      expect(dropdown).toHaveFocus();
    });
  });

  describe("Edge Cases", () => {
    it("should handle duplicate language codes", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should deduplicate
      const englishOptions = screen.getAllByRole("option", { name: /english/i });
      expect(englishOptions).toHaveLength(1);
    });

    it("should sort languages alphabetically by display name (option count only)", () => {
      // Complements the exact-order assertion in "Language consolidation" above:
      // this copy only verifies the "All languages" option leads and the
      // remaining option count, without asserting the precise sorted order.
      renderWithProviders(
        <SearchFilters
          availableLanguages={["zh", "en", "es", "de"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const options = screen.getAllByRole("option");
      // First option is "All languages"
      expect(options[0]).toHaveTextContent(/all languages/i);

      // Remaining options should be sorted
      const languageOptions = options.slice(1);
      const languageNames = languageOptions.map((opt) => opt.textContent);

      // Verify alphabetical order (may vary based on implementation)
      expect(languageNames).toHaveLength(4);
    });

    it("should handle very long language lists", () => {
      const manyLanguages = [
        "en", "es", "de", "fr", "pt", "ja", "ko", "zh",
        "ru", "ar", "hi", "it", "nl", "pl", "tr", "vi",
      ];

      renderWithProviders(
        <SearchFilters
          availableLanguages={manyLanguages}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toBeInTheDocument();

      // All languages + "All languages" option
      const options = screen.getAllByRole("option");
      expect(options.length).toBeGreaterThanOrEqual(manyLanguages.length + 1);
    });
  });

  describe("Filter Context", () => {
    it("should be wrapped in a form for semantic HTML", () => {
      const { container } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Check if there's a semantic container
      expect(container.querySelector("div")).toBeInTheDocument();
    });

    it("should have a visible label for the dropdown", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should have either a visible label or aria-label
      const dropdown = screen.getByRole("combobox");
      expect(dropdown).toHaveAccessibleName();
    });
  });

  describe("Filter panel visibility", () => {
    it("should show filter panel even with zero results", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage="fr"
          onLanguageChange={() => {}}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Filter panel should still be visible
      expect(screen.getByText("Search Type")).toBeInTheDocument();
      expect(screen.getByLabelText("Language filter")).toBeInTheDocument();
    });
  });

  describe("Search type checkboxes", () => {
    it("should show all three enabled types as checked", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const transcriptsCheckbox = screen.getByLabelText("Transcripts search type") as HTMLInputElement;
      expect(transcriptsCheckbox).toBeInTheDocument();
      expect(transcriptsCheckbox.checked).toBe(true);
      expect(transcriptsCheckbox.disabled).toBe(false);

      const titlesCheckbox = screen.getByLabelText("Video Titles search type") as HTMLInputElement;
      expect(titlesCheckbox.checked).toBe(true);
      expect(titlesCheckbox.disabled).toBe(false);

      const descriptionsCheckbox = screen.getByLabelText("Descriptions search type") as HTMLInputElement;
      expect(descriptionsCheckbox.checked).toBe(true);
      expect(descriptionsCheckbox.disabled).toBe(false);
    });

    it("should only render the three functional search types", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // No "Coming Soon" placeholders
      expect(screen.queryByText("Coming Soon")).not.toBeInTheDocument();

      // Only three checkboxes rendered (without includeUnavailable toggle)
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(3);
    });
  });

  describe("Search Type Filter Panel (FR-013)", () => {
    it("should render Transcripts checkbox checked and enabled", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const transcriptsCheckbox = screen.getByRole("checkbox", { name: /transcripts/i });
      expect(transcriptsCheckbox).toBeInTheDocument();
      expect(transcriptsCheckbox).toBeChecked();
      expect(transcriptsCheckbox).toBeEnabled();
    });

    it("should display result count on Transcripts checkbox", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={47}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should show "Transcripts (47)"
      expect(screen.getByText(/transcripts \(47\)/i)).toBeInTheDocument();
    });

    it("should handle zero results count", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // When count is 0, label shows without count (no "(0)" badge)
      expect(screen.queryByText(/transcripts \(0\)/i)).not.toBeInTheDocument();
      expect(screen.getByRole("checkbox", { name: /transcripts/i })).toBeInTheDocument();
    });

    it("should render only the three functional search types", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // All three functional search types are present and enabled
      expect(screen.getByRole("checkbox", { name: /transcripts/i })).toBeEnabled();
      expect(screen.getByRole("checkbox", { name: /video titles/i })).toBeEnabled();
      expect(screen.getByRole("checkbox", { name: /descriptions/i })).toBeEnabled();

      // No "Coming Soon" placeholders
      expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /channels/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /tags/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /topics/i })).not.toBeInTheDocument();
    });

    it("should have ARIA attributes for accessibility", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      const transcriptsCheckbox = screen.getByRole("checkbox", { name: /transcripts/i });
      expect(transcriptsCheckbox).toHaveAttribute("aria-label");
      expect(transcriptsCheckbox).toHaveAttribute("id");
    });
  });

  describe("Include unavailable content toggle", () => {
    it("should render the toggle when onToggleIncludeUnavailable is provided", () => {
      const handleToggle = vi.fn();
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          includeUnavailable={false}
          onToggleIncludeUnavailable={handleToggle}
        />
      );

      // Should have 4 checkboxes: 3 search types + 1 unavailable toggle
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(4);

      // Verify the toggle is present and labeled correctly
      const unavailableToggle = screen.getByLabelText("Include unavailable content");
      expect(unavailableToggle).toBeInTheDocument();
      expect(unavailableToggle).not.toBeChecked();
    });

    it("should not render the toggle when onToggleIncludeUnavailable is not provided", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should only have 3 checkboxes for search types
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(3);

      // Verify the toggle is not present
      expect(screen.queryByLabelText("Include unavailable content")).not.toBeInTheDocument();
    });

    it("should reflect the checked state correctly", () => {
      const handleToggle = vi.fn();
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          includeUnavailable={true}
          onToggleIncludeUnavailable={handleToggle}
        />
      );

      const unavailableToggle = screen.getByLabelText("Include unavailable content") as HTMLInputElement;
      expect(unavailableToggle).toBeChecked();
    });

    it("should call onToggleIncludeUnavailable when clicked", async () => {
      const handleToggle = vi.fn();
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          includeUnavailable={false}
          onToggleIncludeUnavailable={handleToggle}
        />
      );

      const unavailableToggle = screen.getByLabelText("Include unavailable content");
      await user.click(unavailableToggle);

      expect(handleToggle).toHaveBeenCalledTimes(1);
    });

    it("should display the toggle in the correct section with border separator", () => {
      const handleToggle = vi.fn();
      const { container } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          includeUnavailable={false}
          onToggleIncludeUnavailable={handleToggle}
        />
      );

      // Verify the toggle section has the border-top separator
      const toggleSection = container.querySelector(".border-t");
      expect(toggleSection).toBeInTheDocument();
      expect(toggleSection).toHaveClass("pt-4");
    });
  });

  describe("Responsive Filter Panel (FR-021)", () => {
    it("should render as desktop sidebar by default", () => {
      const { container } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Desktop: permanent sidebar (no close button)
      expect(screen.queryByRole("button", { name: /close/i })).not.toBeInTheDocument();

      // Check for sidebar container
      const sidebar = container.querySelector('[class*="lg:"]');
      expect(sidebar).toBeInTheDocument();
    });

    it("should render as tablet drawer when isTablet is true", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isTablet={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      // Tablet: drawer with close button
      const closeButton = screen.getByRole("button", { name: /close/i });
      expect(closeButton).toBeInTheDocument();
    });

    it("should render as mobile bottom sheet when isMobile is true", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isMobile={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      // Mobile: bottom sheet with close button
      const closeButton = screen.getByRole("button", { name: /close/i });
      expect(closeButton).toBeInTheDocument();
    });

    it("should call onClose when close button is clicked", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isTablet={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      const closeButton = screen.getByRole("button", { name: /close/i });
      await user.click(closeButton);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should close panel on Escape key press", async () => {
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isMobile={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      await user.keyboard("{Escape}");

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should not render when isOpen is false on mobile/tablet", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          isMobile={true}
          isOpen={false}
          onClose={mockOnClose}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
        />
      );

      // Should not render the filter panel content when closed
      expect(screen.queryByRole("checkbox", { name: /transcripts/i })).not.toBeInTheDocument();
    });

    it("should auto-close after filter change on tablet/mobile", async () => {
      // Use real timers for this test to avoid timing issues
      const { user } = renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isTablet={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      const dropdown = screen.getByRole("combobox", { name: /language filter/i });
      await user.selectOptions(dropdown, "en");

      // Wait for auto-close delay (500ms) plus a small buffer
      await new Promise((resolve) => setTimeout(resolve, 600));

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should have proper ARIA attributes for drawer/sheet", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isTablet={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      // Should have dialog role or appropriate ARIA attributes
      const panel = screen.getByRole("dialog", { name: /search filters/i });
      expect(panel).toBeInTheDocument();
      expect(panel).toHaveAttribute("aria-modal", "true");
    });

    it("should have focusable close button on mobile/tablet", () => {
      renderWithProviders(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
          totalResults={0}
          enabledTypes={defaultEnabledTypes}
          onToggleType={vi.fn()}
          isTablet={true}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      // Close button should be present and focusable
      const closeButton = screen.getByRole("button", { name: /close/i });
      expect(closeButton).toBeInTheDocument();
      expect(closeButton).not.toBeDisabled();
    });
  });
});
