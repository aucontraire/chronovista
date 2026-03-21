/**
 * Tests for VideoEmbed Component
 *
 * Covers the following requirements:
 * - FR-007: YouTube IFrame embed when video is available
 * - FR-010a: Pre-render availability check — static thumbnail for unavailable videos
 * - FR-010b: Runtime player error fallback to static thumbnail (driven by playerError prop)
 * - FR-012: Watch history disclosure note with all three required content points
 * - FR-018/FR-019: aspect-video class and minimum size constraints
 * - NFR-003: Privacy-enhanced mode via youtube-nocookie.com (handled by useYouTubePlayer
 *   in the parent; VideoEmbed just attaches the containerRef)
 *
 * Architecture note (Feature 048 wiring fix):
 * VideoEmbed is now a presentational component. useYouTubePlayer has been lifted
 * to VideoDetailPage so that seekTo/activeSegmentId/followPlayback can be shared
 * with TranscriptPanel. VideoEmbed receives containerRef and playerError as props.
 *
 * - VideoEmbed: owns the FR-010a pre-render availability check. When the video
 *   is not "available" it returns early and renders ThumbnailFallback directly.
 * - VideoEmbedInner: renders the player div shell using the externally-managed
 *   containerRef and playerError. Handles FR-010b (runtime error fallback).
 */

import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { VideoEmbed } from "../../components/video/VideoEmbed";
import type { PlayerError } from "../../hooks/useYouTubePlayer";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

const TEST_VIDEO_ID = "dQw4w9WgXcQ";

