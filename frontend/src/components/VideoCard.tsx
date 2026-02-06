/**
 * VideoCard component displays a single video item in the list.
 */

import type { VideoListItem } from "../types/video";

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
 * VideoCard displays video metadata in a card format.
 * Includes title, channel, duration, upload date, and transcript info.
 */
export function VideoCard({ video }: VideoCardProps) {
  const {
    title,
    channel_title,
    upload_date,
    duration,
    view_count,
    transcript_summary,
  } = video;

  return (
    <article
      className="bg-white rounded-xl shadow-md border border-gray-100 p-5 hover:shadow-xl hover:border-gray-200 transition-all duration-200 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2"
      tabIndex={0}
      role="article"
      aria-label={`Video: ${title}`}
    >
      {/* Video Title */}
      <h3 className="text-lg font-semibold text-gray-900 line-clamp-2 mb-2">
        {title}
      </h3>

      {/* Channel Name */}
      <p className="text-sm text-gray-600 mb-3">
        {channel_title ?? "Unknown Channel"}
      </p>

      {/* Video Metadata Row */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-500">
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
        <div className="mt-3 pt-3 border-t border-gray-100">
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                transcript_summary.has_manual
                  ? "bg-green-100 text-green-800"
                  : "bg-blue-100 text-blue-800"
              }`}
            >
              {transcript_summary.has_manual ? "Manual CC" : "Auto CC"}
            </span>
            <span className="text-gray-500">
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
    </article>
  );
}
