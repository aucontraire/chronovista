/**
 * UnavailabilityBanner component displays status-specific banners for unavailable videos and channels.
 *
 * Features:
 * - FR-012: Video unavailability banners with status-specific messaging
 * - FR-013: Channel unavailability banners with status-specific messaging
 * - FR-014: Alternative URL display when available
 * - FR-022: WCAG 2.1 Level AA accessibility (role="status", aria-live="polite", no color-only indication)
 * - NFR-003: Keyboard operable, visible focus indicators
 * - Feature 025: Web Archive recovery with status feedback
 * - T034: Elapsed time counter during recovery
 * - T041: Cancel button for active recovery operations
 *
 * Accessibility:
 * - Uses role="status" and aria-live="polite" for screen reader announcements
 * - Does not rely on color alone (includes icons and text)
 * - Visible focus indicators on links
 * - Alternative URL is a properly labeled link
 * - Elapsed timer uses aria-live for screen reader updates
 */

import { useState, useEffect } from "react";
import { useRecoveryStore } from "../stores/recoveryStore";

interface UnavailabilityBannerProps {
  /** The availability_status value from the API */
  availabilityStatus: string;
  /** Whether this banner is for a video or channel */
  entityType: "video" | "channel";
  /** Optional alternative URL for deleted/unavailable videos */
  alternativeUrl?: string | null;
  /** Entity ID (video_id or channel_id) for recovery operations */
  entityId?: string;
  /** Callback to trigger recovery operation */
  onRecover?: (options?: { startYear?: number; endYear?: number }) => void;
  /** Timestamp of previous recovery (ISO 8601) */
  recoveredAt?: string | null;
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
 * Archive box icon for recovery button.
 */
function ArchiveBoxIcon({ className }: { className?: string }) {
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
        d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z"
      />
    </svg>
  );
}

/**
 * Spinner icon for loading state.
 */
function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

/**
 * Check circle icon for success state.
 */
function CheckCircleIcon({ className }: { className?: string }) {
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
        d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
      />
    </svg>
  );
}

/**
 * Information circle icon for informational state.
 */
function InformationCircleIcon({ className }: { className?: string }) {
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
        d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zm-9-3.75h.008v.008H12V8.25z"
      />
    </svg>
  );
}

/**
 * X circle icon for error state.
 */
function XCircleIcon({ className }: { className?: string }) {
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
        d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
      />
    </svg>
  );
}

/**
 * Chevron right icon for collapsed state.
 */
function ChevronRightIcon({ className }: { className?: string }) {
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
        d="m8.25 4.5 7.5 7.5-7.5 7.5"
      />
    </svg>
  );
}

/**
 * Chevron down icon for expanded state.
 */
function ChevronDownIcon({ className }: { className?: string }) {
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
        d="m19.5 8.25-7.5 7.5-7.5-7.5"
      />
    </svg>
  );
}

/**
 * Formats a Wayback Machine timestamp (YYYYMMDDHHMMSS) to human-readable date (YYYY-MM-DD).
 * @param timestamp - Wayback timestamp string
 * @returns Formatted date string or the original timestamp if parsing fails
 */
function formatSnapshotTimestamp(timestamp: string): string {
  if (!timestamp || timestamp.length < 8) {
    return timestamp;
  }

  const year = timestamp.substring(0, 4);
  const month = timestamp.substring(4, 6);
  const day = timestamp.substring(6, 8);

  return `${year}-${month}-${day}`;
}

/**
 * Formats a previous recovery timestamp (ISO 8601) to human-readable date.
 * @param isoTimestamp - ISO 8601 datetime string
 * @returns Formatted date string
 */
