/**
 * ChannelDetailPage displays detailed information about a specific channel.
 */

import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { VideoGrid } from "../components/VideoGrid";
import { LoadingState } from "../components/LoadingState";
import { useChannelDetail, useChannelVideos } from "../hooks";
import { cardPatterns, colorTokens } from "../styles";
import type { ApiError } from "../types/video";

/**
 * Formats a number with K/M suffixes for readability.
 */
function formatCount(count: number | null): string {
  if (count === null) {
    return "";
  }

  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  }

  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }

  return count.toString();
}

/**
 * ChannelDetailPage component.
 *
 * Displays:
 * - Channel header with thumbnail, name, description
 * - Channel metadata (subscriber count, video count from YouTube, country)
 * - Subscription status badge
 * - Videos from the channel with infinite scroll
 *
 * Handles:
 * - Loading states with skeletons
 * - 404 errors with custom UI
 * - General errors with retry option
 * - Missing metadata gracefully
 * - Empty state when channel has no videos
 */
export function ChannelDetailPage() {
  const { channelId } = useParams<{ channelId: string }>();
  const navigate = useNavigate();
  const mainRef = useRef<HTMLElement>(null);

  const {
    data: channel,
    isLoading: channelLoading,
    isError: channelError,
    error: channelErrorObj,
    refetch: channelRefetch,
  } = useChannelDetail(channelId);

  const {
    videos,
    total: videosTotal,
    loadedCount,
    isLoading: videosLoading,
    isError: videosError,
    error: videosErrorObj,
    hasNextPage,
    isFetchingNextPage,
    retry: videosRetry,
    loadMoreRef,
  } = useChannelVideos(channelId);

  // Focus management on page load (FR-018)
  useEffect(() => {
    if (mainRef.current && !channelLoading) {
      mainRef.current.focus();
    }
  }, [channelLoading]);

  // Update document title with channel name
  useEffect(() => {
    if (channel?.title) {
      document.title = `${channel.title} - ChronoVista`;
    } else {
      document.title = "Channel Details - ChronoVista";
    }

    // Cleanup: reset to default on unmount
    return () => {
      document.title = "ChronoVista";
    };
  }, [channel?.title]);

  // Loading state
  if (channelLoading) {
    return (
      <main className="container mx-auto px-4 py-8" ref={mainRef} tabIndex={-1}>
        <LoadingState count={3} />
      </main>
    );
  }

  // 404 error state (EC-005)
  if (channelError && (channelErrorObj as ApiError)?.status === 404) {
    return (
      <main className="container mx-auto px-4 py-8" ref={mainRef} tabIndex={-1}>
        <div className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center">
          {/* 404 Icon */}
          <div className="mx-auto w-20 h-20 mb-6 text-gray-400 bg-gray-100 rounded-full p-4">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15.182 16.318A4.486 4.486 0 0 0 12.016 15a4.486 4.486 0 0 0-3.198 1.318M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z"
              />
            </svg>
          </div>

          {/* Heading */}
          <h1 className="text-2xl font-bold text-gray-900 mb-3">
            Channel Not Found
          </h1>

          {/* Description */}
          <p className="text-gray-600 mb-8 max-w-md mx-auto">
            This channel doesn&apos;t exist or has been removed.
          </p>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/channels"
              className="inline-flex items-center justify-center px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-all duration-200"
            >
              Browse Channels
            </Link>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="inline-flex items-center justify-center px-6 py-3 bg-white text-gray-700 font-semibold rounded-lg shadow-md border border-gray-300 hover:bg-gray-50 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-all duration-200"
            >
              Go Back
            </button>
          </div>
        </div>
      </main>
    );
  }

  // General error state (FR-019)
  if (channelError) {
    return (
      <main className="container mx-auto px-4 py-8" ref={mainRef} tabIndex={-1}>
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Channel Details</h1>
        <div
          className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center"
          role="alert"
          aria-live="polite"
        >
          {/* Error Icon */}
          <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
              />
            </svg>
          </div>

          {/* Error Title */}
          <p className="text-sm font-semibold text-red-800 uppercase tracking-wider mb-2">
            Could not load channel
          </p>

          {/* Error Message */}
          <p className="text-red-700 mb-8 max-w-md mx-auto">
            {typeof channelErrorObj === "object" && channelErrorObj !== null && "message" in channelErrorObj
              ? (channelErrorObj as { message: string }).message
              : "An error occurred while loading the channel"}
          </p>

          {/* Retry Button */}
          <button
            type="button"
            onClick={channelRefetch}
            className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-5 h-5 mr-2"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
              />
            </svg>
            Retry
          </button>
        </div>
      </main>
    );
  }

  // Channel not found (shouldn't happen with proper error handling, but for safety)
  if (!channel) {
    return (
      <main className="container mx-auto px-4 py-8" ref={mainRef} tabIndex={-1}>
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Channel Details</h1>
        <p className="text-gray-600">Channel not found.</p>
      </main>
    );
  }

  // Success state - render channel details
  const {
    title,
    description,
    thumbnail_url,
    subscriber_count,
    video_count,
    country,
    is_subscribed,
  } = channel;

  return (
    <main className="container mx-auto px-4 py-8" ref={mainRef} tabIndex={-1}>
      {/* Breadcrumb Navigation */}
      <nav className="mb-6" aria-label="Breadcrumb">
        <Link
          to="/channels"
          className={`text-${colorTokens.text.secondary} hover:text-${colorTokens.text.primary} transition-colors`}
        >
          ← Back to Channels
        </Link>
      </nav>

      {/* Channel Header */}
      <div className={`${cardPatterns.base} p-8 mb-8`}>
        <div className="flex flex-col md:flex-row gap-6 items-start">
          {/* Channel Thumbnail (EC-001) */}
          <div className="flex-shrink-0">
            {thumbnail_url ? (
              <img
                src={thumbnail_url}
                alt={`${title} channel thumbnail`}
                className="w-32 h-32 rounded-full object-cover"
              />
            ) : (
              <div
                className="w-32 h-32 rounded-full bg-gray-200 flex items-center justify-center"
                role="img"
                aria-label={`${title} channel thumbnail`}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-16 h-16 text-gray-400"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z"
                  />
                </svg>
              </div>
            )}
          </div>

          {/* Channel Info */}
          <div className="flex-grow">
            {/* Channel Name and Subscription Status */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-3">
              <h1 className={`text-3xl font-bold text-${colorTokens.text.primary}`}>
                {title}
              </h1>

              {/* Subscription Badge (FR-008) */}
              <span
                className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                  is_subscribed
                    ? `bg-${colorTokens.status.success.bg} text-${colorTokens.status.success.text}`
                    : `bg-gray-100 text-gray-700`
                }`}
              >
                {is_subscribed ? "Subscribed" : "Not Subscribed"}
              </span>
            </div>

            {/* Channel Description (EC-002) */}
            <p className={`text-${colorTokens.text.secondary} mb-4 whitespace-pre-wrap`}>
              {description || "No description available"}
            </p>

            {/* Channel Metadata (FR-007, EC-004) */}
            <div className={`flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-${colorTokens.text.tertiary}`}>
              {subscriber_count !== null && (
                <span className="flex items-center gap-1">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className="w-5 h-5"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z"
                    />
                  </svg>
                  {formatCount(subscriber_count)} subscribers
                </span>
              )}

              {video_count !== null && (
                <span className="flex items-center gap-1">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className="w-5 h-5"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
                    />
                  </svg>
                  {formatCount(video_count)} videos
                </span>
              )}

              {country && (
                <span className="flex items-center gap-1">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className="w-5 h-5"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
                    />
                  </svg>
                  {country}
                </span>
              )}
            </div>

            {/* View on YouTube Link */}
            <div className="mt-4">
              <a
                href={`https://www.youtube.com/channel/${channel.channel_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-2 text-${colorTokens.text.secondary} hover:text-${colorTokens.text.primary} transition-colors`}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-5 h-5"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                  />
                </svg>
                View on YouTube
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Videos Section */}
      <div>
        <h2 className={`text-2xl font-bold text-${colorTokens.text.primary} mb-6`}>
          Videos
        </h2>

        {/* Videos Loading State */}
        {videosLoading && <LoadingState count={6} />}

        {/* Videos Error State (EC-008) */}
        {!videosLoading && videosError && (
          <div
            className={`bg-${colorTokens.status.error.bg} border border-${colorTokens.status.error.border} rounded-lg p-6 text-center`}
            role="alert"
          >
            <p className={`text-${colorTokens.status.error.text} font-medium mb-4`}>
              Could not load videos:{" "}
              {typeof videosErrorObj === "object" && videosErrorObj !== null && "message" in videosErrorObj
                ? (videosErrorObj as { message: string }).message
                : "An error occurred"}
            </p>
            <button
              type="button"
              onClick={videosRetry}
              className={`inline-flex items-center px-4 py-2 bg-${colorTokens.status.error.text} text-white font-medium rounded-md hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-${colorTokens.status.error.text} focus:ring-offset-2 transition-opacity`}
            >
              Retry
            </button>
          </div>
        )}

        {/* Videos List */}
        {!videosLoading && !videosError && (
          <>
            {/* Empty State (EC-003) */}
            {videos.length === 0 && (
              <div
                className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center"
                role="status"
              >
                <div className="mx-auto w-20 h-20 mb-6 text-gray-400 bg-gray-100 rounded-full p-4">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
                    />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">
                  No videos yet
                </h3>
                <p className="text-gray-600 max-w-md mx-auto">
                  This channel doesn&apos;t have any videos in your database yet.
                </p>
              </div>
            )}

            {/* Video Grid */}
            {videos.length > 0 && (
              <div>
                <VideoGrid videos={videos} />

                {/* Loading More Indicator */}
                {isFetchingNextPage && (
                  <div className="mt-8" aria-live="polite">
                    <p className={`text-sm text-${colorTokens.text.tertiary} text-center py-2`}>
                      Loading more videos...
                    </p>
                    <LoadingState count={3} />
                  </div>
                )}

                {/* Intersection Observer Trigger */}
                {hasNextPage && !videosError && (
                  <div
                    ref={loadMoreRef}
                    className="h-4 mt-8"
                    aria-hidden="true"
                  />
                )}

                {/* All Loaded Message */}
                {!hasNextPage && videosTotal !== null && videosTotal > 0 && (
                  <p className={`text-sm text-${colorTokens.text.tertiary} text-center py-4 mt-8 border-t border-${colorTokens.border}`}>
                    All {videosTotal} video{videosTotal !== 1 ? "s" : ""} loaded ({loadedCount} displayed)
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
