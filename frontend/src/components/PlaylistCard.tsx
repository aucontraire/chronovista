/**
 * PlaylistCard component displays a single playlist item in the grid.
 *
 * Features:
 * - Displays playlist title (truncated with line-clamp-2)
 * - Shows video count
 * - Privacy status badge (public/private/unlisted)
 * - Playlist type badge (YT/Local)
 * - Clickable card linking to playlist detail page
 * - Accessible with keyboard navigation support
 * - Hover effects following design system
 *
 * @example
 * ```tsx
 * <PlaylistCard playlist={playlistItem} />
 * ```
 */

import { Link } from "react-router-dom";

import { cardPatterns, colorTokens } from "../styles";
import type { PlaylistListItem } from "../types/playlist";
import { PlaylistTypeBadge } from "./PlaylistTypeBadge";
import { PrivacyBadge } from "./PrivacyBadge";

interface PlaylistCardProps {
  /** Playlist data to display */
  playlist: PlaylistListItem;
}

/**
 * Formats video count with proper singular/plural handling.
 */
function formatVideoCount(count: number): string {
  if (count === 0) {
    return "No videos";
  }

  if (count === 1) {
    return "1 video";
  }

  return `${count.toLocaleString()} videos`;
}

/**
 * PlaylistCard displays playlist metadata in a card format.
 * Includes title, video count, privacy badge, and type badge.
 * Follows the established card pattern from ChannelCard and VideoCard.
 */
export function PlaylistCard({ playlist }: PlaylistCardProps) {
  const {
    playlist_id,
    title,
    video_count,
    privacy_status,
    is_linked,
  } = playlist;

  const videoCountText = formatVideoCount(video_count);

  return (
    <Link
      to={`/playlists/${playlist_id}`}
      className="block no-underline text-inherit focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-xl"
      aria-label={`View playlist ${title}, ${videoCountText}`}
    >
      <article
        className={`${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.transition} p-6`}
        role="article"
      >
        {/* Playlist Title */}
        <h3
          className={`text-lg font-semibold text-${colorTokens.text.primary} line-clamp-2 mb-3`}
          title={title}
        >
          {title}
        </h3>

        {/* Video Count */}
        <p className={`text-sm text-${colorTokens.text.secondary} mb-3`}>
          {videoCountText}
        </p>

        {/* Badges Row */}
        <div className="flex items-center gap-2 flex-wrap">
          <PrivacyBadge status={privacy_status} />
          <PlaylistTypeBadge isLinked={is_linked} />
        </div>
      </article>
    </Link>
  );
}

/**
 * PlaylistCardSkeleton displays a loading placeholder for PlaylistCard.
 * Matches the dimensions and structure of the actual card.
 *
 * @example
 * ```tsx
 * <PlaylistCardSkeleton />
 * ```
 */
export function PlaylistCardSkeleton() {
  return (
    <div
      className={`${cardPatterns.base} p-6 animate-pulse`}
      role="status"
      aria-label="Loading playlist"
    >
      {/* Title placeholder - two lines matching line-clamp-2 */}
      <div className="h-5 bg-gray-200 rounded w-3/4 mb-2" />
      <div className="h-5 bg-gray-200 rounded w-1/2 mb-3" />

      {/* Video count placeholder */}
      <div className="h-4 bg-gray-200 rounded w-1/4 mb-3" />

      {/* Badges placeholder */}
      <div className="flex items-center gap-2">
        <div className="h-5 bg-gray-200 rounded-full w-16" />
        <div className="h-5 bg-gray-200 rounded-full w-12" />
      </div>
    </div>
  );
}