function formatRecoveredDate(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Formats elapsed time in milliseconds to human-readable string.
 * @param ms - Elapsed milliseconds
 * @returns Formatted time string (e.g., "1m 23s", "45s")
 */
function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
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
  entityId,
  onRecover,
  recoveredAt,
}: UnavailabilityBannerProps) {
  // Get recovery session from store
  const session = useRecoveryStore((s) => s.getActiveSession(entityId ?? ""));
  const cancelRecovery = useRecoveryStore((s) => s.cancelRecovery);

  // Derive isRecovering and recoveryResult from store session
  const isRecovering = session?.phase === "pending" || session?.phase === "in-progress";
  const recoveryResult = session?.result ?? null;

  // State for advanced options
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [startYear, setStartYear] = useState("");
  const [endYear, setEndYear] = useState(String(new Date().getFullYear()));

  // State for cancel note (T041)
  const [showCancelNote, setShowCancelNote] = useState(false);

  // State for elapsed time counter - forces re-render every second (T034)
  const [, setElapsedTick] = useState(0);

  // Elapsed timer effect (T034)
  useEffect(() => {
    if (session?.phase === "in-progress" && session.startedAt) {
      // Update every second to trigger re-render
      const intervalId = setInterval(() => {
        setElapsedTick((prev) => prev + 1);
      }, 1000);

      return () => clearInterval(intervalId);
    }
  }, [session?.phase, session?.startedAt]);

  // Handle cancel button click (T041)
  const handleCancel = () => {
    if (session?.sessionId) {
      cancelRecovery(session.sessionId);
      setShowCancelNote(true);
      // Auto-hide cancel note after 8 seconds
      setTimeout(() => setShowCancelNote(false), 8000);
    }
  };

  // Year range constants
  const YEAR_MIN = 2005;
  const YEAR_MAX = new Date().getFullYear();
  const yearOptions = Array.from(
    { length: YEAR_MAX - YEAR_MIN + 1 },
    (_, i) => YEAR_MIN + i
  );

  // Validate year range
  const yearValidationError =
    startYear && endYear && Number(endYear) < Number(startYear)
      ? "End year must be after start year"
      : null;

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

  // Determine recovery button text
  const recoveryButtonText = recoveredAt
    ? "Re-recover from Web Archive"
    : "Recover from Web Archive";

  // Determine recovery status message
  let recoveryStatusElement: React.ReactNode = null;

  if (isRecovering) {
    const elapsedMs = session?.startedAt ? Date.now() - session.startedAt : 0;
    recoveryStatusElement = (
      <div className="space-y-3">
        {/* Progress indicator with elapsed timer (T034) */}
        <div className="flex items-center gap-2 text-sm text-slate-700">
          <SpinnerIcon className="w-5 h-5 animate-spin" />
          <span aria-live="polite" aria-atomic="true">
            Recovering from Web Archive... ({formatElapsed(elapsedMs)} elapsed)
          </span>
        </div>

        {/* Help text */}
        <p className="text-xs text-slate-600">
          This can take 1–5 minutes depending on archive availability.
        </p>

        {/* Cancel button (T041) */}
        <button
          type="button"
          onClick={handleCancel}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 transition-colors"
        >
          Cancel
        </button>

        {/* Cancel note (T041) */}
        {showCancelNote && (
          <p className="text-xs text-slate-600 italic">
            Recovery cancelled. The server may still complete the operation in the background.
          </p>
        )}
      </div>
    );
  } else if (recoveryResult) {
    if (recoveryResult.success) {
      if (recoveryResult.fields_recovered.length > 0) {
        // Green success message
        const snapshotDate = recoveryResult.snapshot_used
          ? formatSnapshotTimestamp(recoveryResult.snapshot_used)
          : "unknown date";
        recoveryStatusElement = (
          <div className="flex items-start gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-3">
            <CheckCircleIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>
              Recovered {recoveryResult.fields_recovered.length} field
              {recoveryResult.fields_recovered.length !== 1 ? "s" : ""} from
              archive snapshot {snapshotDate}
            </span>
          </div>
        );
      } else {
        // Blue informational message
        recoveryStatusElement = (
          <div className="flex items-start gap-2 text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded-lg p-3">
            <InformationCircleIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>Recovery completed. All fields already up-to-date.</span>
          </div>
        );
      }
    } else {
      // Failure message with contextual text
      let failureMessage = "Recovery failed.";
      if (recoveryResult.failure_reason === "no_snapshots_found") {
        failureMessage = "No archived snapshots found for this content.";
      } else if (recoveryResult.failure_reason === "all_snapshots_failed") {
        failureMessage =
          "Could not extract metadata from available snapshots.";
      } else if (recoveryResult.failure_reason === "cdx_connection_error") {
        failureMessage =
          "Web Archive is temporarily unavailable. Please try again later.";
      } else if (recoveryResult.failure_reason) {
        failureMessage = `Recovery failed: ${recoveryResult.failure_reason}`;
      }

      recoveryStatusElement = (
        <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
          <XCircleIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{failureMessage}</span>
        </div>
      );
    }
  }

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

          {/* Recovery Section (Feature 025) */}
          {entityId && onRecover && (
            <div className="mt-4 pt-4 border-t border-current border-opacity-20">
              {/* Recovery Button */}
              <button
                type="button"
                onClick={() => {
                  const options: { startYear?: number; endYear?: number } = {};
                  if (startYear) options.startYear = Number(startYear);
                  if (endYear) options.endYear = Number(endYear);
                  onRecover(Object.keys(options).length > 0 ? options : undefined);
                }}
                disabled={isRecovering || !!yearValidationError}
                className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-700 rounded-lg hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 disabled:bg-slate-400 disabled:cursor-not-allowed transition-colors ${colors.headingColor}`}
              >
                <ArchiveBoxIcon className="w-4 h-4" />
                {recoveryButtonText}
                {recoveredAt && (
                  <span className="text-xs opacity-90">
                    (last: {formatRecoveredDate(recoveredAt)})
                  </span>
                )}
              </button>

              {/* Advanced Options Toggle */}
              <div className="mt-3">
                <button
                  type="button"
                  onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
                  aria-expanded={showAdvancedOptions}
                  aria-controls="recovery-advanced-options"
                  className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 rounded transition-colors"
                >
                  {showAdvancedOptions ? (
                    <ChevronDownIcon className="w-4 h-4" />
                  ) : (
                    <ChevronRightIcon className="w-4 h-4" />
                  )}
                  Advanced Options
                </button>

                {/* Advanced Options Panel */}
                {showAdvancedOptions && (
                  <div
                    id="recovery-advanced-options"
                    role="region"
                    aria-label="Year range filter"
                    className="mt-3 p-4 bg-slate-50 rounded-lg border border-slate-200"
                  >
                    {/* Year Range Selects */}
                    <div className="flex flex-col sm:flex-row gap-4 mb-3">
                      <div className="flex-1">
                        <label
                          htmlFor="start-year"
                          className="block text-sm font-medium text-slate-700 mb-1"
                        >
                          From:
                        </label>
                        <select
                          id="start-year"
                          value={startYear}
                          onChange={(e) => setStartYear(e.target.value)}
                          className="block w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-500 focus:border-slate-500 text-sm"
                        >
                          <option value="">Any year</option>
                          {yearOptions.map((year) => (
                            <option key={year} value={year}>
                              {year}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="flex-1">
                        <label
                          htmlFor="end-year"
                          className="block text-sm font-medium text-slate-700 mb-1"
                        >
                          To:
                        </label>
                        <select
                          id="end-year"
                          value={endYear}
                          onChange={(e) => setEndYear(e.target.value)}
                          className="block w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-500 focus:border-slate-500 text-sm"
                        >
                          <option value="">Any year</option>
                          {yearOptions.map((year) => (
                            <option key={year} value={year}>
                              {year}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {/* Help Text */}
                    <p className="text-xs text-slate-500 mb-0">
                      Default searches all years (newest first). Narrow the
                      range if you know when the content was created.
                    </p>

                    {/* Validation Error */}
                    {yearValidationError && (
                      <p
                        role="alert"
                        className="text-sm text-red-600 mt-2 mb-0"
                      >
                        {yearValidationError}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Recovery Status (aria-live region) */}
              {recoveryStatusElement && (
                <div className="mt-3" aria-live="polite" aria-atomic="true">
                  {recoveryStatusElement}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
