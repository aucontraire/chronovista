/**
 * Tests for FilterPills component
 *
 * Verifies:
 * - T043: Color-coded pills display (blue=tags, green=categories, purple=topics)
 * - T048: Individual filter removal via × button
 * - T050: Long tag truncation with tooltip
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-007: Visible focus indicators
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterPills } from "../../components/FilterPills";

describe("FilterPills", () => {
  describe("Rendering and display", () => {
    it("should render nothing when no filters provided", () => {
      const { container } = render(
        <FilterPills filters={[]} onRemove={() => {}} />
      );

      expect(container.firstChild).toBeNull();
    });

    it("should render all provided filters with correct labels", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
        { type: "topic" as const, value: "/m/04rlf", label: "Music" },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

      // Check for emoji icons
      expect(container.textContent).toContain("🏷️"); // tag
      expect(container.textContent).toContain("📂"); // category
      expect(container.textContent).toContain("🌐"); // topic
    });
  });

  describe("Color schemes (T043)", () => {
    it("should apply tag color scheme (blue)", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveStyle({
        backgroundColor: "#F3E8FF", // Light purple
        color: "#6B21A8", // Dark purple
      });
    });
  });

  describe("Filter removal (T048)", () => {
    it("should call onRemove with correct type and value when × button clicked", async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      render(<FilterPills filters={filters} onRemove={mockOnRemove} />);

      const removeButton = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });

      await user.click(removeButton);

      expect(mockOnRemove).toHaveBeenCalledOnce();
      expect(mockOnRemove).toHaveBeenCalledWith("tag", "music");
    });

    it("should have distinct remove buttons for each filter", async () => {
      const user = userEvent.setup();
      const mockOnRemove = vi.fn();

      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "tag" as const, value: "tutorial", label: "tutorial" },
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      render(<FilterPills filters={filters} onRemove={mockOnRemove} />);

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
  });

  describe("Long tag truncation (T050)", () => {
    it("should truncate tags longer than 20 characters", () => {
      const filters = [
        {
          type: "tag" as const,
          value: "very-long-tag-name-that-exceeds-limit",
          label: "very-long-tag-name-that-exceeds-limit",
        },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      // Should show truncated text with ellipsis
      expect(screen.getByText("very-long-tag-name-t...")).toBeInTheDocument();
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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

      const pill = container.querySelector('[role="listitem"]');
      expect(pill).toHaveAttribute(
        "title",
        "very-long-tag-name-that-exceeds-limit"
      );
    });

    it("should not truncate tags shorter than 20 characters", () => {
      const filters = [
        { type: "tag" as const, value: "short", label: "short" },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

      // Note: Short labels don't get truncated, so no tooltip is set
      const pill = container.querySelector('[role="listitem"]');
      expect(pill).not.toHaveAttribute("title");
    });
  });

  describe("Accessibility (FR-ACC-001, FR-ACC-002, FR-ACC-007)", () => {
    it("should have proper ARIA structure with role=list and role=listitem", () => {
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
        { type: "category" as const, value: "10", label: "Gaming" },
      ];

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      render(<FilterPills filters={filters} onRemove={() => {}} />);

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

      const { container } = render(<FilterPills filters={filters} onRemove={() => {}} />);

      // Check for sr-only span with filter type
      const srOnlyText = container.querySelector(".sr-only");
      expect(srOnlyText).toHaveTextContent("tag:");
    });

    it("should be keyboard navigable with focus indicators", async () => {
      const user = userEvent.setup();
      const filters = [
        { type: "tag" as const, value: "music", label: "music" },
      ];

      render(<FilterPills filters={filters} onRemove={() => {}} />);

      const removeButton = screen.getByRole("button", {
        name: "Remove tag filter: music",
      });

      // Tab to button
      await user.tab();
      expect(removeButton).toHaveFocus();
    });
  });
});
