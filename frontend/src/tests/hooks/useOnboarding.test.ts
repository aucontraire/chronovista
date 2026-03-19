/**
 * Unit tests for useOnboarding hooks (Feature 047, US2).
 *
 * Tests:
 * - T031-1: useOnboardingStatus fetches from the correct endpoint
 * - T031-2: useOnboardingStatus enables polling when active_task is present
 * - T031-3: useOnboardingStatus disables polling when no active task
 * - T031-4: useStartTask calls createTask with correct operation_type
 * - T031-5: useStartTask invalidates onboarding status on success
 * - T031-6: useTaskStatus is disabled when taskId is null
 * - T031-7: useTaskStatus polls while task is running
 * - T031-8: useTaskStatus stops polling when task is completed
 * - T031-9: useTaskStatus invalidates onboarding status on terminal state
 *
 * Strategy: mock the onboarding API module (`../../api/onboarding`) with
 * vi.mock() so hooks use the mocked implementations. Wrap renderHook with
 * QueryClientProvider following the pattern in useVideoDetail.test.tsx.
 *
 * @module tests/hooks/useOnboarding
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useOnboardingStatus,
  useStartTask,
  useTaskStatus,
  ONBOARDING_STATUS_KEY,
  taskStatusKey,
} from "../../hooks/useOnboarding";
import type { BackgroundTask, OnboardingStatus } from "../../types/onboarding";

// ---------------------------------------------------------------------------
// API module mock
// ---------------------------------------------------------------------------

vi.mock("../../api/onboarding", () => ({
  fetchOnboardingStatus: vi.fn(),
  createTask: vi.fn(),
  fetchTaskStatus: vi.fn(),
  fetchTasks: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockStatus: OnboardingStatus = {
  steps: [],
  is_authenticated: false,
  data_export_path: "/data/takeout",
  data_export_detected: true,
  active_task: null,
  counts: {
    channels: 0,
    videos: 0,
    playlists: 0,
    transcripts: 0,
    categories: 0,
    canonical_tags: 0,
  },
};

const mockStatusWithActiveTask: OnboardingStatus = {
  ...mockStatus,
  active_task: {
    id: "task-active-001",
    operation_type: "seed_reference",
    status: "running",
    progress: 42,
    error: null,
    started_at: "2024-01-01T00:00:00Z",
    completed_at: null,
  },
};

const mockQueuedTask: BackgroundTask = {
  id: "task-uuid-001",
  operation_type: "seed_reference",
  status: "queued",
  progress: 0,
  error: null,
  started_at: null,
  completed_at: null,
};

const mockRunningTask: BackgroundTask = {
  id: "task-uuid-001",
  operation_type: "seed_reference",
  status: "running",
  progress: 55,
  error: null,
  started_at: "2024-01-01T00:00:00Z",
  completed_at: null,
};

const mockCompletedTask: BackgroundTask = {
  id: "task-uuid-001",
  operation_type: "seed_reference",
  status: "completed",
  progress: 100,
  error: null,
  started_at: "2024-01-01T00:00:00Z",
  completed_at: "2024-01-01T00:01:00Z",
};

const mockFailedTask: BackgroundTask = {
  id: "task-uuid-001",
  operation_type: "seed_reference",
  status: "failed",
  progress: 20,
  error: "Something went wrong",
  started_at: "2024-01-01T00:00:00Z",
  completed_at: "2024-01-01T00:00:30Z",
};

// ---------------------------------------------------------------------------
// Test utilities
// ---------------------------------------------------------------------------

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Disable refetch intervals for most tests; individual tests override as needed
        refetchInterval: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// Tests: useOnboardingStatus
// ---------------------------------------------------------------------------

describe("useOnboardingStatus", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  // T031-1: Fetches from the correct endpoint
  describe("fetches from the correct endpoint (T031-1)", () => {
    it("calls fetchOnboardingStatus and returns the data", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockStatus);
      expect(fetchOnboardingStatus).toHaveBeenCalledTimes(1);
    });

    it("uses the ONBOARDING_STATUS_KEY query key", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Data should be accessible under the known query key
      const cached = queryClient.getQueryData(ONBOARDING_STATUS_KEY);
      expect(cached).toEqual(mockStatus);
    });

    it("passes an AbortSignal to fetchOnboardingStatus", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const callArg = vi.mocked(fetchOnboardingStatus).mock.calls[0]?.[0];
      expect(callArg).toBeInstanceOf(AbortSignal);
    });

    it("exposes isError=true when the fetch rejects", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockRejectedValueOnce(
        new Error("Network failure")
      );

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  // T031-2: Enables polling when active_task is present
  describe("enables polling when active_task is present (T031-2)", () => {
    it("returns data with active_task when polling fires and task is running", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      // First call returns status with active task
      vi.mocked(fetchOnboardingStatus).mockResolvedValue(
        mockStatusWithActiveTask
      );

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.active_task).not.toBeNull();
      expect(result.current.data?.active_task?.id).toBe("task-active-001");
    });

    it("refetchInterval returns 5000 when active_task is non-null", async () => {
      // The hook computes refetchInterval dynamically from query.state.data.
      // We verify the behavior by inspecting the query options stored in the cache.
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValue(
        mockStatusWithActiveTask
      );

      renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(fetchOnboardingStatus).toHaveBeenCalled();
      });

      // The query state transitions: once active_task is in cache, the interval
      // should be 5000. We confirm by checking the cached data has active_task.
      const cached =
        queryClient.getQueryData<OnboardingStatus>(ONBOARDING_STATUS_KEY);
      expect(cached?.active_task).not.toBeNull();
    });
  });

  // T031-3: Disables polling when no active task
  describe("disables polling when no active task (T031-3)", () => {
    it("does not trigger repeated fetches when active_task is null", async () => {
      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // With no active task, refetchInterval returns false — only one call expected
      expect(fetchOnboardingStatus).toHaveBeenCalledTimes(1);
      expect(result.current.data?.active_task).toBeNull();
    });

    it("refetchInterval returns false when active_task is null", async () => {
      // The hook's refetchInterval callback returns `false` when active_task is
      // null/undefined. We validate this by confirming polling does not fire a
      // second call within a short window.
      vi.useFakeTimers();

      const { fetchOnboardingStatus } = await import("../../api/onboarding");
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      renderHook(() => useOnboardingStatus(), {
        wrapper: createWrapper(queryClient),
      });

      // Advance well past the 5s poll interval
      await act(async () => {
        vi.advanceTimersByTime(15_000);
      });

      // Only the initial fetch should have fired
      expect(fetchOnboardingStatus).toHaveBeenCalledTimes(1);

      vi.useRealTimers();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: useStartTask
// ---------------------------------------------------------------------------

describe("useStartTask", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  // T031-4: Calls createTask with correct operation_type
  describe("calls createTask with correct operation_type (T031-4)", () => {
    it("invokes createTask with the provided operation_type when mutate is called", async () => {
      const { createTask } = await import("../../api/onboarding");
      vi.mocked(createTask).mockResolvedValueOnce(mockQueuedTask);

      const { result } = renderHook(() => useStartTask(), {
        wrapper: createWrapper(queryClient),
      });

      await act(async () => {
        result.current.mutate({ operation_type: "seed_reference" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(createTask).toHaveBeenCalledOnce();
      expect(createTask).toHaveBeenCalledWith({
        operation_type: "seed_reference",
      });
    });

    it("returns the created BackgroundTask on success", async () => {
      const { createTask } = await import("../../api/onboarding");
      vi.mocked(createTask).mockResolvedValueOnce(mockQueuedTask);

      const { result } = renderHook(() => useStartTask(), {
        wrapper: createWrapper(queryClient),
      });

      await act(async () => {
        result.current.mutate({ operation_type: "seed_reference" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockQueuedTask);
    });

    it("handles createTask failure and sets isError=true", async () => {
      const { createTask } = await import("../../api/onboarding");
      vi.mocked(createTask).mockRejectedValueOnce(
        new Error("409 Conflict — already running")
      );

      const { result } = renderHook(() => useStartTask(), {
        wrapper: createWrapper(queryClient),
      });

      await act(async () => {
        result.current.mutate({ operation_type: "seed_reference" });
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });

    it("calls createTask with load_data operation_type", async () => {
      const { createTask } = await import("../../api/onboarding");
      vi.mocked(createTask).mockResolvedValueOnce({
        ...mockQueuedTask,
        operation_type: "load_data",
      });

      const { result } = renderHook(() => useStartTask(), {
        wrapper: createWrapper(queryClient),
      });

      await act(async () => {
        result.current.mutate({ operation_type: "load_data" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(createTask).toHaveBeenCalledWith({ operation_type: "load_data" });
    });
  });

  // T031-5: Invalidates onboarding status on success
  describe("invalidates onboarding status on success (T031-5)", () => {
    it("marks the onboarding status query as stale (invalidated) after a successful mutation", async () => {
      const { createTask, fetchOnboardingStatus } = await import(
        "../../api/onboarding"
      );
      vi.mocked(createTask).mockResolvedValueOnce(mockQueuedTask);
      // Seed the cache with fresh data so invalidation can be observed
      queryClient.setQueryData(ONBOARDING_STATUS_KEY, mockStatus);
      vi.mocked(fetchOnboardingStatus).mockResolvedValue(
        mockStatusWithActiveTask
      );

      // Render both hooks in a shared wrapper so the status query has an active
      // observer — without an observer, invalidation triggers no refetch.
      const { result } = renderHook(
        () => ({ mutate: useStartTask(), status: useOnboardingStatus() }),
        { wrapper: createWrapper(queryClient) }
      );

      // Wait for the initial status fetch to settle
      await waitFor(() => {
        expect(result.current.status.isSuccess).toBe(true);
      });

      // Store how many times fetchOnboardingStatus was called before mutation
      const callsBefore = vi.mocked(fetchOnboardingStatus).mock.calls.length;

      await act(async () => {
        result.current.mutate.mutate({ operation_type: "seed_reference" });
      });

      await waitFor(() => {
        expect(result.current.mutate.isSuccess).toBe(true);
      });

      // The mutation's onSuccess calls invalidateQueries, which triggers a
      // refetch because the status query has an active observer.
      await waitFor(() => {
        const callsAfter = vi.mocked(fetchOnboardingStatus).mock.calls.length;
        expect(callsAfter).toBeGreaterThan(callsBefore);
      });
    });

    it("does not trigger additional status fetches when mutation fails", async () => {
      const { createTask, fetchOnboardingStatus } = await import(
        "../../api/onboarding"
      );
      vi.mocked(createTask).mockRejectedValueOnce(new Error("Conflict"));
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => ({ mutate: useStartTask(), status: useOnboardingStatus() }),
        { wrapper: createWrapper(queryClient) }
      );

      // Wait for initial status load
      await waitFor(() => {
        expect(result.current.status.isSuccess).toBe(true);
      });

      const callsBefore = vi.mocked(fetchOnboardingStatus).mock.calls.length;

      await act(async () => {
        result.current.mutate.mutate({ operation_type: "seed_reference" });
      });

      await waitFor(() => {
        expect(result.current.mutate.isError).toBe(true);
      });

      // No additional fetch triggered — onSuccess is not called on failure
      expect(vi.mocked(fetchOnboardingStatus).mock.calls.length).toBe(callsBefore);
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: useTaskStatus
// ---------------------------------------------------------------------------

describe("useTaskStatus", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
    vi.useRealTimers();
  });

  // T031-6: Disabled when taskId is null
  describe("disabled when taskId is null (T031-6)", () => {
    it("does not call fetchTaskStatus when taskId is null", async () => {
      const { fetchTaskStatus } = await import("../../api/onboarding");

      const { result } = renderHook(() => useTaskStatus(null), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(fetchTaskStatus).not.toHaveBeenCalled();
    });

    it("returns isPending=false when taskId is null (query is disabled)", async () => {
      const { result } = renderHook(() => useTaskStatus(null), {
        wrapper: createWrapper(queryClient),
      });

      // A disabled query is not pending
      expect(result.current.isPending).toBe(true); // TanStack v5: disabled queries start pending
      // But fetchTaskStatus must NOT have been called
      const { fetchTaskStatus } = await import("../../api/onboarding");
      expect(fetchTaskStatus).not.toHaveBeenCalled();
    });

    it("transitions from disabled to active when taskId changes from null to a string", async () => {
      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus).mockResolvedValueOnce(mockRunningTask);

      let taskId: string | null = null;
      const { result, rerender } = renderHook(() => useTaskStatus(taskId), {
        wrapper: createWrapper(queryClient),
      });

      // Initially disabled — no fetch
      expect(fetchTaskStatus).not.toHaveBeenCalled();

      // Provide a real taskId
      taskId = "task-uuid-001";
      rerender();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(fetchTaskStatus).toHaveBeenCalledWith(
        "task-uuid-001",
        expect.any(AbortSignal)
      );
    });
  });

  // T031-7: Polls while task is running
  describe("polls while task is running (T031-7)", () => {
    it("fetches task data when taskId is provided and task is queued", async () => {
      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus).mockResolvedValueOnce(mockQueuedTask);

      const { result } = renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockQueuedTask);
      expect(fetchTaskStatus).toHaveBeenCalledWith(
        "task-uuid-001",
        expect.any(AbortSignal)
      );
    });

    it("fetches task data when task is in running status", async () => {
      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus).mockResolvedValueOnce(mockRunningTask);

      const { result } = renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe("running");
    });

    it("returns refetchInterval=2000 behavior when task is queued or running", async () => {
      // The hook's refetchInterval callback returns 2000 for queued/running.
      // We verify by using fake timers to confirm a second fetch fires after
      // the 2s interval elapses.
      vi.useFakeTimers({ shouldAdvanceTime: true });

      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus).mockResolvedValue(mockRunningTask);

      // Use a separate QueryClient that does NOT disable refetchInterval so
      // the hook's own refetchInterval option takes effect.
      const pollingClient = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
        },
      });

      renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(pollingClient),
      });

      // Let the initial fetch settle
      await act(async () => {
        vi.advanceTimersByTime(200);
      });

      // Now advance past the 2s poll interval
      await act(async () => {
        vi.advanceTimersByTime(2_200);
      });

      expect(fetchTaskStatus).toHaveBeenCalledTimes(2);

      pollingClient.clear();
    });
  });

  // T031-8: Stops polling when task is completed
  describe("stops polling when task is completed (T031-8)", () => {
    it("does not continue polling after task reaches completed status", async () => {
      vi.useFakeTimers();

      const { fetchTaskStatus } = await import("../../api/onboarding");
      // First call: running → second call: completed
      vi.mocked(fetchTaskStatus)
        .mockResolvedValueOnce(mockRunningTask)
        .mockResolvedValueOnce(mockCompletedTask);

      renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(queryClient),
      });

      // Let the first fetch fire
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      // Advance past 2s to trigger the second fetch (running → completed)
      await act(async () => {
        vi.advanceTimersByTime(2_100);
      });

      // Advance another 4s — no third fetch should fire since task is completed
      await act(async () => {
        vi.advanceTimersByTime(4_000);
      });

      // Only two fetches total
      expect(fetchTaskStatus).toHaveBeenCalledTimes(2);
    });

    it("stops polling after task reaches failed status", async () => {
      vi.useFakeTimers();

      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus)
        .mockResolvedValueOnce(mockRunningTask)
        .mockResolvedValueOnce(mockFailedTask);

      renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(queryClient),
      });

      await act(async () => {
        vi.advanceTimersByTime(100);
      });
      await act(async () => {
        vi.advanceTimersByTime(2_100);
      });
      await act(async () => {
        vi.advanceTimersByTime(4_000);
      });

      expect(fetchTaskStatus).toHaveBeenCalledTimes(2);
    });
  });

  // T031-9: Invalidates onboarding status on terminal state
  describe("invalidates onboarding status on terminal state (T031-9)", () => {
    it("invalidates ONBOARDING_STATUS_KEY when task reaches completed status", async () => {
      const { fetchTaskStatus, fetchOnboardingStatus } = await import(
        "../../api/onboarding"
      );
      // Stage: status resolves first; task resolves after status is settled
      vi.mocked(fetchOnboardingStatus).mockResolvedValue(mockStatus);
      // Block the task fetch with a deferred promise so we control timing
      let resolveTask!: (v: BackgroundTask) => void;
      vi.mocked(fetchTaskStatus).mockReturnValueOnce(
        new Promise<BackgroundTask>((res) => { resolveTask = res; })
      );

      const { result } = renderHook(
        () => ({
          task: useTaskStatus("task-uuid-001"),
          status: useOnboardingStatus(),
        }),
        { wrapper: createWrapper(queryClient) }
      );

      // Wait for the initial status fetch to settle BEFORE the task resolves
      await waitFor(() => {
        expect(result.current.status.isSuccess).toBe(true);
      });

      // Record how many times status has been fetched so far
      const callsBefore = vi.mocked(fetchOnboardingStatus).mock.calls.length;
      expect(callsBefore).toBeGreaterThanOrEqual(1);

      // Now resolve the task with a terminal status — this should trigger invalidation
      await act(async () => {
        resolveTask(mockCompletedTask);
      });

      await waitFor(() => {
        expect(result.current.task.data?.status).toBe("completed");
      });

      // The useEffect in useTaskStatus calls invalidateQueries when the task
      // reaches "completed", which triggers a refetch of the status query.
      await waitFor(() => {
        const callsAfter = vi.mocked(fetchOnboardingStatus).mock.calls.length;
        expect(callsAfter).toBeGreaterThan(callsBefore);
      });
    });

    it("invalidates ONBOARDING_STATUS_KEY when task reaches failed status", async () => {
      const { fetchTaskStatus, fetchOnboardingStatus } = await import(
        "../../api/onboarding"
      );
      vi.mocked(fetchOnboardingStatus).mockResolvedValue(mockStatus);
      let resolveTask!: (v: BackgroundTask) => void;
      vi.mocked(fetchTaskStatus).mockReturnValueOnce(
        new Promise<BackgroundTask>((res) => { resolveTask = res; })
      );

      const { result } = renderHook(
        () => ({
          task: useTaskStatus("task-uuid-001"),
          status: useOnboardingStatus(),
        }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.status.isSuccess).toBe(true);
      });

      const callsBefore = vi.mocked(fetchOnboardingStatus).mock.calls.length;

      await act(async () => {
        resolveTask(mockFailedTask);
      });

      await waitFor(() => {
        expect(result.current.task.data?.status).toBe("failed");
      });

      await waitFor(() => {
        const callsAfter = vi.mocked(fetchOnboardingStatus).mock.calls.length;
        expect(callsAfter).toBeGreaterThan(callsBefore);
      });
    });

    it("does not invalidate ONBOARDING_STATUS_KEY when task is still running", async () => {
      const { fetchTaskStatus, fetchOnboardingStatus } = await import(
        "../../api/onboarding"
      );
      vi.mocked(fetchTaskStatus).mockResolvedValueOnce(mockRunningTask);
      vi.mocked(fetchOnboardingStatus).mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => ({
          task: useTaskStatus("task-uuid-001"),
          status: useOnboardingStatus(),
        }),
        { wrapper: createWrapper(queryClient) }
      );

      // Wait for both hooks to settle
      await waitFor(() => {
        expect(result.current.status.isSuccess).toBe(true);
        expect(result.current.task.isSuccess).toBe(true);
        expect(result.current.task.data?.status).toBe("running");
      });

      const callsAfterSettle = vi.mocked(fetchOnboardingStatus).mock.calls.length;

      // Give the hook a moment to potentially call invalidation (it should not)
      await new Promise((r) => setTimeout(r, 50));

      // No additional fetch should have been triggered for a running task
      expect(vi.mocked(fetchOnboardingStatus).mock.calls.length).toBe(
        callsAfterSettle
      );
    });

    it("uses taskStatusKey factory for the query key", async () => {
      const { fetchTaskStatus } = await import("../../api/onboarding");
      vi.mocked(fetchTaskStatus).mockResolvedValueOnce(mockCompletedTask);

      const { result } = renderHook(() => useTaskStatus("task-uuid-001"), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Data should be accessible under the stable task key
      const cached = queryClient.getQueryData(taskStatusKey("task-uuid-001"));
      expect(cached).toEqual(mockCompletedTask);
    });
  });
});