/** Creates a React ref for the player container div. */
function makeContainerRef() {
  return createRef<HTMLDivElement | null>();
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("VideoEmbed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // FR-007: Embed renders for available video
  // -------------------------------------------------------------------------

  describe("Embed renders when video is available (FR-007)", () => {
    it("renders the player container div", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const playerDiv = screen.getByLabelText("YouTube video player");
      expect(playerDiv).toBeInTheDocument();
    });

    it("renders the outer section landmark with accessible label", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const section = screen.getByRole("region", { name: "Video embed" });
      expect(section).toBeInTheDocument();
    });

    it("does not render a thumbnail image when the player is active (no error)", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      // No <img> should appear in the normal player path
      const img = screen.queryByRole("img");
      expect(img).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // FR-010a: Pre-render fallback for unavailable video
  // -------------------------------------------------------------------------

  describe("Fallback to thumbnail when video is unavailable (FR-010a)", () => {
    it("renders the static thumbnail image", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const img = screen.getByRole("img");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute(
        "src",
        `https://img.youtube.com/vi/${TEST_VIDEO_ID}/hqdefault.jpg`
      );
    });

    it("renders the thumbnail with a descriptive alt text", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const img = screen.getByRole("img");
      expect(img).toHaveAttribute(
        "alt",
        `Thumbnail for YouTube video ${TEST_VIDEO_ID}`
      );
    });

    it("renders a Watch on YouTube link", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const link = screen.getByRole("link", { name: /watch on youtube/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute(
        "href",
        `https://www.youtube.com/watch?v=${TEST_VIDEO_ID}`
      );
    });

    it("opens the Watch on YouTube link in a new tab", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const link = screen.getByRole("link", { name: /watch on youtube/i });
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("shows the unavailability message in the overlay", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      expect(
        screen.getByText("This video is not currently available.")
      ).toBeInTheDocument();
    });

    it("also shows thumbnail fallback for deleted availability status", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="deleted"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      expect(screen.getByRole("img")).toBeInTheDocument();
    });

    it("does NOT render the watch history disclosure note in the unavailable path", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      // The disclosure paragraph is only rendered by VideoEmbedInner.
      expect(
        screen.queryByLabelText("Watch history and privacy disclosure")
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // FR-010b: Runtime player error fallback (driven by playerError prop)
  // -------------------------------------------------------------------------

  describe("Fallback on player error (FR-010b)", () => {
    it("renders the thumbnail fallback when playerError is a fatal error code", () => {
      const error: PlayerError = {
        code: 100,
        message: "The video was not found. It may have been removed.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      const img = screen.getByRole("img");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute(
        "src",
        `https://img.youtube.com/vi/${TEST_VIDEO_ID}/hqdefault.jpg`
      );
    });

    it("displays the error message from playerError", () => {
      const error: PlayerError = {
        code: 100,
        message: "The video was not found. It may have been removed.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      expect(
        screen.getByText("The video was not found. It may have been removed.")
      ).toBeInTheDocument();
    });

    it("renders the error overlay with role=status and aria-live=polite", () => {
      const error: PlayerError = {
        code: 5,
        message: "The video cannot be played in an embedded player.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      const overlay = screen.getByRole("status");
      expect(overlay).toBeInTheDocument();
      expect(overlay).toHaveAttribute("aria-live", "polite");
    });

    it("shows the Watch on YouTube link in the error fallback", () => {
      const error: PlayerError = {
        code: 101,
        message: "The video owner does not allow embedded playback.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      const link = screen.getByRole("link", { name: /watch on youtube/i });
      expect(link).toBeInTheDocument();
    });

    it("shows 'Video player could not be loaded.' for the API load timeout (error code -1)", () => {
      const error: PlayerError = {
        code: -1,
        message:
          "The YouTube player failed to load within 10 seconds. Check your network connection and try again.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      expect(
        screen.getByText("Video player could not be loaded.")
      ).toBeInTheDocument();
    });

    it("does NOT trigger fallback for non-fatal error codes (e.g. code 3)", () => {
      // Error code 3 is not in FALLBACK_TRIGGER_CODES — the player div should
      // still render.
      const error: PlayerError = {
        code: 3,
        message: "Playback interrupted.",
      };

      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      // The player container div is still rendered.
      expect(screen.getByLabelText("YouTube video player")).toBeInTheDocument();
      // No thumbnail image in this path.
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // FR-012: Watch history disclosure note
  // -------------------------------------------------------------------------

  describe("Watch history disclosure note (FR-012)", () => {
    it("renders the disclosure note when the player is active", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const disclosure = screen.getByLabelText(
        "Watch history and privacy disclosure"
      );
      expect(disclosure).toBeInTheDocument();
    });

    it("contains the watch history warning (content point 1 of 3)", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const disclosure = screen.getByLabelText(
        "Watch history and privacy disclosure"
      );
      expect(disclosure).toHaveTextContent(
        "Playing this video may add it to your YouTube watch history."
      );
    });

    it("contains the privacy-enhanced mode mention (content point 2 of 3)", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const disclosure = screen.getByLabelText(
        "Watch history and privacy disclosure"
      );
      expect(disclosure).toHaveTextContent(
        "This embed uses privacy-enhanced mode (youtube-nocookie.com)."
      );
    });

    it("contains the incognito suggestion (content point 3 of 3)", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const disclosure = screen.getByLabelText(
        "Watch history and privacy disclosure"
      );
      expect(disclosure).toHaveTextContent(
        "Use an incognito window if you prefer not to affect your watch history."
      );
    });
  });

  // -------------------------------------------------------------------------
  // FR-018/FR-019: Aspect ratio and minimum size constraints
  // -------------------------------------------------------------------------

  describe("Aspect ratio and minimum size (FR-018/FR-019)", () => {
    it("applies aspect-video class to the player container wrapper", () => {
      const { container } = render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const aspectWrapper = container.querySelector(".aspect-video");
      expect(aspectWrapper).toBeInTheDocument();
    });

    it("applies min-w-[400px] to the outer section (FR-018 minimum column width)", () => {
      const { container } = render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const section = container.querySelector("section");
      expect(section).toHaveClass("min-w-[400px]");
    });

    it("applies min-h-[200px] to the outer section (FR-019 YouTube ToS minimum height)", () => {
      const { container } = render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const section = container.querySelector("section");
      expect(section).toHaveClass("min-h-[200px]");
    });

    it("applies min-w-[400px] and min-h-[200px] to the unavailable fallback section as well", () => {
      const { container } = render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="unavailable"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const section = container.querySelector("section");
      expect(section).toHaveClass("min-w-[400px]");
      expect(section).toHaveClass("min-h-[200px]");
    });
  });

  // -------------------------------------------------------------------------
  // NFR-003: Privacy-enhanced mode (youtube-nocookie.com)
  // -------------------------------------------------------------------------

  describe("Privacy-enhanced mode mention (NFR-003)", () => {
    it("mentions youtube-nocookie.com in the disclosure note", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      const disclosure = screen.getByLabelText(
        "Watch history and privacy disclosure"
      );
      expect(disclosure).toHaveTextContent("youtube-nocookie.com");
    });
  });

  // -------------------------------------------------------------------------
  // Edge cases
  // -------------------------------------------------------------------------

  describe("Edge cases", () => {
    it("renders thumbnail fallback for empty-string availabilityStatus", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus=""
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      expect(screen.getByRole("img")).toBeInTheDocument();
    });

    it("renders the player path when availabilityStatus is exactly 'available'", () => {
      render(
        <VideoEmbed
          videoId={TEST_VIDEO_ID}
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={null}
        />
      );

      expect(screen.getByLabelText("YouTube video player")).toBeInTheDocument();
    });

    it("uses the videoId in the thumbnail URL for error code 2 (invalid video ID)", () => {
      const error: PlayerError = {
        code: 2,
        message: "The video ID is invalid.",
      };

      render(
        <VideoEmbed
          videoId="INVALID_ID"
          availabilityStatus="available"
          containerRef={makeContainerRef()}
          playerError={error}
        />
      );

      const img = screen.getByRole("img");
      expect(img).toHaveAttribute(
        "src",
        "https://img.youtube.com/vi/INVALID_ID/hqdefault.jpg"
      );
    });
  });
});
