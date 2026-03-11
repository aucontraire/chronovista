/**
 * VideoMetaHeader Component
 *
 * Displays a compact video metadata row: a clickable title deep link, the
 * channel name, and the segment start time formatted as a timestamp badge.
 *
 * Used across batch correction preview cards, search results, and any future
 * surface that needs a lightweight video context header.
 *
 * Navigation uses React Router's `<Link>` so that transitions stay
 * client-side without a full page reload.
 *
 * @see T015 in batch corrections spec
 */

import { Link } from "react-router-dom";
import { formatTimestamp } from "../../utils/formatTimestamp";

export interface VideoMetaHeaderProps {
  /** YouTube video ID */
  videoId: string;
  /** Video title text */
  videoTitle: string;
  /** Channel name */
  channelTitle: string;
  /** Segment start time in seconds (may be fractional) */
  startTime: number;
  /** Deep link URL (e.g., /videos/abc?lang=en&seg=123&t=45) */
  deepLinkUrl: string;
  /** Optional className for the outermost container */
  className?: string;
}

/**
 * Renders a single-line video metadata header with a title link, channel
 * name, and timestamp. Suitable for embedding inside cards or list items
 * where vertical space is at a premium.
 *
 * @example
 * ```tsx
 * <VideoMetaHeader
 *   videoId="dQw4w9WgXcQ"
 *   videoTitle="Never Gonna Give You Up"
 *   channelTitle="Rick Astley"
 *   startTime={43}
 *   deepLinkUrl="/videos/dQw4w9WgXcQ?lang=en&seg=7&t=43"
 * />
 * ```
 */
export function VideoMetaHeader({
  videoId: _videoId,
  videoTitle,
  channelTitle,
  startTime,
  deepLinkUrl,
  className,
}: VideoMetaHeaderProps) {
  const formattedTime = formatTimestamp(startTime);

  return (
    <div
      className={`flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 min-w-0 ${className ?? ""}`}
    >
      {/* Video title — deep link to video page at the correct segment */}
      <h3 className="text-sm font-semibold text-gray-900 line-clamp-1 min-w-0 flex-shrink">
        <Link
          to={deepLinkUrl}
          className="text-blue-700 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
        >
          {videoTitle}
        </Link>
      </h3>

      {/* Separator */}
      <span aria-hidden="true" className="text-gray-300 shrink-0 select-none">
        ·
      </span>

      {/* Channel name */}
      <span className="text-sm text-gray-500 line-clamp-1 min-w-0 shrink">
        {channelTitle}
      </span>

      {/* Separator */}
      <span aria-hidden="true" className="text-gray-300 shrink-0 select-none">
        ·
      </span>

      {/* Timestamp badge — links to the same deep link so it's also clickable.
          min-h/min-w meets WCAG 2.5.8 44×44 px touch target for standalone links. */}
      <Link
        to={deepLinkUrl}
        aria-label={`Jump to ${formattedTime} in video`}
        className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-2 text-xs font-mono font-medium text-gray-600 bg-gray-100 rounded hover:bg-blue-50 hover:text-blue-700 transition-colors shrink-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
      >
        {formattedTime}
      </Link>
    </div>
  );
}
