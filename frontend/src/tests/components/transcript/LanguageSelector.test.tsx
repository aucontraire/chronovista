/**
 * Unit tests for LanguageSelector component.
 *
 * Tests language code display, WAI-ARIA tabs pattern, and quality indicators.
 *
 * @module tests/components/transcript/LanguageSelector
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LanguageSelector } from "../../../components/transcript/LanguageSelector";
import type { TranscriptLanguage } from "../../../types/transcript";

describe("LanguageSelector", () => {
  const mockOnLanguageChange = vi.fn();

  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: "en",
      language_name: "English",
      transcript_type: "manual",
    },
    {
      language_code: "en-GB",
      language_name: "English (UK)",
      transcript_type: "manual",
    },
    {
      language_code: "pt-BR",
      language_name: "Portuguese (Brazil)",
      transcript_type: "auto_generated",
    },
    {
      language_code: "es",
      language_name: "Spanish",
      transcript_type: "auto_generated",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("language code display", () => {
    it("displays full BCP-47 code for language variants (e.g., EN-gb)", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // First tab (en) should show "EN"
      expect(tabs[0]).toHaveTextContent("EN");
      expect(tabs[0]).not.toHaveTextContent("EN-");

      // Second tab (en-GB) should show "EN-gb" (primary uppercase, variant lowercase)
      expect(tabs[1]).toHaveTextContent("EN-gb");

      // Third tab (pt-BR) should show "PT-br"
      expect(tabs[2]).toHaveTextContent("PT-br");

      // Fourth tab (es) should show "ES"
      expect(tabs[3]).toHaveTextContent("ES");
      expect(tabs[3]).not.toHaveTextContent("ES-");
    });

    it("distinguishes between en and en-GB with different labels", () => {
      const twoEnglishVariants: TranscriptLanguage[] = [
        { language_code: "en", language_name: "English", transcript_type: "manual" },
        { language_code: "en-GB", language_name: "English (UK)", transcript_type: "manual" },
      ];

      render(
        <LanguageSelector
          languages={twoEnglishVariants}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // First tab should contain "EN" but NOT "EN-"
      expect(tabs[0]).toHaveTextContent("EN");
      // Second tab should contain "EN-gb"
      expect(tabs[1]).toHaveTextContent("EN-gb");

      // The visible text (before the sr-only span) should be different
      // Check using the id attribute to verify they're distinct
      expect(tabs[0]).toHaveAttribute("id", "tab-en");
      expect(tabs[1]).toHaveAttribute("id", "tab-en-GB");
    });
  });

  describe("quality indicators", () => {
    it("shows checkmark for manual/CC transcripts", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // Manual transcripts (en, en-GB) should have checkmark (✓ = &#10003;)
      expect(tabs[0].textContent).toContain("✓"); // en
      expect(tabs[1].textContent).toContain("✓"); // en-GB
    });

    it("does not show checkmark for auto-generated transcripts", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // Auto-generated transcripts (pt-BR, es) should NOT have checkmark
      expect(tabs[2].textContent).not.toContain("✓"); // pt-BR
      expect(tabs[3].textContent).not.toContain("✓"); // es
    });
  });

  describe("selection behavior", () => {
    it("marks selected language tab as aria-selected", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en-GB"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // en-GB (index 1) should be selected
      expect(tabs[1]).toHaveAttribute("aria-selected", "true");
      // en (index 0) should not be selected
      expect(tabs[0]).toHaveAttribute("aria-selected", "false");
    });

    it("calls onLanguageChange when tab is clicked", async () => {
      vi.useFakeTimers();

      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");
      fireEvent.click(tabs[1]); // Click en-GB tab

      // Fast-forward through debounce
      await vi.advanceTimersByTimeAsync(200);

      expect(mockOnLanguageChange).toHaveBeenCalledWith("en-GB");

      vi.useRealTimers();
    });
  });

  describe("accessibility", () => {
    it("has correct ARIA tablist role", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(screen.getByRole("tablist")).toBeInTheDocument();
    });

    it("includes language name in screen reader text", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // The accessible name should contain the full language name
      expect(tabs[1]).toHaveAccessibleName(/english \(uk\)/i);
    });

    it("indicates high quality transcript in screen reader text", () => {
      render(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");

      // Manual transcripts should have "high quality" in accessible name
      expect(tabs[0]).toHaveAccessibleName(/high quality/i);
      expect(tabs[1]).toHaveAccessibleName(/high quality/i);

      // Auto-generated should NOT have "high quality"
      expect(tabs[2]).not.toHaveAccessibleName(/high quality/i);
    });
  });

  describe("empty state", () => {
    it("renders nothing when languages array is empty", () => {
      const { container } = render(
        <LanguageSelector
          languages={[]}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });
});
