/**
 * Tests for SearchErrorState Component
 *
 * FR-003: Auth errors (401/403) are now handled globally by the QueryCache
 * interceptor — SearchErrorState only renders generic non-auth errors.
 *
 * Tests:
 * - Generic error display with retry button
 * - Accessible ARIA attributes
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

  describe("Accessibility", () => {
    it("should have proper ARIA role on error container", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState onRetry={onRetry} />);

      const errorContainer = screen.getByRole("alert");
      expect(errorContainer).toBeInTheDocument();
    });

    it("should have accessible button label for retry", () => {
      const onRetry = vi.fn();
      render(<SearchErrorState onRetry={onRetry} />);

      const button = screen.getByRole("button", { name: /retry search/i });
      expect(button).toBeInTheDocument();
    });
  });
});
