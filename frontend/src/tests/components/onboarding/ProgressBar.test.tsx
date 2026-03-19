/**
 * Tests for ProgressBar Component (T028)
 *
 * Covers:
 * - Progress percentage label rendering
 * - Fill bar width style
 * - Boundary states (0%, 100%)
 * - Value clamping (above 100, below 0)
 * - ARIA attributes (role, aria-valuenow, aria-valuemin, aria-valuemax)
 * - Custom className forwarding
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ProgressBar } from "../../../components/onboarding/ProgressBar";

describe("ProgressBar", () => {
  describe("percentage label", () => {
    it("renders a percentage label for a mid-range value", () => {
      render(<ProgressBar progress={45} />);

      // aria-hidden label is in the DOM; query by text content
      expect(screen.getByText("45%")).toBeInTheDocument();
    });

    it("renders '0%' when progress is 0", () => {
      render(<ProgressBar progress={0} />);

      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("renders '100%' when progress is 100", () => {
      render(<ProgressBar progress={100} />);

      expect(screen.getByText("100%")).toBeInTheDocument();
    });

    it("rounds fractional progress to nearest integer for label", () => {
      render(<ProgressBar progress={33.7} />);

      expect(screen.getByText("34%")).toBeInTheDocument();
    });
  });

  describe("fill bar width style", () => {
    it("sets width style equal to the progress percentage", () => {
      const { container } = render(<ProgressBar progress={60} />);

      // The inner fill div is the only element with an inline style
      const fill = container.querySelector<HTMLElement>('[style]');
      expect(fill).not.toBeNull();
      expect(fill!.style.width).toBe("60%");
    });

    it("sets width to '0%' for a 0% bar", () => {
      const { container } = render(<ProgressBar progress={0} />);

      const fill = container.querySelector<HTMLElement>('[style]');
      expect(fill!.style.width).toBe("0%");
    });

    it("sets width to '100%' for a full bar", () => {
      const { container } = render(<ProgressBar progress={100} />);

      const fill = container.querySelector<HTMLElement>('[style]');
      expect(fill!.style.width).toBe("100%");
    });
  });

  describe("value clamping", () => {
    it("clamps progress above 100 to 100", () => {
      render(<ProgressBar progress={150} />);

      // Label should show 100%
      expect(screen.getByText("100%")).toBeInTheDocument();
      // ARIA attribute should be 100
      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toHaveAttribute("aria-valuenow", "100");
    });

    it("clamps progress below 0 to 0", () => {
      render(<ProgressBar progress={-25} />);

      // Label should show 0%
      expect(screen.getByText("0%")).toBeInTheDocument();
      // ARIA attribute should be 0
      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toHaveAttribute("aria-valuenow", "0");
    });

    it("sets fill width to 100% when value exceeds 100", () => {
      const { container } = render(<ProgressBar progress={200} />);

      const fill = container.querySelector<HTMLElement>('[style]');
      expect(fill!.style.width).toBe("100%");
    });

    it("sets fill width to 0% when value is below 0", () => {
      const { container } = render(<ProgressBar progress={-10} />);

      const fill = container.querySelector<HTMLElement>('[style]');
      expect(fill!.style.width).toBe("0%");
    });
  });

  describe("ARIA attributes", () => {
    it("has role='progressbar' on the track element", () => {
      render(<ProgressBar progress={50} />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toBeInTheDocument();
    });

    it("sets aria-valuenow to the rounded clamped progress value", () => {
      render(<ProgressBar progress={45} />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toHaveAttribute("aria-valuenow", "45");
    });

    it("sets aria-valuemin to 0", () => {
      render(<ProgressBar progress={50} />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toHaveAttribute("aria-valuemin", "0");
    });

    it("sets aria-valuemax to 100", () => {
      render(<ProgressBar progress={50} />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toHaveAttribute("aria-valuemax", "100");
    });

    it("marks the percentage label as aria-hidden to avoid duplicate announcements", () => {
      render(<ProgressBar progress={75} />);

      const label = screen.getByText("75%");
      expect(label).toHaveAttribute("aria-hidden", "true");
    });
  });

  describe("custom className", () => {
    it("applies a custom className to the outer wrapper element", () => {
      const { container } = render(
        <ProgressBar progress={50} className="mt-4 custom-class" />
      );

      // The outermost div is the wrapper
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper).toHaveClass("mt-4");
      expect(wrapper).toHaveClass("custom-class");
    });

    it("preserves base layout classes when custom className is provided", () => {
      const { container } = render(
        <ProgressBar progress={50} className="my-2" />
      );

      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper).toHaveClass("flex");
      expect(wrapper).toHaveClass("items-center");
      expect(wrapper).toHaveClass("my-2");
    });

    it("renders without error when no className is provided", () => {
      expect(() => render(<ProgressBar progress={50} />)).not.toThrow();
    });
  });
});
