/**
 * TanStack Query v5 hooks for the data onboarding pipeline (Feature 047).
 *
 * Exports:
 * - useOnboardingStatus() — fetches pipeline status with conditional polling
 * - useStartTask() — mutation to create a background task
 * - useTaskStatus(taskId) — polls a specific task with conditional polling and
 *   onboarding-status invalidation when the task finishes
 *
 * @module hooks/useOnboarding
 */

import { useEffect, useRef } from "react";
import {
  useMutation,
  UseMutationResult,
  useQuery,
  UseQueryResult,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createTask,
  fetchOnboardingStatus,
  fetchTaskStatus,
} from "../api/onboarding";
import type {
  BackgroundTask,
  OnboardingStatus,
  TaskCreate,
} from "../types/onboarding";

// ---------------------------------------------------------------------------
// Query key constants
// ---------------------------------------------------------------------------

/** Stable query key for the onboarding pipeline status. */
export const ONBOARDING_STATUS_KEY = ["onboarding", "status"] as const;

/** Stable query key factory for a specific background task. */
export const taskStatusKey = (taskId: string | null) =>
  ["tasks", taskId] as const;

// ---------------------------------------------------------------------------
// useOnboardingStatus
// ---------------------------------------------------------------------------

/**
 * Hook that fetches the full onboarding pipeline status.
 *
 * Polling behaviour:
 * - No polling interval — status updates are driven by explicit invalidation
 *   from useTaskStatus when a task reaches a terminal state.
 * - staleTime of 10 s prevents redundant background refetches between events.
 *
 * @returns Standard TanStack Query UseQueryResult for OnboardingStatus
 *
 * @example
 * ```tsx
 * const { data, isLoading, isError } = useOnboardingStatus();
 * const steps = data?.steps ?? [];
 * ```
 */
export function useOnboardingStatus(): UseQueryResult<OnboardingStatus, Error> {
  return useQuery<OnboardingStatus, Error>({
    queryKey: ONBOARDING_STATUS_KEY,
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ signal }) => fetchOnboardingStatus(signal),
    // No refetchInterval — status updates are driven by invalidation from
    // useTaskStatus when a task finishes.  This avoids polling storms.
    staleTime: 10 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: 2,
  });
}

// ---------------------------------------------------------------------------
// useStartTask
// ---------------------------------------------------------------------------

/**
 * Hook for creating a new background pipeline task.
 *
 * On success, invalidates the onboarding status query so the page reflects
 * the newly created task (active_task transitions from null to the new task).
 *
 * @returns Standard TanStack Query UseMutationResult for BackgroundTask
 *
 * @example
 * ```tsx
 * const mutation = useStartTask();
 *
 * mutation.mutate({ operation_type: "seed_reference" });
 * ```
 */
export function useStartTask(): UseMutationResult<
  BackgroundTask,
  Error,
  TaskCreate
> {
  const queryClient = useQueryClient();

  return useMutation<BackgroundTask, Error, TaskCreate>({
    mutationFn: (data: TaskCreate) => createTask(data),

    onSuccess: () => {
      // Invalidate the onboarding status so the page picks up the active_task.
      void queryClient.invalidateQueries({ queryKey: ONBOARDING_STATUS_KEY });
    },
  });
}

// ---------------------------------------------------------------------------
// useTaskStatus
// ---------------------------------------------------------------------------

/**
 * Hook that polls the status of a specific background task.
 *
 * Polling behaviour:
 * - The query is disabled when `taskId` is null.
 * - Polls every 2 seconds while the task status is "queued" or "running".
 * - Stops polling when status transitions to "completed" or "failed".
 * - On completion or failure, invalidates the onboarding status query ONCE so
 *   that pipeline step statuses are refreshed to reflect the finished operation.
 *
 * The single-invalidation guarantee is implemented with a ref keyed to the
 * taskId so the guard resets correctly when a new task begins.
 *
 * @param taskId - UUID of the task to poll, or null to disable the query
 * @returns Standard TanStack Query UseQueryResult for BackgroundTask
 *
 * @example
 * ```tsx
 * const { data: task } = useTaskStatus(activeTaskId);
 * const progress = task?.progress ?? 0;
 * ```
 */
export function useTaskStatus(
  taskId: string | null
): UseQueryResult<BackgroundTask, Error> {
  const queryClient = useQueryClient();

  const result = useQuery<BackgroundTask, Error>({
    queryKey: taskStatusKey(taskId),
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ signal }) => {
      // taskId is guaranteed non-null here because `enabled` guards the call.
      return fetchTaskStatus(taskId as string, signal);
    },
    enabled: taskId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Poll every 2 s while the task is in an active state.
      if (status === "queued" || status === "running") {
        return 2_000;
      }
      return false;
    },
    staleTime: 2 * 1000, // 2 seconds — matches the poll interval
    gcTime: 5 * 60 * 1000,
  });

  // Track which taskId we have already invalidated for, so we only fire once
  // per task completion regardless of how many times the component re-renders
  // with the same terminal status.
  const invalidatedForTaskRef = useRef<string | null>(null);

  const taskStatus = result.data?.status;

  useEffect(() => {
    if (
      taskId !== null &&
      (taskStatus === "completed" || taskStatus === "failed") &&
      invalidatedForTaskRef.current !== taskId
    ) {
      // Record BEFORE the async invalidation so concurrent re-renders of this
      // effect (while the fetch is in-flight) do not queue duplicate requests.
      invalidatedForTaskRef.current = taskId;
      void queryClient.invalidateQueries({ queryKey: ONBOARDING_STATUS_KEY });
    }
  }, [taskId, taskStatus, queryClient]);

  return result;
}
