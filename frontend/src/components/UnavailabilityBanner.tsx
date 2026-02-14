/**
 * UnavailabilityBanner component displays status-specific banners for unavailable videos and channels.
 *
 * Features:
 * - FR-012: Video unavailability banners with status-specific messaging
 * - FR-013: Channel unavailability banners with status-specific messaging
 * - FR-014: Alternative URL display when available
 * - FR-022: WCAG 2.1 Level AA accessibility (role="status", aria-live="polite", no color-only indication)
 * - NFR-003: Keyboard operable, visible focus indicators
 *
 * Accessibility:
 * - Uses role="status" and aria-live="polite" for screen reader announcements
 * - Does not rely on color alone (includes icons and text)
 * - Visible focus indicators on links
 * - Alternative URL is a properly labeled link
 */

interface UnavailabilityBannerProps {
  /** The availability_status value from the API */
  availabilityStatus: string;
  /** Whether this banner is for a video or channel */
  entityType: "video" | "channel";
  /** Optional alternative URL for deleted/unavailable videos */
  alternativeUrl?: string | null;
}

/**
 * Banner configuration for different availability statuses.
 */
interface BannerConfig {
  heading: string;
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
  colorClasses: {
    background: string;
    border: string;
    iconBackground: string;
    iconColor: string;
    headingColor: string;
    detailColor: string;
  };
}

/**
 * Lock/Shield icon for private status.
 */
function LockIcon({ className }: { className?: string }) {
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
        d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
      />
    </svg>
  );
}

/**
 * Trash/X icon for deleted status.
 */
function TrashIcon({ className }: { className?: string }) {
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
        d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
      />
    </svg>
  );
}

/**
 * Ban/Block icon for terminated status.
 */
function BanIcon({ className }: { className?: string }) {
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
        d="M18.364 18.364A9 9 0 0 0 5.636 5.636m12.728 12.728A9 9 0 0 1 5.636 5.636m12.728 12.728L5.636 5.636"
      />
    </svg>
  );
}

/**
 * Copyright/Alert icon for copyright status.
 */
