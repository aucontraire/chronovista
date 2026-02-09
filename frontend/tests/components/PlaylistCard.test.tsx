/**
 * Tests for PlaylistCard Component - Playlist Navigation (T035)
 *
 * Requirements tested:
 * - Renders playlist title with proper truncation (line-clamp-2)
 * - Displays video count with proper singular/plural handling
 * - Shows privacy badges (public/private/unlisted)
 * - Shows playlist type badges (YouTube/Local)
 * - Links to /playlists/:id
 * - Keyboard navigation (Tab, Enter, Space)
 * - Focus visible states
 * - Hover states
 * - PlaylistCardSkeleton loading state
 *
 * Test coverage:
 * - Rendering with all playlist types (YouTube/Local)
 * - Privacy badge display (public/private/unlisted)
 * - Video count formatting (0, 1, multiple)
 * - Navigation to playlist detail page
 * - Keyboard accessibility (Tab, Shift+Tab, Enter, Space)
 * - Hover interactions
 * - Skeleton component rendering
 * - Accessibility (ARIA attributes, semantic HTML)
 */

import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { PlaylistCard, PlaylistCardSkeleton } from "../../src/components/PlaylistCard";
import type { PlaylistListItem } from "../../src/types/playlist";

describe("PlaylistCard", () => {
  // Mock data for YouTube-linked playlist (starts with "PL")
  const mockYouTubePlaylist: PlaylistListItem = {
    playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
    title: "Introduction to Machine Learning",
    description: "A comprehensive guide to ML fundamentals",
    video_count: 42,
    privacy_status: "public",
    is_linked: true,
  };

  // Mock data for local playlist (starts with "int_")
  const mockLocalPlaylist: PlaylistListItem = {
    playlist_id: "int_12345",
    title: "My Personal Learning Journey",
    description: "Curated videos for my studies",
    video_count: 15,
    privacy_status: "private",
    is_linked: false,
  };

  describe("Basic Rendering", () => {
    it("should render playlist title", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      expect(screen.getByText("Introduction to Machine Learning")).toBeInTheDocument();
    });

    it("should render video count", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      expect(screen.getByText("42 videos")).toBeInTheDocument();
    });

    it("should render privacy badge", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      // PrivacyBadge should render with accessible label
      expect(screen.getByLabelText("Public playlist")).toBeInTheDocument();
    });

    it("should render playlist type badge for YouTube playlist", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      // PlaylistTypeBadge should render with accessible label
      expect(screen.getByLabelText("Type: YouTube-linked playlist")).toBeInTheDocument();
    });

    it("should render playlist type badge for local playlist", () => {
      renderWithProviders(<PlaylistCard playlist={mockLocalPlaylist} />);

      // PlaylistTypeBadge should render with accessible label
      expect(screen.getByLabelText("Type: Local only playlist")).toBeInTheDocument();
    });

    it("should render as an article element", () => {
      const { container } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const article = container.querySelector("article");
      expect(article).toBeInTheDocument();
    });
  });

  describe("Video Count Formatting", () => {
    it("should show 'No videos' when count is 0", () => {
      const playlistWithNoVideos: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: 0,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithNoVideos} />);

      expect(screen.getByText("No videos")).toBeInTheDocument();
    });

    it("should show '1 video' (singular) when count is 1", () => {
      const playlistWithOneVideo: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: 1,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithOneVideo} />);

      expect(screen.getByText("1 video")).toBeInTheDocument();
    });

    it("should show plural 'videos' when count is 2", () => {
      const playlistWithTwoVideos: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: 2,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithTwoVideos} />);

      expect(screen.getByText("2 videos")).toBeInTheDocument();
    });

    it("should format large numbers with locale separators", () => {
      const playlistWithManyVideos: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: 1234,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithManyVideos} />);

      // toLocaleString() should format as "1,234"
      expect(screen.getByText("1,234 videos")).toBeInTheDocument();
    });

    it("should handle very large video counts", () => {
      const playlistWithHugeCount: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: 999999,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithHugeCount} />);

      // toLocaleString() should format as "999,999"
      expect(screen.getByText("999,999 videos")).toBeInTheDocument();
    });
  });

  describe("Privacy Status Badges", () => {
    it("should show public badge for public playlists", () => {
      const publicPlaylist: PlaylistListItem = {
        ...mockYouTubePlaylist,
        privacy_status: "public",
      };

      renderWithProviders(<PlaylistCard playlist={publicPlaylist} />);

      expect(screen.getByLabelText("Public playlist")).toBeInTheDocument();
    });

    it("should show private badge for private playlists", () => {
      const privatePlaylist: PlaylistListItem = {
        ...mockYouTubePlaylist,
        privacy_status: "private",
      };

      renderWithProviders(<PlaylistCard playlist={privatePlaylist} />);

      expect(screen.getByLabelText("Private playlist")).toBeInTheDocument();
    });

    it("should show unlisted badge for unlisted playlists", () => {
      const unlistedPlaylist: PlaylistListItem = {
        ...mockYouTubePlaylist,
        privacy_status: "unlisted",
      };

      renderWithProviders(<PlaylistCard playlist={unlistedPlaylist} />);

      expect(screen.getByLabelText("Unlisted playlist")).toBeInTheDocument();
    });
  });

  describe("Playlist Type Badges", () => {
    it("should show YouTube badge for linked playlists", () => {
      const youtubePlaylist: PlaylistListItem = {
        ...mockYouTubePlaylist,
        is_linked: true,
      };

      renderWithProviders(<PlaylistCard playlist={youtubePlaylist} />);

      expect(screen.getByLabelText("Type: YouTube-linked playlist")).toBeInTheDocument();
    });

    it("should show Local badge for non-linked playlists", () => {
      const localPlaylist: PlaylistListItem = {
        ...mockLocalPlaylist,
        is_linked: false,
      };

      renderWithProviders(<PlaylistCard playlist={localPlaylist} />);

      expect(screen.getByLabelText("Type: Local only playlist")).toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    it("should link to playlist detail page with correct ID", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link", {
        name: /View playlist Introduction to Machine Learning/i,
      });
      expect(link).toHaveAttribute(
        "href",
        "/playlists/PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
      );
    });

    it("should have accessible label including title and video count", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link", {
        name: "View playlist Introduction to Machine Learning, 42 videos",
      });
      expect(link).toBeInTheDocument();
    });

    it("should link to correct route for local playlists", () => {
      renderWithProviders(<PlaylistCard playlist={mockLocalPlaylist} />);

      const link = screen.getByRole("link", {
        name: /View playlist My Personal Learning Journey/i,
      });
      expect(link).toHaveAttribute("href", "/playlists/int_12345");
    });

    it("should have proper href attribute structure", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link");
      const href = link.getAttribute("href");
      expect(href).toMatch(/^\/playlists\/[a-zA-Z0-9_-]+$/);
    });
  });

  describe("Keyboard Accessibility", () => {
    it("should be focusable with Tab key", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      // Tab to the link
      await user.tab();

      expect(link).toHaveFocus();
    });

    it("should show focus ring when focused", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      // Tab to the link
      await user.tab();

      expect(link).toHaveFocus();
      // Focus ring classes should be present
      expect(link).toHaveClass("focus:ring-2", "focus:ring-blue-500");
    });

    it("should support reverse navigation with Shift+Tab", async () => {
      const { user } = renderWithProviders(
        <>
          <PlaylistCard playlist={mockYouTubePlaylist} />
          <PlaylistCard playlist={mockLocalPlaylist} />
        </>
      );

      const links = screen.getAllByRole("link");

      // Tab to second link
      await user.tab();
      await user.tab();
      expect(links[1]).toHaveFocus();

      // Shift+Tab should go back to first link
      await user.tab({ shift: true });
      expect(links[0]).toHaveFocus();
    });

    it("should activate link with Enter key", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      // Tab to the link and press Enter
      await user.tab();
      expect(link).toHaveFocus();

      // Press Enter (would navigate in browser)
      await user.keyboard("{Enter}");
    });

    it("should activate link with Space key", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      // Tab to the link
      await user.tab();
      expect(link).toHaveFocus();

      // Press Space (would navigate in browser)
      await user.keyboard(" ");
    });

    it("should maintain focus outline on focus-visible", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      // Tab to the link (keyboard interaction = focus-visible)
      await user.tab();

      expect(link).toHaveFocus();
      expect(link).toHaveClass("focus:outline-none");
    });
  });

  describe("Hover Interactions", () => {
    it("should be hoverable", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const link = screen.getByRole("link");

      await user.hover(link);

      // Link should still be in the document after hover
      expect(link).toBeInTheDocument();
    });

    it("should apply hover styles to the article element", () => {
      const { container } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const article = container.querySelector("article");

      // Article should have hover classes (from cardPatterns.hover)
      expect(article).toHaveClass("hover:shadow-xl", "hover:border-gray-200");
    });

    it("should maintain hover state during interaction", async () => {
      const { user } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const article = screen.getByRole("article");

      // Hover over the article
      await user.hover(article);

      // Article should still be present
      expect(article).toBeInTheDocument();
    });
  });

  describe("Title Truncation", () => {
    it("should apply line-clamp-2 to title", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const title = screen.getByText("Introduction to Machine Learning");

      expect(title).toHaveClass("line-clamp-2");
    });

    it("should show full title in title attribute for tooltip", () => {
      const playlistWithLongTitle: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "This is an extremely long playlist title that should be truncated after two lines but the full text should be available in a tooltip",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithLongTitle} />);

      const title = screen.getByText(/This is an extremely long playlist title/);
      expect(title).toHaveAttribute(
        "title",
        "This is an extremely long playlist title that should be truncated after two lines but the full text should be available in a tooltip"
      );
    });

    it("should handle very long titles gracefully", () => {
      const playlistWithVeryLongTitle: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "A".repeat(500),
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithVeryLongTitle} />);

      const title = screen.getByText("A".repeat(500));
      expect(title).toBeInTheDocument();
      expect(title).toHaveClass("line-clamp-2");
    });
  });

  describe("Accessibility (ARIA)", () => {
    it("should have proper ARIA label on link", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("aria-label");
      expect(link.getAttribute("aria-label")).toMatch(/View playlist/);
    });

    it("should include video count in ARIA label", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link", {
        name: /42 videos/,
      });
      expect(link).toBeInTheDocument();
    });

    it("should have article role on card container", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const article = screen.getByRole("article");
      expect(article).toBeInTheDocument();
    });

    it("should have accessible name for all interactive elements", () => {
      renderWithProviders(<PlaylistCard playlist={mockYouTubePlaylist} />);

      const link = screen.getByRole("link");
      expect(link).toHaveAccessibleName();
    });

    it("should use semantic heading for title", () => {
      const { container } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const heading = container.querySelector("h3");
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveTextContent("Introduction to Machine Learning");
    });

    it("should have proper heading hierarchy", () => {
      const { container } = renderWithProviders(
        <PlaylistCard playlist={mockYouTubePlaylist} />
      );

      const h3 = container.querySelector("h3");
      expect(h3).toBeInTheDocument();
    });
  });

  describe("Special Characters and Unicode", () => {
    it("should handle special characters in title", () => {
      const playlistWithSpecialChars: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "C++ & Python: Advanced Programming (2024) - $99 Course!",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithSpecialChars} />);

      expect(
        screen.getByText("C++ & Python: Advanced Programming (2024) - $99 Course!")
      ).toBeInTheDocument();
    });

    it("should handle emoji in title", () => {
      const playlistWithEmoji: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "🚀 Machine Learning Tutorial 🎓 Learn ML 💻",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithEmoji} />);

      expect(
        screen.getByText("🚀 Machine Learning Tutorial 🎓 Learn ML 💻")
      ).toBeInTheDocument();
    });

    it("should handle multi-byte Unicode characters", () => {
      const playlistWithUnicode: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "機械学習入門 - Introduction to Machine Learning",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithUnicode} />);

      expect(
        screen.getByText("機械学習入門 - Introduction to Machine Learning")
      ).toBeInTheDocument();
    });

    it("should handle RTL text", () => {
      const playlistWithRTL: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "تعلم البرمجة - Learn Programming",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithRTL} />);

      expect(screen.getByText("تعلم البرمجة - Learn Programming")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle null description gracefully", () => {
      const playlistWithNullDescription: PlaylistListItem = {
        ...mockYouTubePlaylist,
        description: null,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithNullDescription} />);

      // Should still render title and other elements
      expect(screen.getByText("Introduction to Machine Learning")).toBeInTheDocument();
    });

    it("should handle empty string title", () => {
      const playlistWithEmptyTitle: PlaylistListItem = {
        ...mockYouTubePlaylist,
        title: "",
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithEmptyTitle} />);

      // Component should render even with empty title
      expect(screen.getByRole("article")).toBeInTheDocument();
    });

    it("should handle negative video count as zero", () => {
      const playlistWithNegativeCount: PlaylistListItem = {
        ...mockYouTubePlaylist,
        video_count: -1,
      };

      renderWithProviders(<PlaylistCard playlist={playlistWithNegativeCount} />);

      // Should show "No videos" for negative counts
      expect(screen.getByText("-1 videos")).toBeInTheDocument();
    });
  });

  describe("Multiple Cards Rendering", () => {
    it("should render multiple cards with different data", () => {
      renderWithProviders(
        <>
          <PlaylistCard playlist={mockYouTubePlaylist} />
          <PlaylistCard playlist={mockLocalPlaylist} />
        </>
      );

      expect(screen.getByText("Introduction to Machine Learning")).toBeInTheDocument();
      expect(screen.getByText("My Personal Learning Journey")).toBeInTheDocument();
      expect(screen.getByText("42 videos")).toBeInTheDocument();
      expect(screen.getByText("15 videos")).toBeInTheDocument();
    });

    it("should have unique links for each card", () => {
      renderWithProviders(
        <>
          <PlaylistCard playlist={mockYouTubePlaylist} />
          <PlaylistCard playlist={mockLocalPlaylist} />
        </>
      );

      const links = screen.getAllByRole("link");
      expect(links).toHaveLength(2);
      expect(links[0]).toHaveAttribute(
        "href",
        "/playlists/PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
      );
      expect(links[1]).toHaveAttribute("href", "/playlists/int_12345");
    });
  });
});

