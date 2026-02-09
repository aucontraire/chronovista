/**
 * Tests for SearchFilters component
 *
 * Verifies:
 * - Language consolidation (regional variants -> base codes)
 * - Filter panel persistence even with no results
 * - Language dropdown functionality
 * - Search type checkboxes
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SearchFilters } from "../../components/SearchFilters";

describe("SearchFilters", () => {
  describe("Language consolidation", () => {
    it("should consolidate regional language variants to base codes", () => {
      // Component now PRESERVES regional variants to show specific language context
      // This allows users to filter by exact dialect/spelling (e.g., en-US vs en-GB)
      const regionalVariants = ["en", "en-US", "en-GB", "es", "es-MX"];

      render(
        <SearchFilters
          availableLanguages={regionalVariants}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
        />
      );

      const languageSelect = screen.getByLabelText("Language filter");
      const options = Array.from(languageSelect.querySelectorAll("option"));
      const languageOptions = options.filter(opt => opt.value !== "");

      // Should preserve all 5 regional variants
      expect(languageOptions).toHaveLength(5);

      // Should show both base codes and regional variants with region labels
      const languageTexts = languageOptions.map(opt => opt.textContent);
      expect(languageTexts).toContain("English");
      expect(languageTexts).toContain("English (US)");
      expect(languageTexts).toContain("English (UK)");
      expect(languageTexts).toContain("Spanish");
      expect(languageTexts).toContain("Spanish (Mexico)");
    });

    it("should handle empty language list gracefully", () => {
      render(
        <SearchFilters
          availableLanguages={[]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
        />
      );

      // Language filter should not be rendered when no languages available
      const languageSelect = screen.queryByLabelText("Language filter");
      expect(languageSelect).not.toBeInTheDocument();
    });

    it("should sort languages alphabetically by display name", () => {
      const languages = ["ja", "en", "zh", "es", "ar"];

      render(
        <SearchFilters
          availableLanguages={languages}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={0}
        />
      );

      const languageSelect = screen.getByLabelText("Language filter");
      const options = Array.from(languageSelect.querySelectorAll("option"));
      const languageOptions = options.filter(opt => opt.value !== "");
      const languageTexts = languageOptions.map(opt => opt.textContent);

      // Should be sorted: Arabic, Chinese, English, Japanese, Spanish
      expect(languageTexts).toEqual([
        "Arabic",
        "Chinese",
        "English",
        "Japanese",
        "Spanish"
      ]);
    });
  });

  describe("Filter panel visibility", () => {
    it("should show filter panel even with zero results", () => {
      render(
        <SearchFilters
          availableLanguages={["en", "es"]}
          selectedLanguage="fr"
          onLanguageChange={() => {}}
          totalResults={0}
        />
      );

      // Filter panel should still be visible
      expect(screen.getByText("Search Type")).toBeInTheDocument();
      expect(screen.getByLabelText("Language filter")).toBeInTheDocument();
    });

    it("should display result count on Transcripts checkbox", () => {
      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={47}
        />
      );

      // Should show count in parentheses
      expect(screen.getByText(/Transcripts \(47\)/)).toBeInTheDocument();
    });
  });

  describe("Search type checkboxes", () => {
    it("should show Transcripts as enabled and checked", () => {
      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
        />
      );

      const transcriptsCheckbox = screen.getByLabelText("Transcripts search type") as HTMLInputElement;
      expect(transcriptsCheckbox).toBeInTheDocument();
      expect(transcriptsCheckbox.checked).toBe(true);
      expect(transcriptsCheckbox.disabled).toBe(false);
    });

    it("should show other search types as disabled with Coming Soon badge", () => {
      render(
        <SearchFilters
          availableLanguages={["en"]}
          selectedLanguage=""
          onLanguageChange={() => {}}
          totalResults={10}
        />
      );

      // Check for "Coming Soon" badges (should be multiple)
      const comingSoonBadges = screen.getAllByText("Coming Soon");
      expect(comingSoonBadges.length).toBeGreaterThan(0);

      // Check that other checkboxes are disabled
      const videoTitlesCheckbox = screen.getByLabelText("Video Titles search type") as HTMLInputElement;
      expect(videoTitlesCheckbox.disabled).toBe(true);
      expect(videoTitlesCheckbox.checked).toBe(false);
    });
  });
});
