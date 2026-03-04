/**
 * Tests for VideoCard Component - Corrections Badge (Feature 035, T020a).
 *
 * Test coverage:
 * - Renders "Corrections" badge when transcript_summary.has_corrections is true
 * - Does NOT render badge when has_corrections is false
 * - Handles missing has_corrections field (defaults to false via ?? operator)
 * - Badge has aria-label="Transcript has corrections"
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { VideoCard } from "../VideoCard";
import type { VideoListItem } from "../../types/video";

/**
 * Test factory for VideoListItem with sensible defaults.
 * Allows partial overrides of transcript_summary.
 */
function createTestVideo(
  transcriptSummaryOverrides: Partial<VideoListItem["transcript_summary"]> = {}
): VideoListItem {
  return {
    video_id: "test-video-123",
    title: "Test Video Title",
    channel_id: "UCtest",
    channel_title: "Test Channel",
    upload_date: "2024-01-15T00:00:00Z",
    duration: 300,
    view_count: 12345,
    transcript_summary: {
      count: 1,
      languages: ["en"],
      has_manual: true,
      has_corrections: false,
      ...transcriptSummaryOverrides,
    },
    tags: [],
    category_id: null,
    category_name: null,
    topics: [],
    availability_status: "available",
    recovered_at: null,
    recovery_source: null,
  };
}

/**
 * Helper to render VideoCard inside MemoryRouter (required because VideoCard renders a Link).
 */
function renderVideoCard(video: VideoListItem) {
  return render(
    <MemoryRouter>
      <VideoCard video={video} />
    </MemoryRouter>
  );
}

describe("VideoCard - Corrections Badge", () => {
  describe("Badge renders when has_corrections is true", () => {
    it("renders 'Corrections' badge when has_corrections is true", () => {
      const video = createTestVideo({ has_corrections: true });
      renderVideoCard(video);

      expect(screen.getByText("Corrections")).toBeInTheDocument();
    });

    it("badge has aria-label='Transcript has corrections' for accessibility", () => {
      const video = createTestVideo({ has_corrections: true });
      renderVideoCard(video);

      const badge = screen.getByLabelText("Transcript has corrections");
      expect(badge).toBeInTheDocument();
    });

    it("badge has correct amber styling classes", () => {
      const video = createTestVideo({ has_corrections: true });
      renderVideoCard(video);

      const badge = screen.getByLabelText("Transcript has corrections");
      expect(badge).toHaveClass("bg-amber-100");
      expect(badge).toHaveClass("text-amber-800");
      expect(badge).toHaveClass("border-amber-200");
    });
  });

  describe("Badge does NOT render when has_corrections is false", () => {
    it("does not render 'Corrections' badge when has_corrections is false", () => {
      const video = createTestVideo({ has_corrections: false });
      renderVideoCard(video);

      expect(screen.queryByText("Corrections")).not.toBeInTheDocument();
    });

    it("does not render badge with aria-label when has_corrections is false", () => {
      const video = createTestVideo({ has_corrections: false });
      renderVideoCard(video);

      expect(
        screen.queryByLabelText("Transcript has corrections")
      ).not.toBeInTheDocument();
    });
  });

  describe("Badge defaults to hidden when has_corrections is absent", () => {
    it("does not render badge when has_corrections is not set (defaults to false via ?? operator)", () => {
      // Build a video whose transcript_summary is missing has_corrections.
      // TypeScript requires the full type, so we cast to simulate a server
      // response that omits the optional field.
      const video = createTestVideo();
      // Simulate missing field by deleting it from the object after creation
      const transcriptSummaryWithoutField = { ...video.transcript_summary };
      delete (transcriptSummaryWithoutField as Record<string, unknown>)[
        "has_corrections"
      ];
      const videoWithMissingField: VideoListItem = {
        ...video,
        transcript_summary: transcriptSummaryWithoutField as VideoListItem["transcript_summary"],
      };

      renderVideoCard(videoWithMissingField);

      // ?? false defensiveness means no badge should appear
      expect(screen.queryByText("Corrections")).not.toBeInTheDocument();
    });
  });

  describe("Badge co-exists with other transcript info", () => {
    it("shows both the CC badge and Corrections badge when both conditions are true", () => {
      const video = createTestVideo({
        has_manual: true,
        has_corrections: true,
      });
      renderVideoCard(video);

      expect(screen.getByText("Manual CC")).toBeInTheDocument();
      expect(screen.getByText("Corrections")).toBeInTheDocument();
    });

    it("shows only CC badge (not Corrections) when has_corrections is false", () => {
      const video = createTestVideo({
        has_manual: true,
        has_corrections: false,
      });
      renderVideoCard(video);

      expect(screen.getByText("Manual CC")).toBeInTheDocument();
      expect(screen.queryByText("Corrections")).not.toBeInTheDocument();
    });

    it("does not render transcript info section at all when count is 0", () => {
      const video = createTestVideo({
        count: 0,
        has_corrections: true,
      });
      renderVideoCard(video);

      // The whole transcript info section is gated on count > 0
      expect(screen.queryByText("Corrections")).not.toBeInTheDocument();
    });
  });
});
