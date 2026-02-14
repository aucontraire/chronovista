/**
 * PlaylistVideoCard component displays a single video item within a playlist.
 *
 * Features:
 * - Position badge showing 1-indexed position (#1, #2, #3, etc.)
 * - Video title, channel name, upload date, duration
 * - Unavailable indicator: opacity-50, line-through title, tooltip
 * - TranscriptSummary badge if transcripts available
 * - Clickable card linking to video detail page
 * - Accessible with keyboard navigation support
 *
 * Visual design:
 * - Position badge: circular, bg-gray-100, text-gray-700, w-8 h-8
 * - Card: bg-white, rounded-lg, shadow-sm, hover:shadow-md
 * - Unavailable state: opacity-50 on entire card, line-through on title only
 *
 * @example
 * ```tsx
 * <PlaylistVideoCard video={playlistVideoItem} />
 * ```
 */

import { Link } from "react-router-dom";

import { cardPatterns, colorTokens } from "../styles";
import type { PlaylistVideoItem } from "../types/playlist";
import { formatDate, formatTimestamp } from "../utils/formatters";
import { AvailabilityBadge } from "./AvailabilityBadge";
import { isVideoUnavailable } from "../utils/availability";

interface PlaylistVideoCardProps {
  /** Playlist video data to display */
  video: PlaylistVideoItem;
}

/**
 * PlaylistVideoCard displays a video within a playlist context.
 * Shows position badge, video metadata, and handles unavailable video state.
 */
export function PlaylistVideoCard({ video }: PlaylistVideoCardProps) {
  const {
    video_id,
    title,
    channel_title,
    upload_date,
    duration,
    transcript_summary,
    position,
    availability_status,
  } = video;

  // Convert 0-indexed position to 1-indexed display format
  const displayPosition = position + 1;

  // Derive unavailable state from availability_status
  const isUnavailable = isVideoUnavailable(availability_status);

  // Apply unavailable state styling
  const cardOpacity = isUnavailable ? "opacity-50" : "";
  const titleDecoration = isUnavailable ? "line-through" : "";

  return (
    <Link
      to={`/videos/${video_id}`}
      className="block no-underline text-inherit focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-lg"
      aria-label={isUnavailable ? `Unavailable video (was at position ${displayPosition})` : `Video: ${title} at position ${displayPosition}`}
    >
      <article
        className={`${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.transition} p-4 ${cardOpacity}`}
        role="article"
      >
        <div className="flex items-start gap-3">
          {/* Position Badge */}
          <div
            className="flex-shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 text-gray-700 text-sm font-semibold"
            aria-label={`Position ${displayPosition}`}
          >
            #{displayPosition}
          </div>

          {/* Video Content */}
          <div className="flex-1 min-w-0">
            {/* Video Title with Availability Badge */}
            <div className="flex items-start justify-between gap-2 mb-1">
              <h3
                className={`text-base font-semibold text-${colorTokens.text.primary} line-clamp-2 flex-1 ${titleDecoration}`}
                title={isUnavailable ? "This video is no longer available on YouTube" : title}
              >
                {isUnavailable ? "Unavailable Video" : title}
              </h3>
              <AvailabilityBadge status={availability_status} className="flex-shrink-0" />
            </div>

            {/* Channel Name */}
            <p className={`text-sm text-${colorTokens.text.secondary}`}>
              {channel_title ?? "Unknown Channel"}
            </p>

            {/* Video Metadata Row */}
            <div className={`mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-${colorTokens.text.tertiary}`}>
              {/* Duration Badge */}
              <span className="inline-flex items-center bg-gray-100 px-2 py-0.5 rounded font-mono">
                {formatTimestamp(duration)}
              </span>

              {/* Upload Date */}
              <span>{formatDate(upload_date)}</span>
            </div>

            {/* Transcript Info (only if transcripts available) */}
            {transcript_summary.count > 0 && (
              <div className="mt-2">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    transcript_summary.has_manual
                      ? `bg-${colorTokens.status.success.bg} text-${colorTokens.status.success.text}`
                      : `bg-${colorTokens.status.info.bg} text-${colorTokens.status.info.text}`
                  }`}
                  title={`${transcript_summary.count} transcript${transcript_summary.count !== 1 ? "s" : ""} available`}
                >
                  {transcript_summary.has_manual ? "Manual CC" : "Auto CC"}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Unavailable Indicator Tooltip */}
        {isUnavailable && (
          <div className="sr-only">
            This video is no longer available on YouTube
          </div>
        )}
      </article>
    </Link>
  );
}

/**
 * PlaylistVideoCardSkeleton displays a loading placeholder for PlaylistVideoCard.
 * Matches the dimensions and structure of the actual card.
 *
 * @example
 * ```tsx
 * <PlaylistVideoCardSkeleton />
 * ```
 */
export function PlaylistVideoCardSkeleton() {
  return (
    <div
      className={`${cardPatterns.base} p-4 animate-pulse`}
      role="status"
      aria-label="Loading video"
    >
      <div className="flex items-start gap-3">
        {/* Position badge placeholder */}
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200" />

        {/* Content placeholder */}
        <div className="flex-1 min-w-0">
          {/* Title placeholder - two lines */}
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
          <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />

          {/* Channel name placeholder */}
          <div className="h-3 bg-gray-200 rounded w-1/3 mb-2" />

          {/* Metadata row placeholder */}
          <div className="flex items-center gap-3">
            <div className="h-5 bg-gray-200 rounded w-12" />
            <div className="h-3 bg-gray-200 rounded w-20" />
          </div>
        </div>
      </div>
    </div>
  );
}
