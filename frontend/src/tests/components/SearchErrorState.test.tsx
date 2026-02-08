/**
 * Tests for SearchErrorState Component
 *
 * Tests edge case handling:
 * - T056: Authentication error detection (EC-011-EC-016)
 * - Generic error display with retry
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SearchErrorState } from "../../components/SearchErrorState";

describe("SearchErrorState", () => {
  describe("Generic error display", () => {
    it("should display default error message when no message provided", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState onRetry={onRetry} />);

      expect(screen.getByText("Error loading search results")).toBeInTheDocument();
      expect(screen.getByText("Something went wrong. Please try again.")).toBeInTheDocument();
    });

    it("should display custom error message when provided", () => {
      const onRetry = vi.fn();
      render(
        <SearchErrorState
          message="Network error: Unable to reach server"
          onRetry={onRetry}
        />
      );

      expect(screen.getByText("Network error: Unable to reach server")).toBeInTheDocument();
    });

    it("should call onRetry when Try Again button is clicked", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      render(<SearchErrorState onRetry={onRetry} />);

      const retryButton = screen.getByRole("button", { name: /retry search/i });
      await user.click(retryButton);

      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("should have accessible ARIA attributes", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState onRetry={onRetry} />);

      const errorContainer = screen.getByRole("alert");
      expect(errorContainer).toHaveAttribute("aria-live", "assertive");
    });
  });

  describe("T056: Authentication error handling (EC-011-EC-016)", () => {
    it("should display session expired message for 401 status", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={401} onRetry={onRetry} />);

      expect(screen.getByText("Session expired")).toBeInTheDocument();
      expect(screen.getByText("Session expired. Please refresh the page.")).toBeInTheDocument();
    });

    it("should display session expired message for 403 status", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={403} onRetry={onRetry} />);

      expect(screen.getByText("Session expired")).toBeInTheDocument();
      expect(screen.getByText("Session expired. Please refresh the page.")).toBeInTheDocument();
    });

    it("should extract status from ApiError object", () => {
      const onRetry = vi.fn();
      const error = { status: 401, message: "Unauthorized", type: "server" };
      render(<SearchErrorState error={error} onRetry={onRetry} />);

      expect(screen.getByText("Session expired")).toBeInTheDocument();
    });

    it("should show Refresh Page button for auth errors", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={401} onRetry={onRetry} />);

      const refreshButton = screen.getByRole("button", { name: /refresh page/i });
      expect(refreshButton).toBeInTheDocument();
    });

    it("should show terminal command help text for auth errors (EC-015)", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={401} onRetry={onRetry} />);

      expect(screen.getByText(/chronovista auth login/)).toBeInTheDocument();
      expect(screen.getByText(/Or run/)).toBeInTheDocument();
      expect(screen.getByText(/in your terminal/)).toBeInTheDocument();
    });

    it("should call window.location.reload when Refresh Page is clicked", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      const reloadSpy = vi.fn();

      // Mock window.location.reload
      Object.defineProperty(window, "location", {
        value: { reload: reloadSpy },
        writable: true,
      });

      render(<SearchErrorState status={401} onRetry={onRetry} />);

      const refreshButton = screen.getByRole("button", { name: /refresh page/i });
      await user.click(refreshButton);

      expect(reloadSpy).toHaveBeenCalledTimes(1);
      expect(onRetry).not.toHaveBeenCalled(); // Refresh should be called instead of retry
    });

    it("should not show auth error UI for non-auth status codes", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={500} onRetry={onRetry} />);

      expect(screen.queryByText("Session expired")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry search/i })).toBeInTheDocument();
    });

    it("should prioritize explicit status prop over error object status", () => {
      const onRetry = vi.fn();
      const error = { status: 500, message: "Server error", type: "server" };
      render(<SearchErrorState status={401} error={error} onRetry={onRetry} />);

      // Should show auth error UI because explicit status=401 takes precedence
      expect(screen.getByText("Session expired")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes for auth errors", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={401} onRetry={onRetry} />);

      const errorContainer = screen.getByRole("alert");
      expect(errorContainer).toHaveAttribute("aria-live", "assertive");
    });

    it("should have accessible button labels", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState status={401} onRetry={onRetry} />);

      const refreshButton = screen.getByRole("button", { name: /refresh page to re-authenticate/i });
      expect(refreshButton).toBeInTheDocument();
    });
  });
});
