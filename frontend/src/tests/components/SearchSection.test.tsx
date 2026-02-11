/**
 * Tests for SearchSection Component
 *
 * Tests from T018 specification:
 * - Header format variations
 * - Hidden when empty
 * - Loading state
 * - Error state (with and without retry)
 * - Children rendering conditions
 * - Accessibility attributes
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SearchSection } from "../../components/SearchSection";

describe("SearchSection", () => {
  describe("Header format", () => {
    it("should show count format when totalCount equals displayedCount", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={3}
          displayedCount={3}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
        "Video Titles (3)"
      );
    });

    it("should show 'Showing X of Y' format when totalCount exceeds displayedCount", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={75}
          displayedCount={50}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
        "Video Titles - Showing 50 of 75"
      );
    });
  });

  describe("Hidden when empty", () => {
    it("should return null when totalCount is 0, not loading, and no error", () => {
      const { container } = render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(container.firstChild).toBeNull();
    });

    it("should render when totalCount is 0 but loading", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={true}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
    });

    it("should render when totalCount is 0 but error exists", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Failed")}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
    });
  });

  describe("Loading state", () => {
    it("should show spinner with loadingText when loading", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
          loadingText="Searching titles..."
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("status")).toHaveTextContent("Searching titles...");
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    it("should show title only (no count) in header during loading", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      const heading = screen.getByRole("heading", { level: 2 });
      expect(heading).toHaveTextContent("Video Titles");
      expect(heading).not.toHaveTextContent("10");
    });

    it("should use default loadingText when not provided", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("status")).toHaveTextContent("Searching...");
    });

    it("should not render children while loading", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
        >
          <div data-testid="children">Results</div>
        </SearchSection>
      );

      expect(screen.queryByTestId("children")).not.toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("should show error message with retry button when error and onRetry provided", () => {
      const onRetry = vi.fn();

      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Network error")}
          onRetry={onRetry}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to load video titles results."
      );
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    it("should call onRetry when retry button is clicked", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();

      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Network error")}
          onRetry={onRetry}
        >
          <div>Results</div>
        </SearchSection>
      );

      const retryButton = screen.getByRole("button", { name: /retry/i });
      await user.click(retryButton);

      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("should show error message without retry button when onRetry not provided", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Network error")}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to load video titles results."
      );
      expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    });

    it("should not render children when error present", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={false}
          error={new Error("Network error")}
        >
          <div data-testid="children">Results</div>
        </SearchSection>
      );

      expect(screen.queryByTestId("children")).not.toBeInTheDocument();
    });

    it("should not show error when loading even if error exists", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={true}
          error={new Error("Network error")}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("Children rendering", () => {
    it("should render children when not loading and no error", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={3}
          displayedCount={3}
          isLoading={false}
          error={null}
        >
          <div data-testid="children">Results content</div>
        </SearchSection>
      );

      expect(screen.getByTestId("children")).toBeInTheDocument();
      expect(screen.getByTestId("children")).toHaveTextContent("Results content");
    });

    it("should handle multiple children elements", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={3}
          displayedCount={3}
          isLoading={false}
          error={null}
        >
          <div data-testid="child1">Result 1</div>
          <div data-testid="child2">Result 2</div>
          <div data-testid="child3">Result 3</div>
        </SearchSection>
      );

      expect(screen.getByTestId("child1")).toBeInTheDocument();
      expect(screen.getByTestId("child2")).toBeInTheDocument();
      expect(screen.getByTestId("child3")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have section with aria-label matching title", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={3}
          displayedCount={3}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      const section = screen.getByLabelText("Video Titles");
      expect(section.tagName).toBe("SECTION");
    });

    it("should have loading state with role='status' and aria-live='polite'", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      const loadingDiv = screen.getByRole("status");
      expect(loadingDiv).toHaveAttribute("aria-live", "polite");
    });

    it("should have error state with role='alert' and aria-live='assertive'", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Network error")}
        >
          <div>Results</div>
        </SearchSection>
      );

      const alertDiv = screen.getByRole("alert");
      expect(alertDiv).toHaveAttribute("aria-live", "assertive");
    });

    it("should use h2 for section heading", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={3}
          displayedCount={3}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      const heading = screen.getByRole("heading", { level: 2 });
      expect(heading.tagName).toBe("H2");
    });
  });

  describe("Edge cases", () => {
    it("should handle displayedCount of 0 correctly", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={100}
          displayedCount={0}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
        "Video Titles - Showing 0 of 100"
      );
    });

    it("should handle very large counts", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={999999}
          displayedCount={50}
          isLoading={false}
          error={null}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
        "Video Titles - Showing 50 of 999999"
      );
    });

    it("should handle empty string as loadingText", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={10}
          displayedCount={10}
          isLoading={true}
          error={null}
          loadingText=""
        >
          <div>Results</div>
        </SearchSection>
      );

      const loadingDiv = screen.getByRole("status");
      // Should still render the spinner, just with empty text
      expect(loadingDiv).toBeInTheDocument();
    });

    it("should lowercase title in error message", () => {
      render(
        <SearchSection
          title="Video Titles"
          totalCount={0}
          displayedCount={0}
          isLoading={false}
          error={new Error("Network error")}
        >
          <div>Results</div>
        </SearchSection>
      );

      expect(screen.getByRole("alert")).toHaveTextContent(
        "Failed to load video titles results."
      );
    });
  });
});
