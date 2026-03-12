/**
 * Tests for AuthErrorState Component
 *
 * Covers:
 * - FR-002: Consistent "Session Expired" UI
 * - FR-022: Focus moves to "Refresh Page" button on mount
 * - NFR-001: 44×44 px minimum touch target on the button
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AuthErrorState } from "../../components/AuthErrorState";

describe("AuthErrorState", () => {
  beforeEach(() => {
    // Reset any window.location mock before each test
    vi.restoreAllMocks();
  });

  describe("Content rendering", () => {
    it("should render a lock icon (aria-hidden SVG)", () => {
      render(<AuthErrorState />);

      // The icon SVG has aria-hidden so it won't be in the accessibility tree,
      // but we can verify the container rendered by checking the parent div class.
      // Use the role="alert" container as an anchor.
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();

      // The SVG element itself should carry aria-hidden="true"
      const svgs = alert.querySelectorAll('svg[aria-hidden="true"]');
      expect(svgs.length).toBeGreaterThanOrEqual(1);
    });

    it("should display 'Your authentication token has expired' heading", () => {
      render(<AuthErrorState />);

      expect(
        screen.getByText("Your authentication token has expired")
      ).toBeInTheDocument();
    });

    it("should display a 'Refresh Page' button", () => {
      render(<AuthErrorState />);

      const button = screen.getByRole("button", { name: /refresh page/i });
      expect(button).toBeInTheDocument();
    });

    it("should display 'chronovista auth login' as inline code help text", () => {
      render(<AuthErrorState />);

      const codeEl = screen.getByText("chronovista auth login");
      expect(codeEl.tagName.toLowerCase()).toBe("code");
    });

    it("should show 'Session Expired' label text", () => {
      render(<AuthErrorState />);

      expect(screen.getByText("Session Expired")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have role='alert' with aria-live='assertive'", () => {
      render(<AuthErrorState />);

      const alert = screen.getByRole("alert");
      expect(alert).toHaveAttribute("aria-live", "assertive");
    });

    it("should have aria-atomic='true' on the alert container", () => {
      render(<AuthErrorState />);

      const alert = screen.getByRole("alert");
      expect(alert).toHaveAttribute("aria-atomic", "true");
    });

    it("button should have an accessible label referencing re-authentication", () => {
      render(<AuthErrorState />);

      const button = screen.getByRole("button", {
        name: /refresh page to re-authenticate/i,
      });
      expect(button).toBeInTheDocument();
    });

    it("button should meet NFR-001 min-height of 44px via Tailwind class", () => {
      render(<AuthErrorState />);

      const button = screen.getByRole("button", { name: /refresh page/i });
      // Verify the min-h-[44px] class is present
      expect(button.className).toContain("min-h-[44px]");
    });
  });

  describe("FR-022: Focus management on mount", () => {
    it("should move focus to the Refresh Page button on mount", () => {
      render(<AuthErrorState />);

      const button = screen.getByRole("button", { name: /refresh page/i });
      expect(document.activeElement).toBe(button);
    });
  });

  describe("Interaction", () => {
    it("should call window.location.reload() when Refresh Page is clicked", async () => {
      const user = userEvent.setup();
      const reloadSpy = vi.fn();

      Object.defineProperty(window, "location", {
        value: { reload: reloadSpy },
        writable: true,
      });

      render(<AuthErrorState />);

      const button = screen.getByRole("button", { name: /refresh page/i });
      await user.click(button);

      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });

    it("should call window.location.reload() when button is activated via keyboard", async () => {
      const user = userEvent.setup();
      const reloadSpy = vi.fn();

      Object.defineProperty(window, "location", {
        value: { reload: reloadSpy },
        writable: true,
      });

      render(<AuthErrorState />);

      // Button is auto-focused on mount; press Enter to activate
      await user.keyboard("{Enter}");

      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });
  });
});
