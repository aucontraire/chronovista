/**
 * VideoDetailPage component displays comprehensive video information.
 *
 * Features:
 * - Video metadata display (title, channel, upload date, duration, views, likes)
 * - Full description with fallback for missing content
 * - Tags displayed as badges (hidden if no tags per edge case)
 * - Back to Videos navigation link (FR-004)
 * - Watch on YouTube external link (FR-006, FR-007, FR-008)
 * - Loading, error, and 404 states
 * - Cascading failure handling (FR-026 through FR-030):
 *   - When video API fails, TranscriptPanel is NOT rendered
 *   - Unified error message with Retry and Back to Videos options
 *   - Consistent error styling using CONTRAST_SAFE_COLORS
 */

import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import { LoadingState } from "../components/LoadingState";
import { TranscriptPanel } from "../components/transcript";
import { useVideoDetail } from "../hooks/useVideoDetail";
import { CONTRAST_SAFE_COLORS } from "../styles/tokens";

/** Default page title when no video is loaded */
const DEFAULT_PAGE_TITLE = "Chronovista";

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
 * Formats a date string to a readable absolute date (e.g., "Jan 15, 2024").
 *
 * @param dateString - ISO 8601 date string
 * @returns Formatted date string in "MMM D, YYYY" format
 */
function formatAbsoluteDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
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
 * Formats like count with K/M suffixes for readability.
 */
function formatLikeCount(count: number | null): string {
  if (count === null) {
    return "-- likes";
  }

  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M likes`;
  }

  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K likes`;
  }

  return `${count} likes`;
}

/**
 * Arrow left icon for back navigation.
 */
function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"
      />
    </svg>
  );
}

/**
 * External link icon for YouTube link.
 */
function ExternalLinkIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
      />
    </svg>
  );
}

/**
 * Warning icon for not found state.
 */
function WarningIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
      />
    </svg>
  );
}

/**
 * Exclamation triangle icon for error state.
 */
function ExclamationTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
      />
    </svg>
  );
}

/**
 * Refresh/retry icon for retry button.
 */
function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
      />
    </svg>
  );
}

/**
 * VideoDetailPage displays comprehensive video metadata.
 *
 * Route: /videos/:videoId
 *
 * Implements:
 * - FR-001: Dedicated video detail page at /videos/{video_id}
 * - FR-002: Display video title, channel, upload date, view count, duration, description
 * - FR-003: Display video tags as badges (if exist)
 * - FR-004: Back to Videos navigation link
 * - FR-006/FR-007/FR-008: Watch on YouTube external link
 * - FR-024: Video not found handling
 */
