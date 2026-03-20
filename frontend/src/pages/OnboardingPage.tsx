/**
 * OnboardingPage
 *
 * Data onboarding pipeline page for Feature 047 (Docker Onboarding UI).
 *
 * Displays:
 * - Page header "Data Onboarding"
 * - Data export path and detection guidance
 * - Connection error banner (when the API is unreachable) with retry
 * - Five PipelineStepCard components (one per operation type)
 * - Active task progress via useTaskStatus() polling
 *
 * State:
 * - activeTaskId: tracked locally; set when a task is started, cleared on completion/failure
 *
 * Accessibility:
 * - <main> landmark with tabIndex={-1} for skip-link focus
 * - Connection error banner uses role="alert"
 * - Data export guidance uses role="status"
 */

import { useEffect, useState } from "react";

import { PipelineStepCard } from "../components/onboarding/PipelineStepCard";
import { SkipLink } from "../components/SkipLink";
import {
  useOnboardingStatus,
  useStartTask,
  useTaskStatus,
} from "../hooks/useOnboarding";
import type { BackgroundTask, OperationType } from "../types/onboarding";

/** Stable ID for SkipLink target. */
const MAIN_CONTENT_ID = "onboarding-main-content";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Banner shown when the onboarding status query fails (API unreachable).
 */
interface ConnectionErrorBannerProps {
  onRetry: () => void;
}

