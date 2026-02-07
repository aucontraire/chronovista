/**
 * ChannelCard component displays a single channel item in the list.
 */

import { Link } from "react-router-dom";

import { cardPatterns, colorTokens } from "../styles";
import type { ChannelListItem } from "../types/channel";

interface ChannelCardProps {
  /** Channel data to display */
  channel: ChannelListItem;
}

/**
 * Formats a number with K/M suffixes for readability.
 * Used for subscriber counts and video counts.
 */
function formatCount(count: number | null): string {
  if (count === null) {
    return "N/A";
  }

  // For large numbers, use K/M suffixes
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  }

  if (count >= 10000) {
    return `${(count / 1000).toFixed(1)}K`;
  }

  // For smaller numbers, add commas manually for consistent cross-environment behavior
  return count.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Placeholder image URL for channels without thumbnails.
 */
const PLACEHOLDER_THUMBNAIL = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='88' height='88' viewBox='0 0 88 88'%3E%3Crect fill='%23e2e8f0' width='88' height='88'/%3E%3Ctext x='50%25' y='50%25' font-family='system-ui' font-size='32' fill='%2394a3b8' text-anchor='middle' dy='0.35em'%3E?%3C/text%3E%3C/svg%3E";

/**
 * ChannelCard displays channel metadata in a card format.
 * Includes thumbnail, channel name, subscriber count, and video count (in database).
 */
export function ChannelCard({ channel }: ChannelCardProps) {
  const {
    channel_id,
    title,
    thumbnail_url,
    subscriber_count,
    video_count,
  } = channel;

  // Use placeholder if no thumbnail
  const displayThumbnail = thumbnail_url || PLACEHOLDER_THUMBNAIL;

  // Format video count with singular/plural
  const formattedVideoCount = formatCount(video_count);
  const videoCountText = video_count === 1 ? "1 video" : `${formattedVideoCount} videos`;

  // Format subscriber count
  const subscriberCountText = subscriber_count !== null
    ? `${formatCount(subscriber_count)} subscribers`
    : null;

  return (
    <Link
      to={`/channels/${channel_id}`}
      className="block no-underline text-inherit focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-xl"
      aria-label={`View channel ${title}, ${videoCountText}`}
    >
      <article
        className={`${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.transition} p-5`}
        role="article"
      >
        {/* Channel Thumbnail */}
        <div className="mb-4 flex justify-center">
          <img
            src={displayThumbnail}
            alt={title}
            className="w-22 h-22 rounded-full object-cover"
          />
        </div>

        {/* Channel Title */}
        <h3
          className={`text-lg font-semibold text-${colorTokens.text.primary} line-clamp-2 mb-2 text-center`}
          title={title}
        >
          {title}
        </h3>

        {/* Subscriber Count */}
        {subscriberCountText && (
          <p className={`text-sm text-${colorTokens.text.secondary} text-center mb-1`}>
            {subscriberCountText}
          </p>
        )}

        {/* Video Count */}
        <p className={`text-sm text-${colorTokens.text.tertiary} text-center`}>
          {videoCountText}
        </p>
      </article>
    </Link>
  );
}