export function VideoDetailPage() {
  const { videoId } = useParams<{ videoId: string }>();
  // Note: error is destructured but not displayed directly per FR-027 (unified error message)
  const { data: video, isLoading, isError, error: _error, refetch } = useVideoDetail(
    videoId ?? ""
  );

  // Set browser tab title to "Channel - Video Title" when video loads
  useEffect(() => {
    if (video) {
      const channelName = video.channel_title ?? "Unknown Channel";
      document.title = `${channelName} - ${video.title}`;
    }

    // Reset title on unmount
    return () => {
      document.title = DEFAULT_PAGE_TITLE;
    };
  }, [video]);

  // Loading state
  if (isLoading) {
    return (
      <div className="p-6 lg:p-8">
        <LoadingState count={1} />
      </div>
    );
  }

  // Error state with unified error message (FR-026, FR-027, FR-029, FR-030)
  // When video API fails, TranscriptPanel is NOT rendered (FR-026)
  // Single unified error message prevents multiple error messages (FR-029)
  if (isError) {
    return (
      <div className="p-6 lg:p-8">
        {/* Unified error display with Retry and Back to Videos (FR-027) */}
        <div
          className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center max-w-lg mx-auto"
          role="alert"
          aria-live="polite"
        >
          {/* Error Icon */}
          <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
            <ExclamationTriangleIcon className="w-full h-full" />
          </div>

          {/* Error Message with CONTRAST_SAFE_COLORS (FR-030, NFR-A18) */}
          {/* Using text-gray-900 (16.6:1 contrast ratio) for error title */}
          <p className={`text-xl font-semibold ${CONTRAST_SAFE_COLORS.bodyText} mb-4`}>
            Could not load video.
          </p>

          {/* Action buttons: Retry and Back to Videos */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            {/* Retry Button */}
            <button
              type="button"
              onClick={() => void refetch()}
              className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
            >
              <RefreshIcon className="w-5 h-5 mr-2" />
              Retry
            </button>

            {/* Back to Videos Link */}
            <Link
              to="/videos"
              className="inline-flex items-center px-6 py-3 bg-slate-600 text-white font-semibold rounded-lg shadow-md hover:bg-slate-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 transition-all duration-200"
            >
              <ArrowLeftIcon className="w-5 h-5 mr-2" />
              Back to Videos
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 404 state when video not found (FR-024)
  if (!video) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] p-8">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md">
          {/* Warning Icon */}
          <div className="mx-auto w-16 h-16 mb-6 text-slate-400 bg-slate-100 rounded-full p-4">
            <WarningIcon className="w-full h-full" />
          </div>

          {/* Heading */}
          <h2 className="text-2xl font-bold text-slate-900 mb-3">
            Video Not Found
          </h2>

          {/* Description */}
          <p className="text-slate-600">
            The video you're looking for doesn't exist or has been removed.
          </p>

          {/* Navigation Link */}
          <Link
            to="/videos"
            className="inline-flex items-center mt-6 px-6 py-3 bg-slate-900 text-white font-semibold rounded-lg hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
          >
            <ArrowLeftIcon className="w-5 h-5 mr-2" />
            Back to Videos
          </Link>
        </div>
      </div>
    );
  }

  const {
    video_id,
    title,
    description,
    channel_id,
    channel_title,
    upload_date,
    duration,
    view_count,
    like_count,
    tags,
  } = video;

  const youtubeUrl = `https://www.youtube.com/watch?v=${video_id}`;

  return (
    <div className="p-6 lg:p-8">
      {/* Navigation Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        {/* Back to Videos Link (FR-004) */}
        <Link
          to="/videos"
          className="inline-flex items-center text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 mr-2" />
          Back to Videos
        </Link>

        {/* Watch on YouTube Link (FR-006, FR-007, FR-008) */}
        <a
          href={youtubeUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
        >
          <ExternalLinkIcon className="w-5 h-5 mr-2" />
          Watch on YouTube
          <span className="sr-only">(opens in new tab)</span>
        </a>
      </div>

      {/* Video Content Card */}
      <article className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8">
        {/* Video Title (FR-002) */}
        <h1 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-4">
          {title}
        </h1>

        {/* Channel Name (FR-002, FR-012, FR-013, FR-014, FR-015) */}
        {channel_id && channel_title ? (
          <Link
            to={`/channels/${channel_id}`}
            className="text-lg text-blue-500 hover:text-blue-600 hover:underline transition-colors mb-4 inline-block focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
          >
            {channel_title}
          </Link>
        ) : (
          <p className="text-lg text-gray-600 mb-4">Unknown Channel</p>
        )}

        {/* Video Metadata Row (FR-002) */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-500 mb-6">
          {/* Upload Date - shows absolute date (e.g., "Jan 15, 2024") */}
          <span className="inline-flex items-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-4 h-4 mr-1"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
              />
            </svg>
            {formatAbsoluteDate(upload_date)}
          </span>

          {/* Duration Badge */}
          <span className="inline-flex items-center bg-gray-100 px-2 py-0.5 rounded font-mono text-xs">
            {formatDuration(duration)}
          </span>

          {/* View Count */}
          <span className="inline-flex items-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-4 h-4 mr-1"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
              />
            </svg>
            {formatViewCount(view_count)}
          </span>

          {/* Like Count */}
          <span className="inline-flex items-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-4 h-4 mr-1"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V2.75a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m10.598-9.75H14.25M5.904 18.5c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 0 1-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 9.953 4.167 9.5 5 9.5h1.053c.472 0 .745.556.5.96a8.958 8.958 0 0 0-1.302 4.665c0 1.194.232 2.333.654 3.375Z"
              />
            </svg>
            {formatLikeCount(like_count)}
          </span>
        </div>

        {/* Tags Section (FR-003) - Hide if no tags per edge case */}
        {tags.length > 0 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-2">
              Tags
            </h2>
            <div className="flex flex-wrap gap-2">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Description Section (FR-002) */}
        <div className="border-t border-gray-100 pt-6">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
            Description
          </h2>
          <div className="prose prose-sm max-w-none text-gray-600 whitespace-pre-wrap">
            {description || "No description available"}
          </div>
        </div>
      </article>

      {/* Transcript Panel */}
      <TranscriptPanel videoId={video_id} />

      {/* Back to Videos Link */}
      <div className="mt-6">
        <Link
          to="/videos"
          className="inline-flex items-center text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 mr-2" />
          Back to Videos
        </Link>
      </div>
    </div>
  );
}