function ConnectionErrorBanner({ onRetry }: ConnectionErrorBannerProps) {
  return (
    <div
      role="alert"
      aria-label="Unable to connect to the server"
      className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
    >
      <div className="flex items-center gap-3">
        {/* Warning icon */}
        <svg
          className="w-5 h-5 text-red-500 shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
          />
        </svg>
        <p className="text-sm font-medium text-red-800">
          Unable to connect to the server. Make sure the API is running.
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        aria-label="Retry connection to the server"
        className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-red-600 text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
      >
        {/* Refresh icon */}
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
            d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
          />
        </svg>
        Retry Connection
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data export path display
// ---------------------------------------------------------------------------

interface DataExportPathProps {
  dataExportPath: string;
  dataExportDetected: boolean;
}

/**
 * Shows the configured data export path and a guidance message when no export
 * archive has been detected there yet.
 */
function DataExportPath({
  dataExportPath,
  dataExportDetected,
}: DataExportPathProps) {
  return (
    <div
      role="status"
      aria-label={
        dataExportDetected
          ? "Data export detected"
          : "No data export detected"
      }
      className={[
        "mb-6 rounded-lg border p-4",
        dataExportDetected
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        {dataExportDetected ? (
          <svg
            className="w-5 h-5 text-green-600 shrink-0 mt-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        ) : (
          <svg
            className="w-5 h-5 text-amber-600 shrink-0 mt-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z"
            />
          </svg>
        )}

        <div className="flex-1 min-w-0">
          <p
            className={[
              "text-sm font-medium mb-1",
              dataExportDetected ? "text-green-800" : "text-amber-800",
            ].join(" ")}
          >
            {dataExportDetected
              ? "Data export detected"
              : "No data export found"}
          </p>

          <p
            className={[
              "text-xs mb-1",
              dataExportDetected ? "text-green-700" : "text-amber-700",
            ].join(" ")}
          >
            Expected path:{" "}
            <code className="font-mono bg-white/60 px-1 py-0.5 rounded">
              {dataExportPath}
            </code>
          </p>

          {!dataExportDetected && (
            <p className="text-xs text-amber-700 mt-1">
              Download your YouTube data export from{" "}
              <a
                href="https://takeout.google.com"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-amber-900 focus:outline-none focus:ring-1 focus:ring-amber-500 rounded"
              >
                Google Takeout
              </a>{" "}
              and place the archive at the path above, then refresh this page.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function StepCardSkeleton() {
  return (
    <div
      className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 animate-pulse"
      aria-hidden="true"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="h-4 bg-slate-200 rounded w-1/3" />
        <div className="h-5 bg-slate-100 rounded-full w-20" />
      </div>
      {/* Description lines */}
      <div className="space-y-2 mb-4">
        <div className="h-3 bg-slate-100 rounded w-full" />
        <div className="h-3 bg-slate-100 rounded w-4/5" />
      </div>
      {/* Button placeholder */}
      <div className="flex justify-end">
        <div className="h-8 bg-slate-100 rounded-lg w-16" />
      </div>
    </div>
  );
}

function PipelineLoadingState() {
  return (
    <div
      role="status"
      aria-label="Loading onboarding pipeline"
      aria-live="polite"
      aria-busy="true"
      className="space-y-4"
    >
      {Array.from({ length: 5 }, (_, i) => (
        <StepCardSkeleton key={i} />
      ))}
      <span className="sr-only">Loading onboarding pipeline…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

/**
 * OnboardingPage is the main data onboarding UI (Feature 047, US2).
 *
 * It fetches the pipeline status, renders five PipelineStepCard components,
 * tracks the active task with real-time polling, and shows a connection error
 * banner when the API is unreachable.
 */
export function OnboardingPage() {
  // Pipeline status query (includes polling while a task is active)
  const {
    data: status,
    isLoading,
    isError,
    refetch,
  } = useOnboardingStatus();

  // Local state: the ID of the task that was started in this session
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  // Start task mutation
  const startTask = useStartTask();

  // Poll the active task while it runs
  const { data: activeTaskPoll } = useTaskStatus(activeTaskId);

  // Auto-populate activeTaskId from backend status when not set locally.
  // This handles page refresh and connection drop/recovery — if the backend
  // reports an active_task but the local state is null (e.g. the user reloaded
  // the page mid-run), we pick it up so polling and progress display resume.
  useEffect(() => {
    if (status?.active_task && activeTaskId === null) {
      setActiveTaskId(status.active_task.id);
    }
  }, [status?.active_task, activeTaskId]);

  // Clear activeTaskId when the polled task reaches a terminal state
  useEffect(() => {
    if (
      activeTaskPoll?.status === "completed" ||
      activeTaskPoll?.status === "failed"
    ) {
      setActiveTaskId(null);
    }
  }, [activeTaskPoll?.status]);

  // Set page title
  useEffect(() => {
    document.title = "Data Onboarding - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Handlers
  const handleStart = (operationType: OperationType) => {
    startTask.mutate(
      { operation_type: operationType },
      {
        onSuccess: (task) => {
          setActiveTaskId(task.id);
        },
      }
    );
  };

  const handleRetry = (operationType: OperationType) => {
    startTask.mutate(
      { operation_type: operationType },
      {
        onSuccess: (task) => {
          setActiveTaskId(task.id);
        },
      }
    );
  };

  /**
   * Resolves which BackgroundTask is "active" for a given step.
   * Prefers the locally polled task; falls back to status.active_task if it
   * matches the step's operation_type.
   */
  const getActiveTaskForStep = (
    operationType: OperationType
  ): BackgroundTask | null => {
    // Prefer the polled task if it matches this step
    if (
      activeTaskPoll !== undefined &&
      activeTaskPoll.operation_type === operationType
    ) {
      return activeTaskPoll;
    }
    // Fall back to the status's active_task
    if (status?.active_task?.operation_type === operationType) {
      return status.active_task;
    }
    return null;
  };

  return (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8 max-w-3xl"
      >
        {/* Page header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-slate-900 mb-1">
            Data Onboarding
          </h1>
          <p className="text-sm text-slate-500">
            Run each pipeline step to import and enrich your YouTube data.
          </p>
        </div>

        {/* Connection error banner */}
        {isError && (
          <ConnectionErrorBanner onRetry={() => void refetch()} />
        )}

        {/* Data export path (only when status is available) */}
        {status !== undefined && (
          <DataExportPath
            dataExportPath={status.data_export_path}
            dataExportDetected={status.data_export_detected}
          />
        )}

        {/* Pipeline steps */}
        {isLoading && !status ? (
          <PipelineLoadingState />
        ) : status !== undefined ? (
          <div className="space-y-4">
            {status.steps.map((step) => (
              <PipelineStepCard
                key={step.operation_type}
                step={step}
                activeTask={getActiveTaskForStep(step.operation_type)}
                isAuthenticated={status.is_authenticated}
                onStart={handleStart}
                onRetry={handleRetry}
              />
            ))}
          </div>
        ) : null}

        {/* Start task mutation error (e.g. 409 conflict) */}
        {startTask.isError && (
          <div
            role="alert"
            aria-label="Failed to start task"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
          >
            <p className="text-sm text-red-800">
              Failed to start the operation:{" "}
              {startTask.error?.message ?? "Unknown error"}
            </p>
          </div>
        )}
      </main>
    </>
  );
}
