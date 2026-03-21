/**
 * VideoEmbed component — renders an embedded YouTube player or a static
 * thumbnail fallback when the video is unavailable or the player fails to load.
 *
 * Implements:
 * - FR-007: YouTube IFrame embed when video is available and has a transcript
 * - FR-009/NFR-003: Privacy-enhanced mode via youtube-nocookie.com (handled by hook)
 * - FR-010a: Pre-render availability check — static thumbnail for unavailable videos
 * - FR-010b: Runtime player error fallback to static thumbnail
 * - FR-012: Watch history disclosure note below the player
 * - FR-018/FR-019: 16:9 aspect ratio with 400px minimum column width, 200x200px minimum
 *
 * @module components/video/VideoEmbed
 */

import type { RefObject } from "react";
import type { PlayerError } from "../../hooks/useYouTubePlayer";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * YouTube error codes that should trigger the static thumbnail fallback.
 * Code -1 is the internal API load timeout sentinel set by useYouTubePlayer.
 */
const FALLBACK_TRIGGER_CODES = new Set([2, 5, 100, 101, 150, -1]);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Props for the VideoEmbed component.
 */
export interface VideoEmbedProps {
  /** 11-character YouTube video ID. */
  videoId: string;
  /**
   * Content availability status from the backend API.
   * When not "available", the component renders a static thumbnail instead of
   * an embed (FR-010a pre-render check).
   */
  availabilityStatus: string;
  /**
   * Ref for the container div that the YouTube IFrame API will replace.
   * Must be created by useYouTubePlayer in the parent (VideoDetailPage) and
   * passed down here so the hook and the DOM element are co-located correctly.
   */
  containerRef: RefObject<HTMLDivElement | null>;
  /**
   * Player error from useYouTubePlayer, or null when there is no error.
   * Drives the FR-010b runtime fallback to static thumbnail.
   */
  playerError: PlayerError | null;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Renders a "Watch on YouTube" link styled as a pill button.
 * Used in both the unavailability fallback and the runtime error fallback.
 */
function WatchOnYouTubeLink({ videoId }: { videoId: string }) {
  return (
    <a
      href={`https://www.youtube.com/watch?v=${videoId}`}
      target="_blank"
      rel="noopener noreferrer"
      className="
        inline-flex items-center gap-1.5
        mt-3 px-4 py-2
        bg-red-600 text-white text-sm font-medium
        rounded-lg
        hover:bg-red-700
        focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2
        transition-colors
      "
    >
      {/* YouTube play icon */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path d="M19.615 3.184C16.011 2.938 7.984 2.938 4.38 3.184 0.488 3.45 0.029 5.804 0 12c.029 6.185.484 8.549 4.38 8.816 3.604.247 11.631.247 15.235 0C23.512 20.55 23.971 18.196 24 12c-.029-6.185-.484-8.549-4.385-8.816zM9.75 15.75v-7.5L17.25 12l-7.5 3.75z" />
      </svg>
      Watch on YouTube
      <span className="sr-only">(opens in new tab)</span>
    </a>
  );
}

/**
 * Static thumbnail image with an optional overlay message and "Watch on
 * YouTube" link. Used as the fallback when the video is unavailable or the
 * player encounters a fatal error.
 */
function ThumbnailFallback({
  videoId,
  message,
}: {
  videoId: string;
  message?: string;
}) {
  const thumbnailUrl = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

  return (
    <div className="flex flex-col items-center">
      {/* Aspect-ratio container — keeps the thumbnail at 16:9 */}
      <div className="relative w-full aspect-video bg-slate-100 rounded-lg overflow-hidden">
        <img
          src={thumbnailUrl}
          alt={`Thumbnail for YouTube video ${videoId}`}
          className="w-full h-full object-cover"
          /**
           * YouTube thumbnail URLs always resolve (they return a placeholder
           * when the video is deleted), so we do not need an onError handler
           * here. The underlying image may itself be a "video unavailable"
           * placeholder served by YouTube.
           */
        />

        {/* Dark overlay + message when the caller provides one */}
        {message && (
          <div
            className="
              absolute inset-0
              flex flex-col items-center justify-center
              bg-black/60
              p-4 text-center
            "
            role="status"
            aria-live="polite"
          >
            <p className="text-white text-sm font-medium">{message}</p>
          </div>
        )}
      </div>

      <WatchOnYouTubeLink videoId={videoId} />
    </div>
  );
}

/**
 * Privacy and watch history disclosure note displayed below the player.
 * Satisfies FR-012 with three required content points.
 */
function WatchHistoryDisclosure() {
  return (
    <p
      className="mt-3 text-sm text-gray-500 leading-relaxed"
      aria-label="Watch history and privacy disclosure"
    >
      Playing this video may add it to your YouTube watch history.{" "}
      This embed uses privacy-enhanced mode (youtube-nocookie.com).{" "}
      Use an incognito window if you prefer not to affect your watch history.
    </p>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * VideoEmbed renders an interactive YouTube IFrame player when the video is
 * available, otherwise it falls back to a static thumbnail.
 *
 * Player state (containerRef, playerError) is supplied by the parent via
 * useYouTubePlayer so that seekTo/activeSegmentId/followPlayback can be
 * wired to TranscriptPanel at the VideoDetailPage level (Feature 048).
 *
 * @example
 * ```tsx
 * const { containerRef, error, seekTo, ... } = useYouTubePlayer({ videoId, segments });
 *
 * <VideoEmbed
 *   videoId="dQw4w9WgXcQ"
 *   availabilityStatus="available"
 *   containerRef={containerRef}
 *   playerError={error}
 * />
 * ```
 */
export function VideoEmbed({
  videoId,
  availabilityStatus,
  containerRef,
  playerError,
}: VideoEmbedProps) {
  // FR-010a: Pre-render availability check.
  // If the video is not "available", skip the player entirely and show a
  // static thumbnail with a "Watch on YouTube" link.
  if (availabilityStatus !== "available") {
    return (
      // min-w-[400px]: FR-018 minimum column width
      // The outer wrapper prevents the card from collapsing below 200px
      // in either dimension (FR-019 YouTube ToS minimum size).
      <section
        aria-label="Video embed"
        className="min-w-[400px] min-h-[200px] w-full"
      >
        <ThumbnailFallback
          videoId={videoId}
          message="This video is not currently available."
        />
      </section>
    );
  }

  // For available videos, render the player shell with the externally-managed
  // containerRef. VideoEmbedInner no longer calls useYouTubePlayer; the hook
  // lives in VideoDetailPage so its state can be shared with TranscriptPanel.
  return (
    <VideoEmbedInner
      videoId={videoId}
      containerRef={containerRef}
      playerError={playerError}
    />
  );
}

// ---------------------------------------------------------------------------
// Inner component (always rendered for available videos)
// ---------------------------------------------------------------------------

/**
 * Inner player component that renders the YouTube player div shell.
 * Receives containerRef and playerError from the parent instead of calling
 * useYouTubePlayer directly — the hook now lives in VideoDetailPage so its
 * state (seekTo, activeSegmentId, followPlayback) can be shared with
 * TranscriptPanel (Feature 048).
 */
function VideoEmbedInner({
  videoId,
  containerRef,
  playerError,
}: {
  videoId: string;
  containerRef: RefObject<HTMLDivElement | null>;
  playerError: PlayerError | null;
}) {
  // FR-010b: Runtime player error — fall back to static thumbnail.
  // Also covers the API load timeout (code -1 from the hook).
  const hasPlayerError =
    playerError !== null && FALLBACK_TRIGGER_CODES.has(playerError.code);

  const isScriptLoadTimeout = playerError?.code === -1;

  if (hasPlayerError) {
    const message = isScriptLoadTimeout
      ? "Video player could not be loaded."
      : (playerError?.message ?? "The video could not be played.");

    return (
      <section
        aria-label="Video embed"
        className="min-w-[400px] min-h-[200px] w-full"
      >
        <ThumbnailFallback videoId={videoId} message={message} />
      </section>
    );
  }

  return (
    <section
      aria-label="Video embed"
      className="min-w-[400px] min-h-[200px] w-full"
    >
      {/*
       * aspect-video: Tailwind utility that enforces 16:9 ratio (FR-018).
       * The YT.Player constructor replaces this div with an <iframe>;
       * the iframe inherits the container's dimensions.
       * bg-slate-900 provides a dark loading state before the iframe appears.
       * rounded-lg + overflow-hidden keeps the player within the card boundary.
       */}
      <div className="aspect-video w-full bg-slate-900 rounded-lg overflow-hidden">
        <div
          ref={containerRef}
          className="w-full h-full"
          /**
           * aria-label gives screen readers context before the iframe is
           * injected by the YouTube IFrame API.
           */
          aria-label="YouTube video player"
        />
      </div>

      {/* FR-012: Watch history disclosure note */}
      <WatchHistoryDisclosure />
    </section>
  );
}
