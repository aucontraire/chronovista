/**
 * Tests for LanguageSelector component.
 *
 * Merged from two divergent copies (#309 Phase 3 consolidation):
 * - BCP-47 code display suite: verifies full region-qualified codes
 *   (e.g. "EN-gb", "PT-br") render distinctly from plain 2-letter codes,
 *   plus quality indicators, basic ARIA, and the empty-state case.
 * - Full behavior suite: rendering, tab selection, quality indicators
 *   (including `auto_synced`), keyboard navigation (NFR-A03), ARIA
 *   attributes, screen-reader announcements (NFR-A04), and visual styling.
 *
 * Dropped (documented, not silently lost):
 * - "has correct ARIA tablist role" (basic-suite) collapsed into "should
 *   render tablist with proper ARIA attributes" (full-suite) — same intent,
 *   and the kept version's `getByRole('tablist', { name: ... })` already
 *   implies the role assertion the basic-suite version made.
 * - "renders nothing when languages array is empty" (basic-suite) collapsed
 *   into "should render nothing when languages array is empty" (full-suite)
 *   — identical intent and assertion (`container.firstChild` is null).
 *
 * The two suites use different fixture data (region-variant codes vs. plain
 * codes across `manual`/`auto_synced`/`auto_generated` types), so their
 * checkmark/quality-indicator cases are kept side by side rather than forced
 * into a shared fixture — they exercise different `transcript_type` values.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ReactElement } from "react";
import { act } from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LanguageSelector } from "../LanguageSelector";
import type { TranscriptLanguage } from "../../../types/transcript";

/**
 * Local render helper (no `tests/test-utils` import — #159 typecheck trap).
 * LanguageSelector itself needs no router/query context, but returns a
 * configured `user` for interaction tests, matching the source suites.
 */
function renderWithProviders(ui: ReactElement) {
  const result = render(ui);
  return {
    ...result,
    user: userEvent.setup(),
  };
}

describe("LanguageSelector — code display & quality indicators (region-variant fixtures)", () => {
  const mockOnLanguageChange = vi.fn();

  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: "en",
      language_name: "English",
      transcript_type: "manual",
      is_translatable: true,
      downloaded_at: "2023-01-01T00:00:00Z",
    },
    {
      language_code: "en-GB",
      language_name: "English (UK)",
      transcript_type: "manual",
      is_translatable: true,
      downloaded_at: "2023-01-01T00:00:00Z",
    },
    {
      language_code: "pt-BR",
      language_name: "Portuguese (Brazil)",
      transcript_type: "auto_generated",
      is_translatable: false,
      downloaded_at: "2023-01-01T00:00:00Z",
    },
    {
      language_code: "es",
      language_name: "Spanish",
      transcript_type: "auto_generated",
      is_translatable: false,
      downloaded_at: "2023-01-01T00:00:00Z",
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
        { language_code: "en", language_name: "English", transcript_type: "manual", is_translatable: true, downloaded_at: "2023-01-01T00:00:00Z" },
        { language_code: "en-GB", language_name: "English (UK)", transcript_type: "manual", is_translatable: true, downloaded_at: "2023-01-01T00:00:00Z" },
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
      expect(tabs[0]?.textContent).toContain("✓"); // en
      expect(tabs[1]?.textContent).toContain("✓"); // en-GB
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
      expect(tabs[2]?.textContent).not.toContain("✓"); // pt-BR
      expect(tabs[3]?.textContent).not.toContain("✓"); // es
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
      const enGbTab = tabs[1];
      if (enGbTab) {
        fireEvent.click(enGbTab); // Click en-GB tab
      }

      // Fast-forward through debounce
      await vi.advanceTimersByTimeAsync(200);

      expect(mockOnLanguageChange).toHaveBeenCalledWith("en-GB");

      vi.useRealTimers();
    });
  });

  describe("accessibility", () => {
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
});

