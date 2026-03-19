/**
 * Onboarding domain types for the data onboarding pipeline UI (Feature 047).
 * These types match the backend Pydantic schemas in:
 *   src/chronovista/api/schemas/onboarding.py
 *   src/chronovista/api/schemas/tasks.py
 *   src/chronovista/models/enums.py (OperationType, TaskStatus, PipelineStepStatus)
 */

// ---------------------------------------------------------------------------
// Enums — match backend OperationType, TaskStatus, PipelineStepStatus
// ---------------------------------------------------------------------------

/**
 * Pipeline operation types that can be triggered as background tasks.
 * Matches backend OperationType enum values.
 */
export type OperationType =
  | "seed_reference"
  | "load_data"
  | "enrich_metadata"
  | "sync_transcripts"
  | "normalize_tags";

/**
 * Lifecycle status of a background task.
 * Matches backend TaskStatus enum values.
 */
export type TaskStatus = "queued" | "running" | "completed" | "failed";

/**
 * Status of a pipeline step in the onboarding flow.
 * Matches backend PipelineStepStatus enum values.
 */
export type PipelineStepStatus =
  | "not_started"
  | "available"
  | "running"
  | "completed"
  | "blocked";

// ---------------------------------------------------------------------------
// Onboarding schemas — match src/chronovista/api/schemas/onboarding.py
// ---------------------------------------------------------------------------

/** Aggregate record counts displayed on the onboarding page. */
export interface OnboardingCounts {
  channels: number;
  videos: number;
  playlists: number;
  transcripts: number;
  categories: number;
  canonical_tags: number;
}

/** A single step in the data onboarding pipeline. */
export interface PipelineStep {
  name: string;
  operation_type: OperationType;
  description: string;
  status: PipelineStepStatus;
  /** Operation types that must complete before this step becomes available. */
  dependencies: OperationType[];
  requires_auth: boolean;
  /** Key/value metrics reported after the step completes (e.g. rows loaded). */
  metrics: Record<string, number | string>;
  error: string | null;
}

/** Complete onboarding pipeline state returned by GET /api/v1/onboarding/status. */
export interface OnboardingStatus {
  steps: PipelineStep[];
  is_authenticated: boolean;
  /** Filesystem path where the user's data export is expected. */
  data_export_path: string;
  /** True when a data export archive was detected at data_export_path. */
  data_export_detected: boolean;
  /** Currently running task, or null when no task is active. */
  active_task: BackgroundTask | null;
  counts: OnboardingCounts;
}

// ---------------------------------------------------------------------------
// Task schemas — match src/chronovista/api/schemas/tasks.py
// ---------------------------------------------------------------------------

/** Request body for POST /api/v1/tasks to start a pipeline operation. */
export interface TaskCreate {
  operation_type: OperationType;
}

/** A background task tracked by the in-memory TaskManager. */
export interface BackgroundTask {
  id: string;
  operation_type: OperationType;
  status: TaskStatus;
  /** Progress percentage (0.0–100.0). */
  progress: number;
  error: string | null;
  /** ISO 8601 datetime string, or null if the task has not started yet. */
  started_at: string | null;
  /** ISO 8601 datetime string, or null if the task has not finished. */
  completed_at: string | null;
}

/** Response envelope for GET /api/v1/tasks. */
export interface TaskListResponse {
  tasks: BackgroundTask[];
}
