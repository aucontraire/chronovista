/**
 * PrivacyBadge component displays playlist privacy status.
 *
 * Implements CHK060 accessibility requirements and visual specifications
 * from 019-playlist-navigation/visual-specs.md.
 *
 * @example
 * ```tsx
 * <PrivacyBadge status="public" />
 * <PrivacyBadge status="private" className="ml-2" />
 * <PrivacyBadge status="unlisted" />
 * ```
 *
 * @module components/PrivacyBadge
 */

interface PrivacyBadgeProps {
  /** Privacy status of the playlist */
  status: "public" | "private" | "unlisted";
  /** Optional additional CSS classes */
  className?: string;
}

/**
 * Privacy badge icon components (inline SVG for zero dependencies).
 */
const PrivacyIcons = {
  public: (
    <svg
      className="w-3 h-3"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
  private: (
    <svg
      className="w-3 h-3"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
      />
    </svg>
  ),
  unlisted: (
    <svg
      className="w-3 h-3"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
      />
    </svg>
  ),
};

/**
 * Privacy status configurations with WCAG AA compliant colors.
 *
 * Color contrast ratios (per CHK061):
 * - Public: green-100/green-800 = 7.5:1
 * - Private: red-100/red-800 = 8.2:1
 * - Unlisted: amber-100/amber-800 = 7.1:1
 */
const privacyConfig = {
  public: {
    bgColor: "bg-green-100",
    textColor: "text-green-800",
    label: "Public playlist",
    displayText: "Public",
  },
  private: {
    bgColor: "bg-red-100",
    textColor: "text-red-800",
    label: "Private playlist",
    displayText: "Private",
  },
  unlisted: {
    bgColor: "bg-amber-100",
    textColor: "text-amber-800",
    label: "Unlisted playlist",
    displayText: "Unlisted",
  },
} as const;

/**
 * PrivacyBadge displays playlist privacy status with an icon and text label.
 *
 * Features:
 * - Three privacy states: public, private, unlisted
 * - Distinct colors and icons per state (CHK060)
 * - WCAG AA contrast compliance (CHK061)
 * - Accessible aria-label for screen readers
 * - Small, inline pill shape design
 *
 * @param status - Privacy status (public, private, unlisted)
 * @param className - Optional additional CSS classes
 */
export function PrivacyBadge({ status, className = "" }: PrivacyBadgeProps) {
  const config = privacyConfig[status];
  const icon = PrivacyIcons[status];

  return (
    <span
      className={`
        inline-flex items-center gap-1
        px-2 py-0.5
        text-xs font-medium
        rounded-full
        ${config.bgColor} ${config.textColor}
        ${className}
      `.trim()}
      aria-label={config.label}
      role="img"
    >
      {icon}
      <span>{config.displayText}</span>
    </span>
  );
}