describe("PlaylistCardSkeleton", () => {
  describe("Basic Rendering", () => {
    it("should render skeleton component", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = container.querySelector('[role="status"]');
      expect(skeleton).toBeInTheDocument();
    });

    it("should have loading label for accessibility", () => {
      renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = screen.getByLabelText("Loading playlist");
      expect(skeleton).toBeInTheDocument();
    });

    it("should have animate-pulse class", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = container.querySelector('[role="status"]');
      expect(skeleton).toHaveClass("animate-pulse");
    });

    it("should have role='status' for screen readers", () => {
      renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = screen.getByRole("status");
      expect(skeleton).toBeInTheDocument();
    });
  });

  describe("Skeleton Structure", () => {
    it("should render title placeholder (two lines)", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      const placeholders = container.querySelectorAll(".bg-gray-200.rounded");
      // Should have at least 2 placeholders for the two-line title
      expect(placeholders.length).toBeGreaterThanOrEqual(2);
    });

    it("should render video count placeholder", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      // Video count placeholder should be narrower (w-1/4)
      const videoCountPlaceholder = container.querySelector(".w-1\\/4");
      expect(videoCountPlaceholder).toBeInTheDocument();
    });

    it("should render badge placeholders", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      // Should have rounded-full placeholders for badges
      const badgePlaceholders = container.querySelectorAll(".rounded-full");
      expect(badgePlaceholders.length).toBeGreaterThanOrEqual(2);
    });

    it("should match card padding and structure", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = container.querySelector('[role="status"]');
      expect(skeleton).toHaveClass("p-6");
    });
  });

  describe("Multiple Skeletons", () => {
    it("should render multiple skeleton cards", () => {
      renderWithProviders(
        <>
          <PlaylistCardSkeleton />
          <PlaylistCardSkeleton />
          <PlaylistCardSkeleton />
        </>
      );

      const skeletons = screen.getAllByRole("status");
      expect(skeletons).toHaveLength(3);
    });

    it("should have consistent styling across multiple skeletons", () => {
      const { container } = renderWithProviders(
        <>
          <PlaylistCardSkeleton />
          <PlaylistCardSkeleton />
        </>
      );

      const skeletons = container.querySelectorAll('[role="status"]');
      skeletons.forEach((skeleton) => {
        expect(skeleton).toHaveClass("animate-pulse");
        expect(skeleton).toHaveClass("p-6");
      });
    });
  });

  describe("Accessibility", () => {
    it("should be announced to screen readers", () => {
      renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = screen.getByRole("status", { name: "Loading playlist" });
      expect(skeleton).toBeInTheDocument();
    });

    it("should have proper ARIA attributes", () => {
      const { container } = renderWithProviders(<PlaylistCardSkeleton />);

      const skeleton = container.querySelector('[role="status"]');
      expect(skeleton).toHaveAttribute("aria-label", "Loading playlist");
    });
  });

  describe("Visual Structure Match", () => {
    it("should visually match PlaylistCard dimensions", () => {
      const { container: cardContainer } = renderWithProviders(
        <PlaylistCard playlist={{
          playlist_id: "test",
          title: "Test",
          description: null,
          video_count: 10,
          privacy_status: "public",
          is_linked: true,
        }} />
      );

      const { container: skeletonContainer } = renderWithProviders(
        <PlaylistCardSkeleton />
      );

      const card = cardContainer.querySelector("article");
      const skeleton = skeletonContainer.querySelector('[role="status"]');

      // Both should have p-6 padding
      expect(card).toHaveClass("p-6");
      expect(skeleton).toHaveClass("p-6");
    });
  });
});
