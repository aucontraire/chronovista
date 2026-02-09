/**
 * PlaylistDetailPage displays comprehensive playlist information with video list.
 *
 * Features:
 * - Playlist metadata (title, description, video count, privacy, published date, type)
 * - Description truncation with "Show more/less" toggle for descriptions > 200 chars
 * - "View on YouTube" link for linked playlists
 * - Back to Playlists navigation (top and bottom)
 * - Video list using PlaylistVideoCard with infinite scroll
 * - Loading, error, and empty states
 * - 404 handling for missing playlists
 *
 * Route: /playlists/:playlistId
 *
 * Implements:
 * - CHK007: External links open in new tab with security attributes
 * - CHK008: Declarative navigation with React Router Link
 * - CHK009: 404 page design pattern
 * - CHK010: Playlist detail header layout
 * - CHK041: Description truncation with "Show more/less" toggle
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { LoadingState } from "../components/LoadingState";
import { PlaylistVideoCard } from "../components/PlaylistVideoCard";
import { usePlaylistDetail, usePlaylistVideos } from "../hooks";
import { cardPatterns } from "../styles";
import type { PlaylistPrivacyStatus } from "../types/playlist";
import { formatDate } from "../utils/formatters";

/** Default page title when no playlist is loaded */
const DEFAULT_PAGE_TITLE = "ChronoVista";

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
 * Calendar icon for published date.
 */
function CalendarIcon({ className }: { className?: string }) {
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
        d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
      />
    </svg>
  );
}

/**
 * Video icon for video count.
 */
function VideoIcon({ className }: { className?: string }) {
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
        d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
      />
    </svg>
  );
}

/**
 * Film icon for empty playlist state (CHK047).
 */
function FilmIcon({ className }: { className?: string }) {
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
        d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-3.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-1.5A1.125 1.125 0 0 1 18 18.375M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-1.5C18.504 4.5 18 5.004 18 5.625m3.75 0v1.5c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M3.375 4.5h1.5C5.496 4.5 6 5.004 6 5.625m-3.75 0v1.5c0 .621.504 1.125 1.125 1.125m0 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m1.5-3.75C5.496 8.25 6 7.746 6 7.125v-1.5M4.875 8.25C5.496 8.25 6 8.754 6 9.375v1.5m0-5.25v5.25m0-5.25C6 5.004 6.504 4.5 7.125 4.5h9.75c.621 0 1.125.504 1.125 1.125m1.125 2.625h1.5m-1.5 0A1.125 1.125 0 0 1 18 7.125v-1.5m1.125 2.625c-.621 0-1.125.504-1.125 1.125v1.5m2.625-2.625c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125M18 5.625v5.25M7.125 12h9.75m-9.75 0A1.125 1.125 0 0 1 6 10.875M7.125 12C6.504 12 6 12.504 6 13.125m0-2.25C6 11.496 5.496 12 4.875 12M18 10.875c0 .621-.504 1.125-1.125 1.125M18 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m-12 5.25v-5.25m0 5.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125m-12 0v-1.5c0-.621-.504-1.125-1.125-1.125M18 18.375v-5.25m0 5.25v-1.5c0-.621.504-1.125 1.125-1.125M18 13.125v1.5c0 .621.504 1.125 1.125 1.125M18 13.125c0-.621.504-1.125 1.125-1.125M6 13.125v1.5c0 .621-.504 1.125-1.125 1.125M6 13.125C6 12.504 5.496 12 4.875 12m-1.5 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M19.125 12h1.5m0 0c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h1.5m14.25 0h1.5"
      />
    </svg>
  );
}

/**
 * Privacy badge component for playlist privacy status.
 */
function PrivacyBadge({ status }: { status: PlaylistPrivacyStatus }) {
  const styles: Record<
    PlaylistPrivacyStatus,
    { bg: string; text: string; label: string }
  > = {
    public: { bg: "bg-green-100", text: "text-green-800", label: "Public" },
    private: { bg: "bg-red-100", text: "text-red-800", label: "Private" },
    unlisted: {
      bg: "bg-yellow-100",
      text: "text-yellow-800",
      label: "Unlisted",
    },
  };

  const style = styles[status];

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
    >
      {style.label}
    </span>
  );
}

/**
 * Type badge component showing if playlist is linked to YouTube.
 */
