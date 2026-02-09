/**
 * PlaylistTypeBadge Component
 *
 * Displays a badge indicating whether a playlist is YouTube-linked or local-only.
 * Implements visual specifications from 019-playlist-navigation/visual-specs.md.
 *
 * Features:
 * - YouTube-linked: Red background with "YT" indicator
 * - Local: Blue/slate background with "Local" indicator
 * - Consistent pill shape with PrivacyBadge styling
 * - WCAG 2.1 AA compliant contrast ratios (8.6:1 for YouTube, 12.6:1 for Local)
 * - Screen reader accessible with aria-label
 *
 * @see visual-specs.md (CHK060, CHK061): ARIA labels and color contrast requirements
 *
 * @example
 * ```tsx
 * // YouTube-linked playlist
 * <PlaylistTypeBadge isLinked={true} />
 *
 * // Local-only playlist
 * <PlaylistTypeBadge isLinked={false} />
 *
 * // With custom styling
 * <PlaylistTypeBadge isLinked={true} className="ml-2" />
 * ```
 */

interface PlaylistTypeBadgeProps {
  /** Whether the playlist is linked to YouTube (true) or local-only (false) */
  isLinked: boolean;
  /** Optional additional CSS classes */
  className?: string;
}

/**
 * Badge component for playlist type indication.
 *
 * Displays either "YT" for YouTube-linked playlists or "Local" for local-only playlists.
 * Uses color-coded backgrounds that meet WCAG AA contrast requirements.
 */
export function PlaylistTypeBadge({
  isLinked,
  className = "",
}: PlaylistTypeBadgeProps) {
  // YouTube-linked styling: blue-100 background, blue-800 text (8.6:1 contrast)
  // Local styling: gray-100 background, gray-800 text (12.6:1 contrast)
  const badgeClasses = isLinked
    ? "bg-blue-100 text-blue-800"
    : "bg-gray-100 text-gray-800";

  const label = isLinked ? "YT" : "Local";
  const ariaLabel = isLinked
    ? "Type: YouTube-linked playlist"
    : "Type: Local only playlist";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${badgeClasses} ${className}`}
      aria-label={ariaLabel}
      role="img"
    >
      {label}
    </span>
  );
}
