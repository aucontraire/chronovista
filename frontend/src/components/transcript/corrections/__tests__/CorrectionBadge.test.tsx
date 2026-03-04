/**
 * Tests for CorrectionBadge component (Feature 035, T016).
 *
 * Test coverage:
 * - Renders "Corrected" text when hasCorrection is true
 * - Renders nothing when hasCorrection is false
 * - Has aria-label="Corrected segment" for screen reader support
 * - Shows tooltip with count when correctionCount > 1
 * - No tooltip when correctionCount === 1
 * - Tooltip includes formatted correctedAt timestamp when count > 1
 * - Badge has correct visual styling classes
 *
 * NFR-008: Behavior tested via ARIA attributes and text content, not CSS class names.
 * Exception: visual styling test explicitly validates styling classes.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CorrectionBadge } from "../CorrectionBadge";

describe("CorrectionBadge", () => {
  describe("Rendering when hasCorrection is false", () => {
    it("renders nothing when hasCorrection is false", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={false}
          correctionCount={0}
          correctedAt={null}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it("renders nothing when hasCorrection is false even with correction data", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={false}
          correctionCount={3}
          correctedAt="2025-01-15T15:42:00Z"
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });

  describe("Rendering when hasCorrection is true", () => {
    it('renders "Corrected" text when hasCorrection is true', () => {
      render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt={null}
        />
      );

      expect(screen.getByText("Corrected")).toBeInTheDocument();
    });

    it('has aria-label="Corrected segment" for screen reader accessibility', () => {
      render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt={null}
        />
      );

      expect(
        screen.getByRole("generic", { name: "Corrected segment" })
      ).toBeInTheDocument();
    });

    it("renders the badge as an inline element with correct visual styling classes", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt={null}
        />
      );

      const badge = container.firstChild as HTMLElement;
      expect(badge).toHaveClass("bg-amber-100");
      expect(badge).toHaveClass("text-amber-800");
      expect(badge).toHaveClass("border-amber-200");
      expect(badge).toHaveClass("text-xs");
      expect(badge).toHaveClass("font-medium");
      expect(badge).toHaveClass("rounded");
    });
  });

  describe("Tooltip behavior", () => {
    it("does not show a tooltip when correctionCount is 1", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt="2025-01-15T15:42:00Z"
        />
      );

      const badge = container.firstChild as HTMLElement;
      expect(badge).not.toHaveAttribute("title");
    });

    it("shows tooltip with count when correctionCount > 1", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={3}
          correctedAt={null}
        />
      );

      const badge = container.firstChild as HTMLElement;
      expect(badge).toHaveAttribute("title");
      expect(badge.getAttribute("title")).toContain("Corrected 3 times");
    });

    it("tooltip includes formatted correctedAt timestamp when correctionCount > 1", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={3}
          correctedAt="2025-01-15T15:42:00Z"
        />
      );

      const badge = container.firstChild as HTMLElement;
      const title = badge.getAttribute("title") ?? "";
      expect(title).toContain("Corrected 3 times");
      // The date portion should appear in the tooltip (formatted date will vary by locale)
      expect(title).toContain("Last corrected:");
    });

    it("shows count tooltip without timestamp section when correctedAt is null and count > 1", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={5}
          correctedAt={null}
        />
      );

      const badge = container.firstChild as HTMLElement;
      const title = badge.getAttribute("title") ?? "";
      expect(title).toContain("Corrected 5 times");
      expect(title).not.toContain("Last corrected:");
    });

    it("tooltip contains the correction count in natural language", () => {
      const { container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={2}
          correctedAt="2025-06-01T09:00:00Z"
        />
      );

      const badge = container.firstChild as HTMLElement;
      const title = badge.getAttribute("title") ?? "";
      expect(title).toContain("Corrected 2 times");
    });
  });

  describe("Accessibility", () => {
    it("aria-label is always present when hasCorrection is true regardless of count", () => {
      const { rerender, container } = render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt={null}
        />
      );

      expect((container.firstChild as HTMLElement).getAttribute("aria-label")).toBe(
        "Corrected segment"
      );

      rerender(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={10}
          correctedAt="2025-01-01T00:00:00Z"
        />
      );

      expect((container.firstChild as HTMLElement).getAttribute("aria-label")).toBe(
        "Corrected segment"
      );
    });

    it("text label 'Corrected' is always visible (not hidden) — WCAG 1.4.1", () => {
      render(
        <CorrectionBadge
          hasCorrection={true}
          correctionCount={1}
          correctedAt={null}
        />
      );

      const text = screen.getByText("Corrected");
      // Text must be in the document and visible, not sr-only or hidden
      expect(text).toBeVisible();
    });
  });
});
