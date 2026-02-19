/**
 * VideoCard component displays a single video item in the list.
 */

import { Link } from "react-router-dom";

import { cardPatterns, colorTokens } from "../styles";
import type { VideoListItem } from "../types/video";
import { AvailabilityBadge } from "./AvailabilityBadge";
import { isVideoUnavailable } from "../utils/availability";
import { API_BASE_URL } from "../api/config";

interface VideoCardProps {
  /** Video data to display */
  video: VideoListItem;
}

/**
 * Formats a duration in seconds to MM:SS or HH:MM:SS format.
 */
function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

/**
 * Formats a date string to relative time (e.g., "2 days ago") or ISO date.
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      if (diffMinutes <= 1) {
        return "Just now";
      }
      return `${diffMinutes} minutes ago`;
    }
    if (diffHours === 1) {
      return "1 hour ago";
    }
    return `${diffHours} hours ago`;
  }

  if (diffDays === 1) {
    return "Yesterday";
  }

  if (diffDays < 7) {
    return `${diffDays} days ago`;
  }

  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return weeks === 1 ? "1 week ago" : `${weeks} weeks ago`;
  }

  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return months === 1 ? "1 month ago" : `${months} months ago`;
  }

  const years = Math.floor(diffDays / 365);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}

/**
 * Formats view count with K/M suffixes for readability.
 */
function formatViewCount(count: number | null): string {
  if (count === null) {
    return "-- views";
  }

  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M views`;
  }

  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K views`;
  }

  return `${count} views`;
}

/**
 * Placeholder image URL for videos without thumbnails.
 * Uses a play icon SVG on gray background matching project patterns.
 */
const PLACEHOLDER_THUMBNAIL = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180' viewBox='0 0 320 180'%3E%3Crect fill='%23e2e8f0' width='320' height='180'/%3E%3Cpath fill='%2394a3b8' d='M128 60l48 30-48 30z'/%3E%3C/svg%3E";

/**
 * VideoCard displays video metadata in a card format.
 * Includes title, channel, duration, upload date, and transcript info.
 * Shows unavailability indicators when content is not available (Feature 023, FR-021).
 */
export function VideoCard({ video }: VideoCardProps) {
  const {
    title,
    channel_title,
    upload_date,
    duration,
    view_count,
    transcript_summary,
    availability_status,
  } = video;

  // Determine if video is unavailable
  const isUnavailable = isVideoUnavailable(availability_status);
  // Only apply heavy dimming when there's no recovered title
  const hasRecoveredData = isUnavailable && !!title;
  const cardOpacity = isUnavailable && !hasRecoveredData ? "opacity-50" : "";
  const titleDecoration = isUnavailable && !hasRecoveredData ? "line-through" : "";

  // Use proxy URL for video thumbnails (Feature 026)
  const thumbnailUrl = `${API_BASE_URL}/images/videos/${video.video_id}?quality=mqdefault`;

  return (
    <Link
      to={`/videos/${video.video_id}`}
      className="block no-underline text-inherit focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-xl"
    >
      <article
        className={`${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.transition} overflow-hidden ${cardOpacity}`}
        role="article"
        aria-label={isUnavailable && !title ? `Unavailable video` : `Video: ${title}`}
      >
      {/* Video Thumbnail */}
      <img
        src={thumbnailUrl}
        alt={title || "Video thumbnail"}
        className="w-full aspect-video object-cover"
        loading="lazy"
        onError={(e) => {
          e.currentTarget.src = PLACEHOLDER_THUMBNAIL;
        }}
      />

      {/* Video Content */}
      <div className="p-5">
      {/* Video Title with Availability Badge */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className={`text-lg font-semibold text-${colorTokens.text.primary} line-clamp-2 flex-1 ${titleDecoration}`}>
          {title || (isUnavailable ? "Unavailable Video" : "")}
        </h3>
        <AvailabilityBadge status={availability_status} className="flex-shrink-0" />
      </div>

      {/* Channel Name */}
      <p className={`text-sm text-${colorTokens.text.secondary} mb-3`}>
        {channel_title ?? "Unknown Channel"}
      </p>

      {/* Video Metadata Row */}
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-${colorTokens.text.tertiary}`}>
        {/* Duration Badge */}
        <span className="inline-flex items-center bg-gray-100 px-2 py-0.5 rounded font-mono text-xs">
          {formatDuration(duration)}
        </span>

        {/* Upload Date */}
        <span title={new Date(upload_date).toLocaleDateString()}>
          {formatRelativeTime(upload_date)}
        </span>

        {/* View Count */}
        <span>{formatViewCount(view_count)}</span>
      </div>

      {/* Transcript Info */}
      {transcript_summary.count > 0 && (
        <div className={`mt-3 pt-3 border-t border-${colorTokens.border}`}>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                transcript_summary.has_manual
                  ? `bg-${colorTokens.status.success.bg} text-${colorTokens.status.success.text}`
                  : `bg-${colorTokens.status.info.bg} text-${colorTokens.status.info.text}`
              }`}
            >
              {transcript_summary.has_manual ? "Manual CC" : "Auto CC"}
            </span>
            <span className={`text-${colorTokens.text.tertiary}`}>
              {transcript_summary.count} transcript
              {transcript_summary.count !== 1 ? "s" : ""}
              {transcript_summary.languages.length > 0 && (
                <span className="ml-1">
                  ({transcript_summary.languages.slice(0, 3).join(", ")}
                  {transcript_summary.languages.length > 3 && "..."})
                </span>
              )}
            </span>
          </div>
        </div>
      )}
      </div>
      </article>
    </Link>
  );
}
