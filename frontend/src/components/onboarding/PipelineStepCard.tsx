/**
 * PipelineStepCard Component
 *
 * Renders a single data onboarding pipeline step as a card with status badge,
 * metrics display, action button, dependency explanation, auth badge, and
 * inline error display. Integrates with ProgressBar for running tasks.
 *
 * Accessibility:
 * - Action buttons have descriptive aria-labels
 * - Disabled buttons carry aria-disabled for screen readers
 * - Status badges are aria-label annotated
 * - Error regions use role="alert"
 * - Auth badge uses role="status"
 */

import type { BackgroundTask, OperationType, PipelineStep } from "../../types/onboarding";
import { ProgressBar } from "./ProgressBar";

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface PipelineStepCardProps {
  /** The pipeline step data to render. */
  step: PipelineStep;
  /**
   * Currently running background task for this step (matched by operation_type),
   * or null when no task is active for this step.
   */
  activeTask: BackgroundTask | null;
  /** Whether the user is authenticated with YouTube OAuth. */
  isAuthenticated: boolean;
  /** Called when the user clicks "Start" for an available step. */
  onStart: (operationType: OperationType) => void;
  /** Called when the user clicks "Retry" after a failed step. */
  onRetry: (operationType: OperationType) => void;
}

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

/** Returns Tailwind classes for the status badge background and text. */
function statusBadgeClasses(status: PipelineStep["status"]): string {
  switch (status) {
    case "not_started":
      return "bg-slate-100 text-slate-600 border-slate-200";
    case "available":
      return "bg-blue-100 text-blue-700 border-blue-200";
    case "running":
      return "bg-amber-100 text-amber-700 border-amber-200";
    case "completed":
      return "bg-green-100 text-green-700 border-green-200";
    case "blocked":
      return "bg-red-50 text-red-600 border-red-200";
    default: {
      // Exhaustive check — this branch should never be reached
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

/** Human-readable label for a step status. */
function statusLabel(status: PipelineStep["status"]): string {
  switch (status) {
    case "not_started":
      return "Not started";
    case "available":
      return "Available";
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "blocked":
      return "Blocked";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

// ---------------------------------------------------------------------------
// Metrics display
// ---------------------------------------------------------------------------

/**
 * Formats a metric value for display (adds thousands separators for numbers).
 */
function formatMetricValue(value: number | string): string {
  if (typeof value === "number") {
    return value.toLocaleString();
  }
  return value;
}

interface MetricsDisplayProps {
  metrics: Record<string, number | string>;
}

/**
 * Renders key/value metric pairs in a compact inline list.
 * Only rendered when the step is completed and metrics are non-empty.
 */
function MetricsDisplay({ metrics }: MetricsDisplayProps) {
  const entries = Object.entries(metrics);
  if (entries.length === 0) return null;

  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-1">
          <dt className="text-xs text-slate-500 capitalize">
            {key.replace(/_/g, " ")}:
          </dt>
          <dd className="text-xs font-semibold text-slate-700 tabular-nums">
            {formatMetricValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// Action button
// ---------------------------------------------------------------------------

interface ActionButtonProps {
  step: PipelineStep;
  isAuthenticated: boolean;
  onStart: (operationType: OperationType) => void;
  onRetry: (operationType: OperationType) => void;
}

/**
 * Renders the appropriate action button for a pipeline step based on its
 * current status and auth requirements.
 *
 * Button states:
 * - available: "Start" (enabled)
 * - running: "Running…" (disabled, no action)
 * - completed + error: "Retry" (enabled)
 * - blocked / not_started / auth-gated: button disabled with explanation
 */
function ActionButton({
  step,
  isAuthenticated,
  onStart,
  onRetry,
}: ActionButtonProps) {
  const authBlocked = step.requires_auth && !isAuthenticated;

  if (step.status === "running") {
    return (
      <button
        type="button"
        disabled
        aria-disabled="true"
        aria-label={`${step.name} is currently running`}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-amber-100 text-amber-700 border border-amber-200 cursor-not-allowed"
      >
        {/* Spinner */}
        <svg
          className="w-4 h-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
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
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Running…
      </button>
    );
  }

  if (step.status === "completed" && step.error !== null) {
    return (
      <button
        type="button"
        onClick={() => onRetry(step.operation_type)}
        aria-label={`Retry ${step.name}`}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 transition-colors"
      >
        Retry
      </button>
    );
  }

  if (step.status === "available" && !authBlocked) {
    return (
      <button
        type="button"
        onClick={() => onStart(step.operation_type)}
        aria-label={`Start ${step.name}`}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
      >
        Start
      </button>
    );
  }

  // Blocked, not_started, or auth-blocked — render a disabled button
  const disabledLabel =
    authBlocked
      ? `${step.name} requires authentication`
      : step.status === "blocked"
      ? `${step.name} is blocked by incomplete dependencies`
      : `${step.name} is not yet available`;

  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      aria-label={disabledLabel}
      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
    >
      Start
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * PipelineStepCard renders one step of the data onboarding pipeline with:
 * - Step name and description
 * - Color-coded status badge (with pulse animation when running)
 * - Completed metrics
 * - Auth-required badge when OAuth is needed but not present
 * - Dependency explanation when blocked
 * - Inline error message when an error is recorded
 * - ProgressBar when running and an active task exists
 * - Action button (Start / Running… / Retry / disabled)
 *
 * @example
 * ```tsx
 * <PipelineStepCard
 *   step={pipelineStep}
 *   activeTask={activeTask}
 *   isAuthenticated={status.is_authenticated}
 *   onStart={(opType) => startMutation.mutate({ operation_type: opType })}
 *   onRetry={(opType) => startMutation.mutate({ operation_type: opType })}
 * />
 * ```
 */
export function PipelineStepCard({
  step,
  activeTask,
  isAuthenticated,
  onStart,
  onRetry,
}: PipelineStepCardProps) {
  const isRunning = step.status === "running";
  const isCompleted = step.status === "completed";
  const isBlocked = step.status === "blocked";
  const authRequired = step.requires_auth && !isAuthenticated;
  const taskProgress = activeTask?.progress ?? 0;

  return (
    <article
      aria-label={`Pipeline step: ${step.name}`}
      className="bg-white rounded-xl border border-slate-200 shadow-sm p-5"
    >
      {/* Header row: step name + status badge */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="text-base font-semibold text-slate-900 leading-snug">
          {step.name}
        </h3>

        {/* Status badge */}
        <span
          aria-label={`Status: ${statusLabel(step.status)}`}
          className={[
            "inline-flex items-center gap-1.5 shrink-0 px-2.5 py-0.5 rounded-full text-xs font-medium border",
            statusBadgeClasses(step.status),
          ].join(" ")}
        >
          {/* Pulse dot for running state */}
          {isRunning && (
            <span
              className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"
              aria-hidden="true"
            />
          )}
          {statusLabel(step.status)}
        </span>
      </div>

      {/* Description */}
      <p className="text-sm text-slate-600 mb-3 leading-relaxed">
        {step.description}
      </p>

      {/* Auth required badge */}
      {authRequired && (
        <div
          role="status"
          aria-label="Authentication required for this step"
          className="inline-flex items-center gap-1.5 mb-3 px-2.5 py-1 rounded-md bg-orange-50 border border-orange-200 text-xs font-medium text-orange-700"
        >
          {/* Lock icon */}
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          Requires Authentication
        </div>
      )}

      {/* Dependency explanation (blocked state only) */}
      {isBlocked && step.dependencies.length > 0 && (
        <p className="text-xs text-slate-500 mb-3 italic">
          Requires completion of:{" "}
          <span className="font-medium text-slate-600">
            {step.dependencies
              .map((dep) => dep.replace(/_/g, " "))
              .join(", ")}
          </span>
        </p>
      )}

      {/* Completed metrics */}
      {isCompleted && Object.keys(step.metrics).length > 0 && (
        <MetricsDisplay metrics={step.metrics} />
      )}

      {/* Progress bar (running + active task) */}
      {isRunning && activeTask !== null && (
        <div className="mt-3" aria-label={`${step.name} progress`}>
          <ProgressBar progress={taskProgress} />
        </div>
      )}

      {/* Inline error display */}
      {step.error !== null && (
        <div
          role="alert"
          aria-label={`Error in ${step.name}`}
          className="mt-3 flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200"
        >
          <svg
            className="w-4 h-4 text-red-500 shrink-0 mt-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
          <p className="text-xs text-red-700 leading-relaxed">{step.error}</p>
        </div>
      )}

      {/* Action button — right-aligned */}
      <div className="mt-4 flex justify-end">
        <ActionButton
          step={step}
          isAuthenticated={isAuthenticated}
          onStart={onStart}
          onRetry={onRetry}
        />
      </div>
    </article>
  );
}
