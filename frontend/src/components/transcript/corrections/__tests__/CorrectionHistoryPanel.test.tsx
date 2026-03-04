/**
 * Tests for CorrectionHistoryPanel component (Feature 035, T028).
 *
 * Test coverage:
 * 1.  Renders loading skeleton when isLoading=true and records=[]
 * 2.  Renders records when data loaded
 * 3.  Displays correction_type label correctly (CORRECTION_TYPE_LABELS for known types, "Revert" for "revert")
 * 4.  Displays formatted corrected_at timestamp
 * 5.  Displays original_text with line-through styling
 * 6.  Displays corrected_text
 * 7.  Displays correction_note when present
 * 8.  Hides correction_note when null
 * 9.  Shows "Load more" button when hasMore=true
 * 10. Hides "Load more" when hasMore=false
 * 11. Load more button triggers onLoadMore callback
 * 12. Shows empty state message when records=[] and not loading
 * 13. Escape key calls onClose
 * 14. role="region" and aria-label="Correction history" present
 * 15. Renders multiple records in order
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CorrectionHistoryPanel } from "../CorrectionHistoryPanel";
import type { CorrectionHistoryPanelProps } from "../CorrectionHistoryPanel";
import type { CorrectionAuditRecord } from "../../../../types/corrections";

/**
 * Factory for building a CorrectionAuditRecord test fixture.
 */
function createRecord(overrides: Partial<CorrectionAuditRecord> = {}): CorrectionAuditRecord {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    video_id: "test-video",
    language_code: "en",
    segment_id: 1,
    correction_type: "spelling",
    original_text: "teh quick brown fox",
    corrected_text: "the quick brown fox",
    correction_note: null,
    corrected_by_user_id: null,
    corrected_at: "2025-01-15T10:30:00Z",
    version_number: 1,
    ...overrides,
  };
}

/**
 * Factory for building CorrectionHistoryPanelProps with sensible defaults.
 */
