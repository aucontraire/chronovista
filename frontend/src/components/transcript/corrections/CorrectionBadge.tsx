/**
 * CorrectionBadge component for marking corrected transcript segments (Feature 035).
 *
 * Implements:
 * - FR-035-BADGE: Visual indicator for corrected segments
 * - NFR-008: Color is not the sole visual indicator (text label always visible — WCAG 1.4.1)
 * - NFR-A: aria-label for screen reader accessibility
 *
 * @module components/transcript/corrections/CorrectionBadge
 */

/**
 * Props for the CorrectionBadge component.
 */
export interface CorrectionBadgeProps {
  /** Whether this segment has an active correction */
  hasCorrection: boolean;
  /** Total number of corrections applied to this segment */
  correctionCount: number;
  /** ISO 8601 datetime of the most recent correction, or null if uncorrected */
  correctedAt: string | null;
}

/**
 * Formats an ISO 8601 datetime string into a human-readable date/time string.
 *
 * @param isoString - ISO 8601 datetime string
 * @returns Formatted string like "Jan 15, 2025 at 3:42 PM"
 */
function formatCorrectionDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return isoString;
  }
}

/**
 * CorrectionBadge renders a compact visual indicator on corrected transcript segments.
 *
 * When `hasCorrection` is false, renders nothing.
 * When `hasCorrection` is true, renders an amber "Corrected" badge.
 * When `correctionCount > 1`, the badge includes a tooltip showing the count and
 * the timestamp of the most recent correction.
 *
 * @example
 * ```tsx
 * <CorrectionBadge
 *   hasCorrection={segment.has_correction}
 *   correctionCount={segment.correction_count}
 *   correctedAt={segment.corrected_at}
 * />
 * ```
 */
export function CorrectionBadge({
  hasCorrection,
  correctionCount,
  correctedAt,
}: CorrectionBadgeProps) {
  if (!hasCorrection) {
    return null;
  }

  // Build tooltip text when there are multiple corrections (correctionCount > 1)
  const tooltipParts: string[] = [];
  if (correctionCount > 1) {
    tooltipParts.push(`Corrected ${correctionCount} times`);
    if (correctedAt !== null) {
      tooltipParts.push(`Last corrected: ${formatCorrectionDate(correctedAt)}`);
    }
  }
  const tooltipText = tooltipParts.length > 0 ? tooltipParts.join(" · ") : undefined;

  return (
    <span
      className="inline-flex items-center bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-1.5 py-0.5 rounded flex-shrink-0"
      aria-label="Corrected segment"
      title={tooltipText}
    >
      Corrected
    </span>
  );
}
