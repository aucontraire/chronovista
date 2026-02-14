/**
 * Availability status utilities for unavailable content indicators.
 * Supports Feature 023 (Deleted Content Visibility) - FR-021.
 *
 * @module utils/availability
 */

/**
 * Availability status badge configuration.
 * Maps availability_status values to display properties.
 */
interface StatusBadgeConfig {
  /** Display text for the badge */
  label: string;
  /** Tailwind CSS background color class */
  bgColor: string;
  /** Tailwind CSS text color class */
  textColor: string;
  /** Accessible description for screen readers */
  ariaLabel: string;
}

/**
 * Maps availability status to badge configuration.
 * Colors follow WCAG AA guidelines for contrast.
 *
 * @param status - Video availability status from API
 * @returns Badge configuration or null if content is available
 */
export function getStatusBadgeConfig(
  status: string
): StatusBadgeConfig | null {
  switch (status) {
    case "available":
      return null; // No badge for available content

    case "private":
      return {
        label: "Private",
        bgColor: "bg-amber-100",
        textColor: "text-amber-800",
        ariaLabel: "This video is now private",
      };

    case "deleted":
      return {
        label: "Deleted",
        bgColor: "bg-red-100",
        textColor: "text-red-800",
        ariaLabel: "This video has been deleted",
      };

    case "terminated":
      return {
        label: "Terminated",
        bgColor: "bg-red-100",
        textColor: "text-red-800",
        ariaLabel: "This channel has been terminated",
      };

    case "copyright":
      return {
        label: "Copyright",
        bgColor: "bg-orange-100",
        textColor: "text-orange-800",
        ariaLabel: "This video was removed for copyright violation",
      };

    case "tos_violation":
      return {
        label: "TOS Violation",
        bgColor: "bg-orange-100",
        textColor: "text-orange-800",
        ariaLabel: "This video was removed for Terms of Service violation",
      };

    case "unavailable":
    default:
      return {
        label: "Unavailable",
        bgColor: "bg-gray-100",
        textColor: "text-gray-800",
        ariaLabel: "This video is unavailable",
      };
  }
}

/**
 * Checks if a video is unavailable based on availability_status.
 *
 * @param status - Video availability status from API
 * @returns true if video is unavailable, false otherwise
 */
export function isVideoUnavailable(status: string): boolean {
  return status !== "available";
}
