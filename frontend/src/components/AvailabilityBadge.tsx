/**
 * AvailabilityBadge component displays status indicator for unavailable content.
 *
 * Feature 023 (Deleted Content Visibility) - FR-021.
 *
 * Visual design:
 * - Small badge positioned inline or in corner
 * - Status-specific colors (red for deleted, amber for private, etc.)
 * - WCAG AA compliant contrast ratios
 *
 * @example
 * ```tsx
 * <AvailabilityBadge status="deleted" />
 * <AvailabilityBadge status="private" />
 * ```
 */

import { getStatusBadgeConfig } from "../utils/availability";

interface AvailabilityBadgeProps {
  /** Video availability status */
  status: string;
  /** Optional additional CSS classes */
  className?: string;
}

/**
 * AvailabilityBadge shows a small status indicator for unavailable videos.
 * Returns null if the video is available (no badge needed).
 */
export function AvailabilityBadge({
  status,
  className = "",
}: AvailabilityBadgeProps) {
  const badgeConfig = getStatusBadgeConfig(status);

  // No badge for available content
  if (!badgeConfig) {
    return null;
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badgeConfig.bgColor} ${badgeConfig.textColor} ${className}`}
      aria-label={badgeConfig.ariaLabel}
    >
      {badgeConfig.label}
    </span>
  );
}