describe("LanguageSelector — full behavior suite (rendering, keyboard nav, ARIA, announcements)", () => {
  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: "en",
      language_name: "English",
      transcript_type: "manual",
      is_translatable: true,
      downloaded_at: "2024-01-15T10:00:00Z",
    },
    {
      language_code: "es",
      language_name: "Spanish",
      transcript_type: "auto_synced",
      is_translatable: true,
      downloaded_at: "2024-01-15T10:05:00Z",
    },
    {
      language_code: "fr",
      language_name: "French",
      transcript_type: "auto_generated",
      is_translatable: false,
      downloaded_at: "2024-01-15T10:10:00Z",
    },
  ];

  const mockOnLanguageChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Rendering", () => {
    it("should render tablist with proper ARIA attributes", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tablist = screen.getByRole("tablist", { name: "Transcript languages" });
      expect(tablist).toBeInTheDocument();
    });

    it("should render all language tabs", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const tabs = screen.getAllByRole("tab");
      expect(tabs).toHaveLength(3);
    });

    it("should render language labels as uppercase 2-letter codes", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(screen.getByRole("tab", { name: /english/i })).toHaveTextContent("EN");
      expect(screen.getByRole("tab", { name: /spanish/i })).toHaveTextContent("ES");
      expect(screen.getByRole("tab", { name: /french/i })).toHaveTextContent("FR");
    });

    it("should render nothing when languages array is empty", () => {
      const { container } = renderWithProviders(
        <LanguageSelector
          languages={[]}
          selectedLanguage=""
          onLanguageChange={mockOnLanguageChange}
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });

  describe("Tab Selection", () => {
    it('should mark selected tab with aria-selected="true"', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      expect(spanishTab).toHaveAttribute("aria-selected", "true");
    });

    it('should mark non-selected tabs with aria-selected="false"', () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      const frenchTab = screen.getByRole("tab", { name: /french/i });
      expect(englishTab).toHaveAttribute("aria-selected", "false");
      expect(frenchTab).toHaveAttribute("aria-selected", "false");
    });

    it("should call onLanguageChange when tab is clicked", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      await user.click(spanishTab);

      await waitFor(() => {
        expect(mockOnLanguageChange).toHaveBeenCalledWith("es");
      });
    });

    it("should NOT call onLanguageChange when already selected tab is clicked", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      await user.click(englishTab);

      await waitFor(() => {
        expect(mockOnLanguageChange).not.toHaveBeenCalled();
      });
    });
  });

  describe("Quality Indicators", () => {
    it("should show checkmark for manual transcripts", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      expect(englishTab).toHaveTextContent("✓");
    });

    it("should show checkmark for auto_synced transcripts", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      expect(spanishTab).toHaveTextContent("✓");
    });

    it("should NOT show checkmark for auto_generated transcripts", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole("tab", { name: /french/i });
      expect(frenchTab).not.toHaveTextContent("✓");
    });

    it("should include quality indicator in screen reader text", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english.*high quality/i });
      expect(englishTab).toBeInTheDocument();
    });
  });

  describe("Keyboard Navigation (NFR-A03)", () => {
    it("should move focus to next tab with ArrowRight", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      englishTab.focus();

      await user.keyboard("{ArrowRight}");

      await waitFor(() => {
        const spanishTab = screen.getByRole("tab", { name: /spanish/i });
        expect(spanishTab).toHaveFocus();
      });
    });

    it("should move focus to previous tab with ArrowLeft", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      spanishTab.focus();

      await user.keyboard("{ArrowLeft}");

      await waitFor(() => {
        const englishTab = screen.getByRole("tab", { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it("should wrap to first tab when ArrowRight on last tab", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole("tab", { name: /french/i });
      frenchTab.focus();

      await user.keyboard("{ArrowRight}");

      await waitFor(() => {
        const englishTab = screen.getByRole("tab", { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it("should wrap to last tab when ArrowLeft on first tab", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      englishTab.focus();

      await user.keyboard("{ArrowLeft}");

      await waitFor(() => {
        const frenchTab = screen.getByRole("tab", { name: /french/i });
        expect(frenchTab).toHaveFocus();
      });
    });

    it("should move to first tab with Home key", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="fr"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const frenchTab = screen.getByRole("tab", { name: /french/i });
      frenchTab.focus();

      await user.keyboard("{Home}");

      await waitFor(() => {
        const englishTab = screen.getByRole("tab", { name: /english/i });
        expect(englishTab).toHaveFocus();
      });
    });

    it("should move to last tab with End key", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      englishTab.focus();

      await user.keyboard("{End}");

      await waitFor(() => {
        const frenchTab = screen.getByRole("tab", { name: /french/i });
        expect(frenchTab).toHaveFocus();
      });
    });

    it("should select tab when navigating with arrow keys", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      englishTab.focus();

      await user.keyboard("{ArrowRight}");

      await waitFor(() => {
        expect(mockOnLanguageChange).toHaveBeenCalledWith("es");
      });
    });
  });

  describe("ARIA Attributes", () => {
    it("should have proper aria-controls attribute", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
          contentId="test-content"
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      expect(englishTab).toHaveAttribute("aria-controls", "test-content");
    });

    it("should use default content ID when not provided", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      expect(englishTab).toHaveAttribute("aria-controls", "transcript-content");
    });

    it("should have proper tabindex for roving tabindex pattern", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      const frenchTab = screen.getByRole("tab", { name: /french/i });

      // Selected tab should have tabindex="0"
      expect(spanishTab).toHaveAttribute("tabindex", "0");
      // Other tabs should have tabindex="-1"
      expect(englishTab).toHaveAttribute("tabindex", "-1");
      expect(frenchTab).toHaveAttribute("tabindex", "-1");
    });

    it("should have id attribute for each tab", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      expect(englishTab).toHaveAttribute("id", "tab-en");
    });
  });

  describe("Accessibility Announcements (NFR-A04)", () => {
    it("should announce language change to screen readers", async () => {
      const { user } = renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="en"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const spanishTab = screen.getByRole("tab", { name: /spanish/i });
      await user.click(spanishTab);

      await waitFor(() => {
        const announcement = screen.getByRole("status");
        expect(announcement).toHaveTextContent("Transcript language changed to Spanish");
      });
    });

    it("should clear announcement after it has been read", async () => {
      vi.useFakeTimers();

      try {
        renderWithProviders(
          <LanguageSelector
            languages={mockLanguages}
            selectedLanguage="en"
            onLanguageChange={mockOnLanguageChange}
          />
        );

        const spanishTab = screen.getByRole("tab", { name: /spanish/i });

        // Click in act()
        act(() => {
          spanishTab.click();
        });

        // Fast-forward past debounce and announcement clear
        await act(async () => {
          await vi.advanceTimersByTimeAsync(2000);
        });

        const announcement = screen.getByRole("status");
        expect(announcement).toHaveTextContent("");
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe("Visual Styling", () => {
    it("should have different styling for selected tab", () => {
      renderWithProviders(
        <LanguageSelector
          languages={mockLanguages}
          selectedLanguage="es"
          onLanguageChange={mockOnLanguageChange}
        />
      );

      const englishTab = screen.getByRole("tab", { name: /english/i });
      const spanishTab = screen.getByRole("tab", { name: /spanish/i });

      // Selected tab should have blue background
      expect(spanishTab).toHaveClass("bg-blue-600");
      // Non-selected tab should have gray background
      expect(englishTab).toHaveClass("bg-gray-100");
    });
  });
});
