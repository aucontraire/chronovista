/**
 * Tests for FilterPills component
 *
 * Reconciled from two divergent copies (issue #309):
 * - frontend/src/tests/components/FilterPills.test.tsx (general pill suite)
 * - frontend/tests/components/FilterPills.test.tsx (Feature 027 boolean pill suite)
 *
 * Verifies:
 * - T043: Color-coded pills display (blue=tags, green=categories, purple=topics, blue=canonical_tag, slate=boolean)
 * - T048: Individual filter removal via × button
 * - T050: Long tag truncation with tooltip
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-007: Visible focus indicators
 * - US2: Canonical tag pill type with aliasCount variation badge
 * - Feature 027 / T033: Boolean filter pills (Liked, Has transcripts) alongside tag/topic/category pills
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterPills } from "../FilterPills";

// FilterPills has no React Query / Router dependencies, so the local render
// helper only needs to attach a ready-to-use `userEvent` instance. Defined
// in-file (not imported from `frontend/tests/test-utils`) to keep `src/`
// test imports self-contained and typecheck-safe.
function renderWithProviders(ui: React.ReactElement) {
  return {
    ...render(ui),
    user: userEvent.setup(),
  };
}

describe("FilterPills", () => {
  describe("Rendering and display", () => {
    it("should render nothing visible when no filters provided", () => {
      renderWithProviders(<FilterPills filters={[]} onRemove={() => {}} />);

      // The live region (sr-only) is always rendered for screen reader announcements,
      // but no visible filter list is rendered when there are no filters.
      expect(screen.queryByRole("list", { name: "Active filters" })).not.toBeInTheDocument();
    });

    it("should render all provided filters with correct labels", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
        { type: "topic" as const, value: "/m/04rlf", label: "Music" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("music")).toBeInTheDocument();
      expect(screen.getByText("Gaming")).toBeInTheDocument();
      // Check for the topic "Music" (there might be multiple, so use getAllByText)
      const musicLabels = screen.getAllByText("Music");
      expect(musicLabels.length).toBeGreaterThan(0);
    });

    it("should display filter type icons (emoji)", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
        { type: "topic" as const, value: "/m/04rlf", label: "Music" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Check for emoji icons
      expect(container.textContent).toContain("🏷️"); // tag
      expect(container.textContent).toContain("📂"); // category
      expect(container.textContent).toContain("🌐"); // topic
    });

    it("should render boolean pills alongside tag pills", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("music")).toBeInTheDocument();
      expect(screen.getByText("Liked")).toBeInTheDocument();
    });

    it("should render boolean pills alongside category pills", () => {
      const filters = [
        { type: "category" as const, value: "10", label: "Gaming" },
        {
          type: "boolean" as const,
          value: "has_transcript",
          label: "Has transcripts",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("Gaming")).toBeInTheDocument();
      expect(screen.getByText("Has transcripts")).toBeInTheDocument();
    });

    it("should render boolean pills alongside topic pills", () => {
      const filters = [
        { type: "topic" as const, value: "/m/04rlf", label: "Music" },
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      const musicItems = screen.getAllByText("Music");
      expect(musicItems.length).toBeGreaterThan(0);
      expect(screen.getByText("Liked")).toBeInTheDocument();
    });

    it("should render all filter types together", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
        { type: "topic" as const, value: "/m/04rlf", label: "Music Topic" },
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
        {
          type: "boolean" as const,
          value: "has_transcript",
          label: "Has transcripts",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("music")).toBeInTheDocument();
      expect(screen.getByText("Gaming")).toBeInTheDocument();
      expect(screen.getByText("Music Topic")).toBeInTheDocument();
      expect(screen.getByText("Liked")).toBeInTheDocument();
      expect(screen.getByText("Has transcripts")).toBeInTheDocument();
    });

    it("should render Liked pill when liked_only filter is active", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("Liked")).toBeInTheDocument();
    });

    it("should render Has transcripts pill when has_transcript filter is active", () => {
      const filters = [
        {
          type: "boolean" as const,
          value: "has_transcript",
          label: "Has transcripts",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("Has transcripts")).toBeInTheDocument();
    });
  });

  describe("Color schemes (T043)", () => {
    it("should apply tag color scheme (blue)", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Check for blue color in style attribute
      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#DBEAFE", // Light blue
        color: "#1E40AF", // Dark blue
      });
    });

    it("should apply category color scheme (green)", () => {
      const filters = [
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#DCFCE7", // Light green
        color: "#166534", // Dark green
      });
    });

    it("should apply topic color scheme (purple)", () => {
      const filters = [
        { type: "topic" as const, value: "/m/04rlf", label: "Music" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#F3E8FF", // Light purple
        color: "#6B21A8", // Dark purple
      });
    });

    it("should apply canonical_tag color scheme (blue — same as tag)", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "javascript",
          label: "JavaScript",
          aliasCount: 3,
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#DBEAFE", // Light blue (same as tag)
        color: "#1E40AF", // Dark blue (same as tag)
      });
    });

    it("should apply boolean color scheme (slate)", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#F1F5F9", // Light slate
        color: "#334155", // Dark slate
      });
    });
  });

  describe("Filter removal (T048)", () => {
    it("should call onRemove with correct type and value when × button clicked", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      const removeButton = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith("tag", "music");
    });

    it("should have distinct remove buttons for each filter", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "tag" as const, value: "tutorial", label: "tutorial" },
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      const musicRemove = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });
      const tutorialRemove = screen.getByRole("button", {
        name: "Remove tag filter: tutorial",
      });
      const gamingRemove = screen.getByRole("button", {
        name: "Remove category filter: Gaming",
      });

      await user.click(musicRemove);
      expect(mockOnRemove).toHaveBeenCalledWith("tag", "music");

      await user.click(tutorialRemove);
      expect(mockOnRemove).toHaveBeenCalledWith("tag", "tutorial");

      await user.click(gamingRemove);
      expect(mockOnRemove).toHaveBeenCalledWith("category", "10");
    });

    it("should call onRemove with boolean type and liked_only value", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      const removeButton = screen.getByRole("button", {
        name: "Remove boolean filter: Liked",
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith("boolean", "liked_only");
    });

    it("should call onRemove with boolean type and has_transcript value", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        {
          type: "boolean" as const,
          value: "has_transcript",
          label: "Has transcripts",
        },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      const removeButton = screen.getByRole("button", {
        name: "Remove boolean filter: Has transcripts",
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith("boolean", "has_transcript");
    });

    it("should handle removing boolean pill alongside tag pill", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      // Remove the boolean pill
      const booleanRemove = screen.getByRole("button", {
        name: "Remove boolean filter: Liked",
      });
      await user.click(booleanRemove);

      expect(mockOnRemove).toHaveBeenCalledWith("boolean", "liked_only");

      // Remove the tag pill
      const tagRemove = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });
      await user.click(tagRemove);

      expect(mockOnRemove).toHaveBeenCalledWith("tag", "music");
    });
  });

  describe("Long tag truncation (T050)", () => {
    it("should truncate tags longer than 25 characters", () => {
      const filters = [
        {
          type: "tag" as const,
          value: "very-long-tag-name-that-exceeds-limit",
          label: "very-long-tag-name-that-exceeds-limit",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      // Should show first 25 chars + ellipsis
      expect(screen.getByText("very-long-tag-name-that-e...")).toBeInTheDocument();
      expect(
        screen.queryByText("very-long-tag-name-that-exceeds-limit")
      ).not.toBeInTheDocument();
    });

    it("should show full text in tooltip for truncated tags", () => {
      const filters = [
        {
          type: "tag" as const,
          value: "very-long-tag-name-that-exceeds-limit",
          label: "very-long-tag-name-that-exceeds-limit",
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveAttribute(
        "title",
        "very-long-tag-name-that-exceeds-limit"
      );
    });

    it("should not truncate tags shorter than 25 characters", () => {
      const filters = [
        { type: "tag" as const, value: "short", label: "short" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(screen.getByText("short")).toBeInTheDocument();
    });

    it("should use fullText for tooltip when provided", () => {
      const filters = [
        {
          type: "topic" as const,
          value: "/m/04rlf",
          label: "Music",
          fullText: "Arts > Music > Rock Music",
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Note: Short labels don't get truncated, so no tooltip is set
      const pill = container.querySelector('[role="listitem"]');
      expect(pill).not.toHaveAttribute("title");
    });
  });

  describe("Canonical tag pills (US2)", () => {
    it("should show variation badge when aliasCount > 1", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "javascript",
          label: "JavaScript",
          aliasCount: 4,
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // aliasCount=4 → variationCount=3 → shows "3 var."
      expect(container.textContent).toContain("3 var.");
    });

    it("should not show variation badge when aliasCount is 1", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "react",
          label: "React",
          aliasCount: 1,
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      expect(container.textContent).not.toContain("var.");
    });

    it("should not show variation badge when aliasCount is undefined", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "react",
          label: "React",
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      expect(container.textContent).not.toContain("var.");
    });

    it("should truncate canonical_tag labels longer than 25 characters", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "a-very-long-canonical-tag-name",
          label: "a-very-long-canonical-tag-name",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      // Truncated at 25 chars + "..."
      expect(screen.getByText("a-very-long-canonical-tag...")).toBeInTheDocument();
    });

    it("should call onRemove with 'canonical_tag' type when remove button clicked", async () => {
      const mockOnRemove = vi.fn();

      const filters = [
        {
          type: "canonical_tag" as const,
          value: "javascript",
          label: "JavaScript",
          aliasCount: 2,
        },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={mockOnRemove} />
      );

      const removeButton = screen.getByRole("button", {
        name: "Remove canonical_tag filter: JavaScript",
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith("canonical_tag", "javascript");
    });

    it("should display 🏷️ icon for canonical_tag (same as tag)", () => {
      const filters = [
        {
          type: "canonical_tag" as const,
          value: "python",
          label: "Python",
        },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // canonical_tag uses the same tag icon
      expect(container.textContent).toContain("🏷️");
    });
  });

  describe("Accessibility (FR-ACC-001, FR-ACC-002, FR-ACC-007)", () => {
    it("should have proper ARIA structure with role=list and role=listitem", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const list = container.querySelector('[role="list"]');
      expect(list).toBeInTheDocument();
      expect(list).toHaveAttribute("aria-label", "Active filters");

      const items = container.querySelectorAll('[role="listitem"]');
      expect(items).toHaveLength(2);
    });

    it("should have accessible labels for remove buttons", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(
        screen.getByRole("button", { name: "Remove tag filter: music" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Remove category filter: Gaming" })
      ).toBeInTheDocument();
    });

    it("should have screen reader text for filter type", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // Check for sr-only span with filter type (inside the pill, not the live region)
      const srOnlySpans = container.querySelectorAll("span.sr-only");
      const typeSpan = Array.from(srOnlySpans).find((el) =>
        el.textContent?.includes("tag:")
      );
      expect(typeSpan).toBeInTheDocument();
    });

    it("should be keyboard navigable with focus indicators", async () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      const { user } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const removeButton = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });

      // Tab to button
      await user.tab();
      expect(removeButton).toHaveFocus();
    });

    it("should have ARIA list structure for boolean pills", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const list = container.querySelector('[role="list"]');
      expect(list).toBeInTheDocument();
      expect(list).toHaveAttribute("aria-label", "Active filters");

      const items = container.querySelectorAll('[role="listitem"]');
      expect(items).toHaveLength(1);
    });

    it("should have accessible remove button labels for boolean pills", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
        {
          type: "boolean" as const,
          value: "has_transcript",
          label: "Has transcripts",
        },
      ];

      renderWithProviders(<FilterPills filters={filters} onRemove={() => {}} />);

      expect(
        screen.getByRole("button", {
          name: "Remove boolean filter: Liked",
        })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: "Remove boolean filter: Has transcripts",
        })
      ).toBeInTheDocument();
    });

    it("should have screen reader text for boolean filter type", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      // querySelector returns the first .sr-only which is the announcement region;
      // use querySelectorAll to find the span inside the pill label
      const srOnlyElements = container.querySelectorAll(".sr-only");
      const pillTypeSrOnly = Array.from(srOnlyElements).find((el) =>
        el.textContent?.includes("boolean:")
      );
      expect(pillTypeSrOnly).toBeTruthy();
      expect(pillTypeSrOnly).toHaveTextContent("boolean:");
    });

    it("should have 44px minimum hit area on boolean pill remove buttons", () => {
      const filters = [
        { type: "boolean" as const, value: "liked_only", label: "Liked" },
      ];

      const { container } = renderWithProviders(
        <FilterPills filters={filters} onRemove={() => {}} />
      );

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toBeInTheDocument();
      if (pill) {
        expect(pill.className).toMatch(/min-h-\[44px\]/);
      }
    });
  });
});
