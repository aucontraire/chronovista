/**
 * API client functions for the onboarding pipeline endpoints (Feature 047).
 *
 * Covers:
 * - GET /api/v1/onboarding/status — full pipeline state
 * - POST /api/v1/tasks — start a pipeline operation
 * - GET /api/v1/tasks/{task_id} — poll a specific task
 * - GET /api/v1/tasks — list all tasks (optional status filter)
 */

import { apiFetch } from "./config";
import type {
  BackgroundTask,
  OnboardingStatus,
  TaskCreate,
  TaskListResponse,
  TaskStatus,
} from "../types/onboarding";

// ---------------------------------------------------------------------------
// Onboarding status
// ---------------------------------------------------------------------------

/**
 * Fetches the current onboarding pipeline status, including step states,
 * aggregate data counts, and any active background task.
 *
 * @param signal - Optional AbortSignal for cancellation (FR-005)
 * @returns Full OnboardingStatus from the backend
 */
export async function fetchOnboardingStatus(
  signal?: AbortSignal
): Promise<OnboardingStatus> {
  return apiFetch<OnboardingStatus>("/onboarding/status", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

// ---------------------------------------------------------------------------
// Task management
// ---------------------------------------------------------------------------

/**
 * Starts a new pipeline operation as a background task.
 *
 * Returns 201 on success. The backend returns 409 if a task for the same
 * operation type is already running, and 422 if prerequisites are unmet.
 *
 * @param data - Request body specifying which operation to run
 * @returns The newly created BackgroundTask
 * @throws ApiError with status 409 if the operation is already running
 * @throws ApiError with status 422 if prerequisites are not satisfied
 */
export async function createTask(data: TaskCreate): Promise<BackgroundTask> {
  return apiFetch<BackgroundTask>("/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Fetches the current state of a specific background task by ID.
 *
 * Intended for polling — call repeatedly until status is "completed" or "failed".
 *
 * @param taskId - UUID of the task returned by createTask
 * @param signal - Optional AbortSignal for cancellation
 * @returns Current BackgroundTask snapshot
 * @throws ApiError with status 404 if the task ID does not exist
 */
export async function fetchTaskStatus(
  taskId: string,
  signal?: AbortSignal
): Promise<BackgroundTask> {
  return apiFetch<BackgroundTask>(`/tasks/${taskId}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

/**
 * Fetches all background tasks, with an optional status filter.
 *
 * @param status - Optional TaskStatus to filter results (e.g. "running")
 * @param signal - Optional AbortSignal for cancellation
 * @returns TaskListResponse containing the matching tasks
 */
export async function fetchTasks(
  status?: TaskStatus,
  signal?: AbortSignal
): Promise<TaskListResponse> {
  const qs = status !== undefined ? `?status=${status}` : "";
  return apiFetch<TaskListResponse>(`/tasks${qs}`, {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}
