/**
 * ProgressBar Component
 *
 * Presentational progress bar for the data onboarding pipeline UI (Feature 047).
 *
 * Renders a horizontal bar with a filled blue portion proportional to `progress`,
 * plus a percentage label. Suitable for displaying BackgroundTask.progress values
 * (0–100) returned by GET /api/v1/tasks/{id}.
 *
 * Accessibility:
 * - Outer track element carries role="progressbar" with aria-valuenow/min/max
 * - Percentage label is aria-hidden to avoid redundant announcements
 * - The component is purely presentational — callers supply an accessible label
 *   via aria-label or aria-labelledby on the parent container
 */

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface ProgressBarProps {
  /**
   * Current progress value, between 0 and 100 (inclusive).
   * Values outside this range are clamped automatically.
   */
  progress: number;
  /** Optional additional Tailwind classes for the outer wrapper element. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * ProgressBar renders a horizontal progress indicator with a filled region
 * and a percentage label.
 *
 * Uses `transition-[width]` for smooth animated width changes as `progress`
 * updates during task polling. The fill color uses `bg-blue-600` to match
 * the project's semantic info color (#2563EB from tailwind.config.ts).
 *
 * @example
 * ```tsx
 * // Inside a task card:
 * <ProgressBar progress={task.progress} className="mt-2" />
 *
 * // At completion:
 * <ProgressBar progress={100} />
 *
 * // Not yet started:
 * <ProgressBar progress={0} />
 * ```
 */
export function ProgressBar({ progress, className }: ProgressBarProps) {
  // Clamp to [0, 100] so callers don't need to guard against out-of-range values
  const clamped = Math.min(100, Math.max(0, progress));
  const rounded = Math.round(clamped);

  return (
    <div className={['flex items-center gap-3', className].filter(Boolean).join(' ')}>
      {/* Track */}
      <div
        role="progressbar"
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
        className="flex-1 h-2.5 rounded-full bg-slate-200 overflow-hidden"
      >
        {/* Fill */}
        <div
          className="h-full rounded-full bg-blue-600 transition-[width] duration-300 ease-in-out"
          style={{ width: `${clamped}%` }}
        />
      </div>

      {/* Percentage label — decorative, screen readers read aria-valuenow */}
      <span
        aria-hidden="true"
        className="w-10 text-right text-sm font-medium tabular-nums text-slate-600 shrink-0"
      >
        {rounded}%
      </span>
    </div>
  );
}
