/**
 * Tests for UnavailabilityBanner Component
 *
 * Tests Feature 023 (Deleted Content Visibility) requirements:
 * - FR-012: Video unavailability banners with status-specific messaging
 * - FR-013: Channel unavailability banners with status-specific messaging
 * - FR-014: Alternative URL display when available
 * - FR-022: WCAG 2.1 Level AA accessibility (role="status", aria-live="polite", no color-only indication)
 *
 * Test Coverage:
 * - 6 video status types with correct headings and details
 * - 6 channel status types with correct headings and details
 * - Accessibility attributes (role, aria-live, icons)
 * - Alternative URL rendering for videos
 * - Edge cases (available status returns null, unknown status fallback)
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { UnavailabilityBanner } from "../UnavailabilityBanner";

describe("UnavailabilityBanner", () => {
  describe("Video Status - Headings", () => {
    it("should render correct heading for private video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video is private.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for deleted video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video was deleted.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for terminated video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video is from a terminated channel.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for copyright video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="copyright"
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video was removed for copyright violation.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for tos_violation video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="tos_violation"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          "This video was removed for violating YouTube's Terms of Service."
        )
      ).toBeInTheDocument();
    });

    it("should render correct heading for unavailable video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unavailable"
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video is currently unavailable.")
      ).toBeInTheDocument();
    });
  });

  describe("Channel Status - Headings", () => {
    it("should render correct heading for private channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="channel"
        />
      );

      expect(
        screen.getByText("This channel is private.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for deleted channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="channel"
        />
      );

      expect(
        screen.getByText("This channel was deleted.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for terminated channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="channel"
        />
      );

      expect(
        screen.getByText("This channel has been terminated.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for copyright channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="copyright"
          entityType="channel"
        />
      );

      expect(
        screen.getByText("This channel was removed for copyright violations.")
      ).toBeInTheDocument();
    });

    it("should render correct heading for tos_violation channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="tos_violation"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          "This channel was removed for violating YouTube's Terms of Service."
        )
      ).toBeInTheDocument();
    });

    it("should render correct heading for unavailable channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unavailable"
          entityType="channel"
        />
      );

      expect(
        screen.getByText("This channel is currently unavailable.")
      ).toBeInTheDocument();
    });
  });

  describe("Video Status - Detail Text", () => {
    it("should render detail text for private video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /The uploader has made this video private.*metadata shown below was captured before the change/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for deleted video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /This video was removed from YouTube.*metadata shown below was captured before deletion/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for terminated video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /The channel that published this video has been terminated.*metadata shown below was captured before termination/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for copyright video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="copyright"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /YouTube removed this video due to a copyright claim.*metadata shown below was captured before removal/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for tos_violation video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="tos_violation"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /YouTube removed this video for a Terms of Service violation.*metadata shown below was captured before removal/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for unavailable video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unavailable"
          entityType="video"
        />
      );

      expect(
        screen.getByText(
          /This video cannot be accessed on YouTube.*The reason is unknown.*metadata shown below was captured while the video was still available/i
        )
      ).toBeInTheDocument();
    });
  });

  describe("Channel Status - Detail Text", () => {
    it("should render detail text for private channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /This channel has been made private.*metadata shown below was captured before the change/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for deleted channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /This channel was removed from YouTube.*metadata shown below was captured before deletion/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for terminated channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /YouTube has terminated this channel.*metadata shown below was captured before termination/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for copyright channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="copyright"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /YouTube removed this channel due to copyright claims.*metadata shown below was captured before removal/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for tos_violation channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="tos_violation"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /YouTube removed this channel for Terms of Service violations.*metadata shown below was captured before removal/i
        )
      ).toBeInTheDocument();
    });

    it("should render detail text for unavailable channel", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unavailable"
          entityType="channel"
        />
      );

      expect(
        screen.getByText(
          /This channel cannot be accessed on YouTube.*The reason is unknown.*metadata shown below was captured while the channel was still accessible/i
        )
      ).toBeInTheDocument();
    });
  });

  describe("Accessibility - ARIA Attributes (FR-022)", () => {
    it("should have role='status' attribute", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"]');
      expect(banner).toBeInTheDocument();
    });

    it("should have aria-live='polite' attribute", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="channel"
        />
      );

      const banner = container.querySelector('[aria-live="polite"]');
      expect(banner).toBeInTheDocument();
    });

    it("should have both role and aria-live on the same element", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"][aria-live="polite"]');
      expect(banner).toBeInTheDocument();
    });
  });

  describe("Accessibility - Icons (WCAG 1.4.1 - No Color-Only)", () => {
    it("should render icon for private status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="private"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon for deleted status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon for terminated status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="terminated"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon for copyright status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="copyright"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon for tos_violation status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="tos_violation"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon for unavailable status", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="unavailable"
          entityType="video"
        />
      );

      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should render icon in circular background container", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const iconContainer = container.querySelector(".rounded-full");
      expect(iconContainer).toBeInTheDocument();
      expect(iconContainer?.querySelector("svg")).toBeInTheDocument();
    });
  });

  describe("Alternative URL - Video Entity (FR-014)", () => {
    it("should render alternative URL link when provided for video", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/alternative-video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute(
        "href",
        "https://example.com/alternative-video"
      );
    });

    it("should open alternative URL in new tab (target='_blank')", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });
      expect(link).toHaveAttribute("target", "_blank");
    });

    it("should have rel='noopener noreferrer' on alternative URL link", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("should include screen reader text for new tab behavior", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      expect(screen.getByText("(opens in new tab)")).toBeInTheDocument();
      expect(screen.getByText("(opens in new tab)")).toHaveClass("sr-only");
    });

    it("should render external link icon", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });
      const svg = link.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    it("should not render alternative URL section when alternativeUrl is null", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl={null}
        />
      );

      expect(
        screen.queryByRole("link", { name: /alternative platform/i })
      ).not.toBeInTheDocument();
    });

    it("should not render alternative URL section when alternativeUrl is undefined", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      expect(
        screen.queryByRole("link", { name: /alternative platform/i })
      ).not.toBeInTheDocument();
    });

    it("should not render alternative URL for channel entity type", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="channel"
          alternativeUrl="https://example.com/channel"
        />
      );

      expect(
        screen.queryByRole("link", { name: /alternative platform/i })
      ).not.toBeInTheDocument();
    });

    it("should render alternative URL for all video statuses when provided", () => {
      const statuses = [
        "private",
        "deleted",
        "terminated",
        "copyright",
        "tos_violation",
        "unavailable",
      ];

      statuses.forEach((status) => {
        const { unmount } = render(
          <UnavailabilityBanner
            availabilityStatus={status}
            entityType="video"
            alternativeUrl="https://example.com/video"
          />
        );

        const link = screen.getByRole("link", {
          name: /alternative platform/i,
        });
        expect(link).toBeInTheDocument();

        unmount();
      });
    });
  });

  describe("Edge Cases", () => {
    it("should return null when availabilityStatus is 'available'", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="available"
          entityType="video"
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it("should handle unknown video status gracefully with fallback to unavailable", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unknown-status"
          entityType="video"
        />
      );

      // Should fall back to "unavailable" banner
      expect(
        screen.getByText("This video is currently unavailable.")
      ).toBeInTheDocument();
    });

    it("should handle unknown channel status gracefully with fallback to unavailable", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="unknown-status"
          entityType="channel"
        />
      );

      // Should fall back to "unavailable" banner
      expect(
        screen.getByText("This channel is currently unavailable.")
      ).toBeInTheDocument();
    });

    it("should render correctly when status is empty string (fallback to unavailable)", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus=""
          entityType="video"
        />
      );

      expect(
        screen.getByText("This video is currently unavailable.")
      ).toBeInTheDocument();
    });
  });

  describe("Visual Styling", () => {
    it("should have rounded corners on banner", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"]');
      expect(banner).toHaveClass("rounded-xl");
    });

    it("should have shadow styling", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"]');
      expect(banner).toHaveClass("shadow-md");
    });

    it("should have appropriate padding", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"]');
      expect(banner).toHaveClass("p-6");
    });

    it("should have bottom margin", () => {
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
        />
      );

      const banner = container.querySelector('[role="status"]');
      expect(banner).toHaveClass("mb-6");
    });

    it("should apply different background colors for different statuses", () => {
      const testCases = [
        { status: "private", bgClass: "bg-amber-50" },
        { status: "deleted", bgClass: "bg-red-50" },
        { status: "terminated", bgClass: "bg-red-50" },
        { status: "copyright", bgClass: "bg-orange-50" },
        { status: "tos_violation", bgClass: "bg-orange-50" },
        { status: "unavailable", bgClass: "bg-slate-50" },
      ];

      testCases.forEach(({ status, bgClass }) => {
        const { container, unmount } = render(
          <UnavailabilityBanner
            availabilityStatus={status}
            entityType="video"
          />
        );

        const banner = container.querySelector('[role="status"]');
        expect(banner).toHaveClass(bgClass);

        unmount();
      });
    });
  });

  describe("Focus Indicators (NFR-003)", () => {
    it("should have visible focus indicators on alternative URL link", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });

      // Check for focus ring classes
      expect(link).toHaveClass("focus:outline-none");
      expect(link).toHaveClass("focus:ring-2");
      expect(link).toHaveClass("focus:ring-offset-2");
    });

    it("should have rounded focus indicator on alternative URL link", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });

      expect(link).toHaveClass("rounded");
    });

    it("should have hover state on alternative URL link", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          alternativeUrl="https://example.com/video"
        />
      );

      const link = screen.getByRole("link", {
        name: /alternative platform/i,
      });

      expect(link).toHaveClass("hover:underline");
    });
  });
});
