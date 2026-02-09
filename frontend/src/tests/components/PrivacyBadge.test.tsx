/**
 * Tests for PrivacyBadge Component
 *
 * Tests CHK060 and CHK061 requirements:
 * - CHK060: Accessible ARIA labels for privacy states
 * - CHK061: WCAG AA color contrast compliance
 * - Visual rendering of all three privacy states
 * - Icon presence verification
 * - Custom className support
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PrivacyBadge } from "../../components/PrivacyBadge";

describe("PrivacyBadge", () => {
  describe("Public privacy state", () => {
    it("should render public badge with correct text", () => {
      render(<PrivacyBadge status="public" />);

      expect(screen.getByText("Public")).toBeInTheDocument();
    });

    it("should have accessible aria-label for public status (CHK060)", () => {
      render(<PrivacyBadge status="public" />);

      const badge = screen.getByLabelText("Public playlist");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveAttribute("role", "img");
    });

    it("should have green color styling for public status (CHK061)", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("bg-green-100");
      expect(badge).toHaveClass("text-green-800");
    });

    it("should render globe icon for public status", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      // Check for SVG icon presence
      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });
  });

  describe("Private privacy state", () => {
    it("should render private badge with correct text", () => {
      render(<PrivacyBadge status="private" />);

      expect(screen.getByText("Private")).toBeInTheDocument();
    });

    it("should have accessible aria-label for private status (CHK060)", () => {
      render(<PrivacyBadge status="private" />);

      const badge = screen.getByLabelText("Private playlist");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveAttribute("role", "img");
    });

    it("should have red color styling for private status (CHK061)", () => {
      const { container } = render(<PrivacyBadge status="private" />);

      const badge = container.querySelector('[aria-label="Private playlist"]');
      expect(badge).toHaveClass("bg-red-100");
      expect(badge).toHaveClass("text-red-800");
    });

    it("should render lock icon for private status", () => {
      const { container } = render(<PrivacyBadge status="private" />);

      // Check for SVG icon presence
      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });
  });

  describe("Unlisted privacy state", () => {
    it("should render unlisted badge with correct text", () => {
      render(<PrivacyBadge status="unlisted" />);

      expect(screen.getByText("Unlisted")).toBeInTheDocument();
    });

    it("should have accessible aria-label for unlisted status (CHK060)", () => {
      render(<PrivacyBadge status="unlisted" />);

      const badge = screen.getByLabelText("Unlisted playlist");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveAttribute("role", "img");
    });

    it("should have amber color styling for unlisted status (CHK061)", () => {
      const { container } = render(<PrivacyBadge status="unlisted" />);

      const badge = container.querySelector('[aria-label="Unlisted playlist"]');
      expect(badge).toHaveClass("bg-amber-100");
      expect(badge).toHaveClass("text-amber-800");
    });

    it("should render link icon for unlisted status", () => {
      const { container } = render(<PrivacyBadge status="unlisted" />);

      // Check for SVG icon presence
      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });
  });

  describe("Badge styling", () => {
    it("should have pill shape with rounded corners", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("rounded-full");
    });

    it("should have small text size", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("text-xs");
    });

    it("should have correct padding", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("px-2");
      expect(badge).toHaveClass("py-0.5");
    });

    it("should display icon and text inline with gap", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("inline-flex");
      expect(badge).toHaveClass("items-center");
      expect(badge).toHaveClass("gap-1");
    });
  });

  describe("Custom className support", () => {
    it("should apply custom className when provided", () => {
      const { container } = render(
        <PrivacyBadge status="public" className="ml-2 custom-class" />
      );

      const badge = container.querySelector('[aria-label="Public playlist"]');
      expect(badge).toHaveClass("ml-2");
      expect(badge).toHaveClass("custom-class");
    });

    it("should preserve base styles when custom className is applied", () => {
      const { container } = render(
        <PrivacyBadge status="private" className="mt-4" />
      );

      const badge = container.querySelector('[aria-label="Private playlist"]');
      expect(badge).toHaveClass("mt-4");
      expect(badge).toHaveClass("bg-red-100");
      expect(badge).toHaveClass("text-red-800");
      expect(badge).toHaveClass("rounded-full");
    });
  });

  describe("Icon accessibility", () => {
    it("should hide icons from screen readers with aria-hidden", () => {
      const { container } = render(<PrivacyBadge status="public" />);

      const svg = container.querySelector("svg");
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should have consistent icon size across all states", () => {
      const publicRender = render(<PrivacyBadge status="public" />);
      const publicSvg = publicRender.container.querySelector("svg");
      expect(publicSvg).toHaveClass("w-3");
      expect(publicSvg).toHaveClass("h-3");

      const privateRender = render(<PrivacyBadge status="private" />);
      const privateSvg = privateRender.container.querySelector("svg");
      expect(privateSvg).toHaveClass("w-3");
      expect(privateSvg).toHaveClass("h-3");

      const unlistedRender = render(<PrivacyBadge status="unlisted" />);
      const unlistedSvg = unlistedRender.container.querySelector("svg");
      expect(unlistedSvg).toHaveClass("w-3");
      expect(unlistedSvg).toHaveClass("h-3");
    });
  });
});