function CopyrightIcon({ className }: { className?: string }) {
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
 * Alert/Warning icon for TOS violation status.
 */
function AlertIcon({ className }: { className?: string }) {
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
 * Question/Info icon for unavailable status.
 */
function QuestionIcon({ className }: { className?: string }) {
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
        d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z"
      />
    </svg>
  );
}

/**
 * External link icon for alternative URL.
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
 * Video banner configurations (FR-012).
 */
const VIDEO_BANNERS: Record<string, BannerConfig> = {
  private: {
    heading: "This video is private.",
    detail:
      "The uploader has made this video private. The metadata shown below was captured before the change.",
    icon: LockIcon,
    colorClasses: {
      background: "bg-amber-50",
      border: "border-amber-300",
      iconBackground: "bg-amber-100",
      iconColor: "text-amber-600",
      headingColor: "text-amber-900",
      detailColor: "text-amber-800",
    },
  },
  deleted: {
    heading: "This video was deleted.",
    detail:
      "This video was removed from YouTube. The metadata shown below was captured before deletion.",
    icon: TrashIcon,
    colorClasses: {
      background: "bg-red-50",
      border: "border-red-300",
      iconBackground: "bg-red-100",
      iconColor: "text-red-600",
      headingColor: "text-red-900",
      detailColor: "text-red-800",
    },
  },
  terminated: {
    heading: "This video is from a terminated channel.",
    detail:
      "The channel that published this video has been terminated. The metadata shown below was captured before termination.",
    icon: BanIcon,
    colorClasses: {
      background: "bg-red-50",
      border: "border-red-300",
      iconBackground: "bg-red-100",
      iconColor: "text-red-600",
      headingColor: "text-red-900",
      detailColor: "text-red-800",
    },
  },
  copyright: {
    heading: "This video was removed for copyright violation.",
    detail:
      "YouTube removed this video due to a copyright claim. The metadata shown below was captured before removal.",
    icon: CopyrightIcon,
    colorClasses: {
      background: "bg-orange-50",
      border: "border-orange-300",
      iconBackground: "bg-orange-100",
      iconColor: "text-orange-600",
      headingColor: "text-orange-900",
      detailColor: "text-orange-800",
    },
  },
  tos_violation: {
    heading: "This video was removed for violating YouTube's Terms of Service.",
    detail:
      "YouTube removed this video for a Terms of Service violation. The metadata shown below was captured before removal.",
    icon: AlertIcon,
    colorClasses: {
      background: "bg-orange-50",
      border: "border-orange-300",
      iconBackground: "bg-orange-100",
      iconColor: "text-orange-600",
      headingColor: "text-orange-900",
      detailColor: "text-orange-800",
    },
  },
  unavailable: {
    heading: "This video is currently unavailable.",
    detail:
      "This video cannot be accessed on YouTube. The reason is unknown. The metadata shown below was captured while the video was still available.",
    icon: QuestionIcon,
    colorClasses: {
      background: "bg-slate-50",
      border: "border-slate-300",
      iconBackground: "bg-slate-100",
      iconColor: "text-slate-600",
      headingColor: "text-slate-900",
      detailColor: "text-slate-700",
    },
  },
};

/**
 * Channel banner configurations (FR-013).
 */
const CHANNEL_BANNERS: Record<string, BannerConfig> = {
  private: {
    heading: "This channel is private.",
    detail:
      "This channel has been made private. The metadata shown below was captured before the change.",
    icon: LockIcon,
    colorClasses: {
      background: "bg-amber-50",
      border: "border-amber-300",
      iconBackground: "bg-amber-100",
      iconColor: "text-amber-600",
      headingColor: "text-amber-900",
      detailColor: "text-amber-800",
    },
  },
  deleted: {
    heading: "This channel was deleted.",
    detail:
      "This channel was removed from YouTube. The metadata shown below was captured before deletion.",
    icon: TrashIcon,
    colorClasses: {
      background: "bg-red-50",
      border: "border-red-300",
      iconBackground: "bg-red-100",
      iconColor: "text-red-600",
      headingColor: "text-red-900",
      detailColor: "text-red-800",
    },
  },
  terminated: {
    heading: "This channel has been terminated.",
    detail:
      "YouTube has terminated this channel. The metadata shown below was captured before termination.",
    icon: BanIcon,
    colorClasses: {
      background: "bg-red-50",
      border: "border-red-300",
      iconBackground: "bg-red-100",
      iconColor: "text-red-600",
      headingColor: "text-red-900",
      detailColor: "text-red-800",
    },
  },
  copyright: {
    heading: "This channel was removed for copyright violations.",
    detail:
      "YouTube removed this channel due to copyright claims. The metadata shown below was captured before removal.",
    icon: CopyrightIcon,
    colorClasses: {
      background: "bg-orange-50",
      border: "border-orange-300",
      iconBackground: "bg-orange-100",
      iconColor: "text-orange-600",
      headingColor: "text-orange-900",
      detailColor: "text-orange-800",
    },
  },
  tos_violation: {
    heading: "This channel was removed for violating YouTube's Terms of Service.",
    detail:
      "YouTube removed this channel for Terms of Service violations. The metadata shown below was captured before removal.",
    icon: AlertIcon,
    colorClasses: {
      background: "bg-orange-50",
      border: "border-orange-300",
      iconBackground: "bg-orange-100",
      iconColor: "text-orange-600",
      headingColor: "text-orange-900",
      detailColor: "text-orange-800",
    },
  },
  unavailable: {
    heading: "This channel is currently unavailable.",
    detail:
      "This channel cannot be accessed on YouTube. The reason is unknown. The metadata shown below was captured while the channel was still accessible.",
    icon: QuestionIcon,
    colorClasses: {
      background: "bg-slate-50",
      border: "border-slate-300",
      iconBackground: "bg-slate-100",
      iconColor: "text-slate-600",
      headingColor: "text-slate-900",
      detailColor: "text-slate-700",
    },
  },
};

/**
 * UnavailabilityBanner component.
 *
 * Displays a status-specific banner when content is unavailable.
 * Returns null when content is available (no banner needed).
 *
 * @param props - Component props
 * @returns Banner UI or null
 */
export function UnavailabilityBanner({
  availabilityStatus,
  entityType,
  alternativeUrl,
}: UnavailabilityBannerProps) {
  // No banner for available content
  if (availabilityStatus === "available") {
    return null;
  }

  // Select the appropriate banner configuration
  const banners = entityType === "video" ? VIDEO_BANNERS : CHANNEL_BANNERS;
  const config = banners[availabilityStatus];

  // Fallback to unavailable if status not recognized
  const bannerConfig = config ?? banners.unavailable;

  // Safety check (should never happen given fallback)
  if (!bannerConfig) {
    return null;
  }

  const Icon = bannerConfig.icon;
  const colors = bannerConfig.colorClasses;

  return (
    <div
      className={`${colors.background} border ${colors.border} rounded-xl shadow-md p-6 mb-6`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div
          className={`flex-shrink-0 w-12 h-12 ${colors.iconBackground} rounded-full p-2.5`}
        >
          <Icon className={`w-full h-full ${colors.iconColor}`} />
        </div>

        {/* Content */}
        <div className="flex-grow">
          {/* Heading */}
          <h2 className={`text-lg font-semibold ${colors.headingColor} mb-2`}>
            {bannerConfig.heading}
          </h2>

          {/* Detail */}
          <p className={`text-sm ${colors.detailColor} mb-0`}>
            {bannerConfig.detail}
          </p>

          {/* Alternative URL (FR-014) - videos only */}
          {entityType === "video" && alternativeUrl && (
            <div className="mt-4 pt-4 border-t border-current border-opacity-20">
              <a
                href={alternativeUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-2 text-sm font-medium ${colors.headingColor} hover:underline focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-current rounded transition-colors`}
              >
                <ExternalLinkIcon className="w-4 h-4" />
                This content may be available on an alternative platform
                <span className="sr-only">(opens in new tab)</span>
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