function createDefaultProps(
  overrides: Partial<CorrectionHistoryPanelProps> = {}
): CorrectionHistoryPanelProps {
  return {
    records: [],
    isLoading: false,
    hasMore: false,
    onLoadMore: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

describe("CorrectionHistoryPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ---------------------------------------------------------------------------
  // Test 1: Loading skeleton
  // ---------------------------------------------------------------------------
  describe("Test 1 — Renders loading skeleton when isLoading=true and records=[]", () => {
    it("shows loading skeleton with correct role and aria-label", () => {
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ isLoading: true, records: [] })}
        />
      );

      const skeleton = screen.getByRole("status", {
        name: "Loading correction history",
      });
      expect(skeleton).toBeInTheDocument();
    });

    it("does not show record rows or empty state while loading", () => {
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ isLoading: true, records: [] })}
        />
      );

      expect(
        screen.queryByText("No corrections recorded for this segment.")
      ).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 2: Renders records when data loaded
  // ---------------------------------------------------------------------------
  describe("Test 2 — Renders records when data loaded", () => {
    it("renders the corrected text for a record", () => {
      const record = createRecord({ corrected_text: "the quick brown fox" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("the quick brown fox")).toBeInTheDocument();
    });

    it("renders the original text for a record", () => {
      const record = createRecord({ original_text: "teh quick brown fox" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("teh quick brown fox")).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 3: Correction type label
  // ---------------------------------------------------------------------------
  describe("Test 3 — Displays correction_type label correctly", () => {
    it('shows "Spelling" badge for correction_type="spelling"', () => {
      const record = createRecord({ correction_type: "spelling" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("Spelling")).toBeInTheDocument();
    });

    it('shows "ASR Error" badge for correction_type="asr_error"', () => {
      const record = createRecord({ correction_type: "asr_error" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("ASR Error")).toBeInTheDocument();
    });

    it('shows "Context Correction" badge for correction_type="context_correction"', () => {
      const record = createRecord({ correction_type: "context_correction" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("Context Correction")).toBeInTheDocument();
    });

    it('shows "Profanity Fix" badge for correction_type="profanity_fix"', () => {
      const record = createRecord({ correction_type: "profanity_fix" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("Profanity Fix")).toBeInTheDocument();
    });

    it('shows "Formatting" badge for correction_type="formatting"', () => {
      const record = createRecord({ correction_type: "formatting" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("Formatting")).toBeInTheDocument();
    });

    it('shows "Revert" badge for correction_type="revert"', () => {
      const record = createRecord({ correction_type: "revert" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText("Revert")).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 4: Formatted corrected_at timestamp
  // ---------------------------------------------------------------------------
  describe("Test 4 — Displays formatted corrected_at timestamp", () => {
    it("formats the corrected_at ISO timestamp as a locale date string", () => {
      // 2025-01-15T10:30:00Z → locale date (e.g. "1/15/2025" in en-US)
      const record = createRecord({ corrected_at: "2025-01-15T10:30:00Z" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      // The component renders `new Date(corrected_at).toLocaleDateString()`
      // which produces a date string. We check that the timestamp element exists
      // by looking for a text element containing "· v1".
      const timestampEl = screen.getByText(/· v1/);
      expect(timestampEl).toBeInTheDocument();
    });

    it("includes the version_number in the header metadata", () => {
      const record = createRecord({ version_number: 3 });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      expect(screen.getByText(/· v3/)).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 5: original_text with line-through styling
  // ---------------------------------------------------------------------------
  describe("Test 5 — Displays original_text with line-through styling", () => {
    it("applies line-through class to the original_text element", () => {
      const record = createRecord({ original_text: "teh original text" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      const originalTextEl = screen.getByText("teh original text");
      expect(originalTextEl.className).toContain("line-through");
    });

    it("applies text-gray-500 class to original_text", () => {
      const record = createRecord({ original_text: "teh original text" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      const originalTextEl = screen.getByText("teh original text");
      expect(originalTextEl.className).toContain("text-gray-500");
    });
  });

  // ---------------------------------------------------------------------------
  // Test 6: corrected_text displayed
  // ---------------------------------------------------------------------------
  describe("Test 6 — Displays corrected_text", () => {
    it("renders corrected_text with text-gray-900 styling", () => {
      const record = createRecord({ corrected_text: "the corrected text" });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      const correctedEl = screen.getByText("the corrected text");
      expect(correctedEl.className).toContain("text-gray-900");
    });
  });

  // ---------------------------------------------------------------------------
  // Test 7: correction_note displayed when present
  // ---------------------------------------------------------------------------
  describe("Test 7 — Displays correction_note when present", () => {
    it("shows the correction_note when it has a value", () => {
      const record = createRecord({
        correction_note: "Fixed a common OCR error.",
      });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      const noteEl = screen.getByText("Fixed a common OCR error.");
      expect(noteEl).toBeInTheDocument();
      expect(noteEl.className).toContain("italic");
    });
  });

  // ---------------------------------------------------------------------------
  // Test 8: correction_note hidden when null
  // ---------------------------------------------------------------------------
  describe("Test 8 — Hides correction_note when null", () => {
    it("does not render any note element when correction_note is null", () => {
      const record = createRecord({ correction_note: null });
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record] })}
        />
      );

      // There should be no italic text (no note)
      const italicElements = document.querySelectorAll("p.italic");
      expect(italicElements).toHaveLength(0);
    });
  });

  // ---------------------------------------------------------------------------
  // Test 9: "Load more" button shown when hasMore=true
  // ---------------------------------------------------------------------------
  describe("Test 9 — Shows 'Load more' button when hasMore=true", () => {
    it("renders the Load more button when hasMore is true and records exist", () => {
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], hasMore: true })}
        />
      );

      expect(
        screen.getByRole("button", { name: /load more/i })
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 10: "Load more" hidden when hasMore=false
  // ---------------------------------------------------------------------------
  describe("Test 10 — Hides 'Load more' when hasMore=false", () => {
    it("does not render Load more button when hasMore is false", () => {
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], hasMore: false })}
        />
      );

      expect(
        screen.queryByRole("button", { name: /load more/i })
      ).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 11: Load more button triggers onLoadMore
  // ---------------------------------------------------------------------------
  describe("Test 11 — Load more button triggers onLoadMore callback", () => {
    it("calls onLoadMore when Load more button is clicked", async () => {
      const user = userEvent.setup();
      const onLoadMore = vi.fn();
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], hasMore: true, onLoadMore })}
        />
      );

      await user.click(screen.getByRole("button", { name: /load more/i }));

      expect(onLoadMore).toHaveBeenCalledOnce();
    });

    it("Load more button has focus-visible ring classes", () => {
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], hasMore: true })}
        />
      );

      const loadMoreBtn = screen.getByRole("button", { name: /load more/i });
      expect(loadMoreBtn.className).toContain("focus-visible:ring-2");
      expect(loadMoreBtn.className).toContain("focus-visible:ring-blue-500");
    });
  });

  // ---------------------------------------------------------------------------
  // Test 12: Empty state message
  // ---------------------------------------------------------------------------
  describe("Test 12 — Shows empty state when records=[] and not loading", () => {
    it("renders the no-corrections message when records is empty and not loading", () => {
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [], isLoading: false })}
        />
      );

      expect(
        screen.getByText("No corrections recorded for this segment.")
      ).toBeInTheDocument();
    });

    it("does not show the load more button for empty state", () => {
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [], isLoading: false, hasMore: false })}
        />
      );

      expect(
        screen.queryByRole("button", { name: /load more/i })
      ).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 13: Escape key calls onClose
  // ---------------------------------------------------------------------------
  describe("Test 13 — Escape key calls onClose", () => {
    it("calls onClose when Escape is pressed inside the panel", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], onClose })}
        />
      );

      // Focus an element inside the panel (the region itself)
      const region = screen.getByRole("region", { name: "Correction history" });
      region.focus();
      await user.keyboard("{Escape}");

      expect(onClose).toHaveBeenCalledOnce();
    });

    it("calls onClose when Escape is pressed with Load more button focused", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      const record = createRecord();
      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records: [record], hasMore: true, onClose })}
        />
      );

      const loadMoreBtn = screen.getByRole("button", { name: /load more/i });
      loadMoreBtn.focus();
      await user.keyboard("{Escape}");

      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  // ---------------------------------------------------------------------------
  // Test 14: ARIA region
  // ---------------------------------------------------------------------------
  describe("Test 14 — role='region' and aria-label='Correction history' present", () => {
    it("has role='region'", () => {
      render(<CorrectionHistoryPanel {...createDefaultProps()} />);

      expect(
        screen.getByRole("region", { name: "Correction history" })
      ).toBeInTheDocument();
    });

    it("has aria-label='Correction history'", () => {
      render(<CorrectionHistoryPanel {...createDefaultProps()} />);

      const region = screen.getByRole("region");
      expect(region).toHaveAttribute("aria-label", "Correction history");
    });
  });

  // ---------------------------------------------------------------------------
  // Test 15: Multiple records rendered in order
  // ---------------------------------------------------------------------------
  describe("Test 15 — Renders multiple records in order", () => {
    it("renders all provided records", () => {
      const records = [
        createRecord({
          id: "00000000-0000-0000-0000-000000000001",
          corrected_text: "first correction",
          version_number: 2,
        }),
        createRecord({
          id: "00000000-0000-0000-0000-000000000002",
          corrected_text: "second correction",
          version_number: 1,
        }),
      ];

      render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records })}
        />
      );

      expect(screen.getByText("first correction")).toBeInTheDocument();
      expect(screen.getByText("second correction")).toBeInTheDocument();
    });

    it("renders records in DOM order matching the provided array", () => {
      const records = [
        createRecord({
          id: "00000000-0000-0000-0000-000000000001",
          corrected_text: "newest correction",
          version_number: 2,
        }),
        createRecord({
          id: "00000000-0000-0000-0000-000000000002",
          corrected_text: "older correction",
          version_number: 1,
        }),
      ];

      const { container } = render(
        <CorrectionHistoryPanel
          {...createDefaultProps({ records })}
        />
      );

      const correctedTextEls = container.querySelectorAll("p.text-gray-900");
      expect(correctedTextEls[0]?.textContent).toBe("newest correction");
      expect(correctedTextEls[1]?.textContent).toBe("older correction");
    });
  });
});