function PlaylistTypeBadge({ isLinked }: { isLinked: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
        isLinked
          ? "bg-blue-100 text-blue-800"
          : "bg-gray-100 text-gray-700"
      }`}
    >
      {isLinked ? "YouTube" : "Local"}
    </span>
  );
}

/**
 * PlaylistDetailPage displays comprehensive playlist metadata and videos.
 *
 * Route: /playlists/:playlistId
 *
 * Implements:
 * - CHK007: External links with security attributes
 * - CHK008: React Router navigation
 * - CHK009: 404 handling
 * - CHK010: Header layout
 * - CHK041: Description truncation with toggle
 */
export function PlaylistDetailPage() {
  const { playlistId } = useParams<{ playlistId: string }>();
  const {
    playlist,
    isLoading: headerLoading,
    isError: headerError,
    error: headerErrorObj,
    retry: headerRetry,
  } = usePlaylistDetail(playlistId || "");

  const {
    videos,
    isLoading: videosLoading,
    isError: videosError,
    hasNextPage,
    isFetchingNextPage,
    loadMoreRef,
  } = usePlaylistVideos(playlistId || "", {
    enabled: Boolean(playlistId) && Boolean(playlist),
  });

  // Description truncation state (CHK041)
  const [showFullDescription, setShowFullDescription] = useState(false);
  const DESCRIPTION_THRESHOLD = 200;

  // Check if error is a 404 (playlist not found)
  const is404 =
    headerError &&
    headerErrorObj &&
    typeof headerErrorObj === "object" &&
    "status" in headerErrorObj &&
    headerErrorObj.status === 404;

  // Set browser tab title based on state (CHK074)
  useEffect(() => {
    if (headerLoading) {
      document.title = "Loading... - ChronoVista";
    } else if (is404 || (!playlist && !headerLoading)) {
      document.title = "Playlist Not Found - ChronoVista";
    } else if (playlist) {
      document.title = `${playlist.title} - ChronoVista`;
    }

    // Reset title on unmount
    return () => {
      document.title = DEFAULT_PAGE_TITLE;
    };
  }, [playlist, headerLoading, is404]);

  // Loading state
  if (headerLoading) {
    return (
      <div className="p-6 lg:p-8">
        <LoadingState count={1} />
      </div>
    );
  }

  // 404 state when playlist not found (CHK009)
  if (is404 || (!playlist && !headerLoading)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] p-8">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md">
          {/* Warning Icon */}
          <div className="mx-auto w-16 h-16 mb-6 text-slate-400 bg-slate-100 rounded-full p-4">
            <WarningIcon className="w-full h-full" />
          </div>

          {/* Heading */}
          <h2 className="text-2xl font-bold text-slate-900 mb-3">
            Playlist Not Found
          </h2>

          {/* Description */}
          <p className="text-slate-600 mb-6">
            The playlist you're looking for doesn't exist or has been removed
            from your library.
          </p>

          {/* Navigation Link */}
          <Link
            to="/playlists"
            className="inline-flex items-center px-6 py-3 bg-slate-900 text-white font-semibold rounded-lg hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
          >
            <ArrowLeftIcon className="w-5 h-5 mr-2" />
            Back to Playlists
          </Link>
        </div>
      </div>
    );
  }

  // Generic error state with retry (non-404 errors)
  if (headerError) {
    return (
      <div className="p-6 lg:p-8">
        <div
          className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center max-w-lg mx-auto"
          role="alert"
          aria-live="polite"
        >
          {/* Error Icon */}
          <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
            <ExclamationTriangleIcon className="w-full h-full" />
          </div>

          {/* Error Message */}
          <p className="text-xl font-semibold text-gray-900 mb-4">
            Could not load playlist.
          </p>

          {/* Action buttons: Retry and Back to Playlists */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            {/* Retry Button */}
            <button
              type="button"
              onClick={() => void headerRetry()}
              className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
            >
              <RefreshIcon className="w-5 h-5 mr-2" />
              Retry
            </button>

            {/* Back to Playlists Link */}
            <Link
              to="/playlists"
              className="inline-flex items-center px-6 py-3 bg-slate-600 text-white font-semibold rounded-lg shadow-md hover:bg-slate-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 transition-all duration-200"
            >
              <ArrowLeftIcon className="w-5 h-5 mr-2" />
              Back to Playlists
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // TypeScript guard: playlist must be loaded at this point
  if (!playlist) {
    return null;
  }

  const {
    playlist_id,
    title,
    description,
    video_count,
    privacy_status,
    is_linked,
    published_at,
  } = playlist;

  // Check if description needs truncation (CHK041)
  const needsTruncation = description && description.length > DESCRIPTION_THRESHOLD;

  // Generate YouTube URL for linked playlists
  const youtubeUrl =
    is_linked && playlist_id.startsWith("PL")
      ? `https://www.youtube.com/playlist?list=${playlist_id}`
      : null;

  return (
    <div className="p-6 lg:p-8">
      {/* Navigation Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        {/* Back to Playlists Link (CHK008) */}
        <Link
          to="/playlists"
          className="inline-flex items-center text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 mr-2" />
          Back to Playlists
        </Link>

        {/* View on YouTube Link (CHK007) - Only for linked playlists */}
        {youtubeUrl && (
          <a
            href={youtubeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            <ExternalLinkIcon className="w-5 h-5 mr-2" />
            View on YouTube
            <span className="sr-only">(opens in new tab)</span>
          </a>
        )}
      </div>

      {/* Playlist Header Card (CHK010) */}
      <article
        className={`${cardPatterns.base} p-6 lg:p-8 mb-8`}
      >
        {/* 1. Title */}
        <h1 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-4">
          {title}
        </h1>

        {/* 2. Metadata Row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-500 mb-6">
          {/* Published Date */}
          {published_at && (
            <span className="inline-flex items-center">
              <CalendarIcon className="w-4 h-4 mr-1" aria-hidden="true" />
              {formatDate(published_at)}
            </span>
          )}

          {/* Video Count */}
          <span className="inline-flex items-center">
            <VideoIcon className="w-4 h-4 mr-1" aria-hidden="true" />
            {video_count} {video_count === 1 ? "video" : "videos"}
          </span>

          {/* Privacy Badge */}
          <PrivacyBadge status={privacy_status} />

          {/* Type Badge */}
          <PlaylistTypeBadge isLinked={is_linked} />
        </div>

        {/* 3. Description with truncation (CHK041) */}
        <div className="border-t border-gray-100 pt-6">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
            Description
          </h2>
          {description ? (
            <div className="prose prose-sm max-w-none text-gray-600 whitespace-pre-wrap">
              {needsTruncation && !showFullDescription
                ? `${description.slice(0, DESCRIPTION_THRESHOLD)}...`
                : description}
              {needsTruncation && (
                <button
                  onClick={() => setShowFullDescription(!showFullDescription)}
                  aria-expanded={showFullDescription}
                  className="ml-2 text-blue-600 hover:text-blue-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
                >
                  {showFullDescription ? "Show less" : "Show more"}
                </button>
              )}
            </div>
          ) : (
            <span className="text-gray-500 italic">No description</span>
          )}
        </div>
      </article>

      {/* Videos Section */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Videos</h2>

        {/* Videos Loading State */}
        {videosLoading && <LoadingState count={6} />}

        {/* Videos Error State */}
        {!videosLoading && videosError && (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-6 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-4">
              Could not load playlist videos.
            </p>
          </div>
        )}

        {/* Videos List */}
        {!videosLoading && !videosError && (
          <>
            {/* Empty State (CHK047) */}
            {videos.length === 0 && (
              <div
                className="bg-white border border-gray-200 rounded-xl p-8 text-center"
                role="status"
              >
                <div className="mx-auto w-16 h-16 mb-4 text-gray-400 bg-gray-100 rounded-full p-4">
                  <FilmIcon className="w-full h-full" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  No videos in this playlist
                </h3>
                <p className="text-gray-600">
                  This playlist doesn&apos;t contain any videos yet.
                </p>
              </div>
            )}

            {/* Video List */}
            {videos.length > 0 && (
              <div className="space-y-3">
                {videos.map((video) => (
                  <PlaylistVideoCard key={video.video_id} video={video} />
                ))}

                {/* Loading More Indicator */}
                {isFetchingNextPage && (
                  <div className="mt-4" aria-live="polite">
                    <p className="text-sm text-gray-500 text-center py-2">
                      Loading more videos...
                    </p>
                    <LoadingState count={3} />
                  </div>
                )}

                {/* Intersection Observer Trigger */}
                {hasNextPage && !videosError && (
                  <div
                    ref={loadMoreRef}
                    className="h-4 mt-4"
                    aria-hidden="true"
                  />
                )}

                {/* All Loaded Message */}
                {!hasNextPage && videos.length > 0 && (
                  <p className="text-sm text-gray-500 text-center py-4 mt-4 border-t border-gray-100">
                    All {video_count} {video_count === 1 ? "video" : "videos"}{" "}
                    loaded
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Bottom Back to Playlists Link (CHK008) */}
      <div className="mt-6">
        <Link
          to="/playlists"
          className="inline-flex items-center text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 mr-2" />
          Back to Playlists
        </Link>
      </div>
    </div>
  );
}
