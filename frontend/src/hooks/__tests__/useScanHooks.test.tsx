/**
 * Tests for useScanEntity and useScanVideoEntities launch→poll hooks
 * in hooks/useEntityMentions.ts (async entity-mention scan flow).
 *
 * The scan endpoints now launch a background job (202) instead of blocking
 * for the scan's full duration. These hooks POST to launch the job, then
 * poll GET /scan-jobs/{job_id} every 2s while it's running, and resolve via
 * onSuccess/onError callbacks once the job reaches a terminal status.
 *
 * Coverage:
 * - useScanEntity: launches via scanEntity() with correct entityId/options
 * - useScanEntity: launch→poll→succeeded — isPending true until terminal,
 *   then isSuccess, data.data exposes the result, onSuccess callback fires
 * - useScanEntity: launch→poll→failed — onError fires with the job's real
 *   error message (not a generic message)
 * - useScanEntity: 409 on launch (already in progress) — onError fires
 *   immediately with status 409, no polling occurs
 * - useScanEntity: polls getScanJob every 2s while running, stops once terminal
 * - useScanEntity: invalidates ["entity-detail", entityId] and
 *   ["entity-videos", entityId] only on success, never on failure
 * - useScanVideoEntities: launches via scanVideoEntities() with correct videoId/options
 * - useScanVideoEntities: launch→poll→succeeded / failed / 409 (mirrors useScanEntity)
 * - useScanVideoEntities: invalidates only ["video-entities", videoId] on success
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { scanEntity, scanVideoEntities, getScanJob } from "../../api/entityMentions";
import { useScanEntity, useScanVideoEntities } from "../useEntityMentions";
import type { ScanJob } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  scanEntity: vi.fn(),
  scanVideoEntities: vi.fn(),
  getScanJob: vi.fn(),
  // Stub all other exports that useEntityMentions imports transitively.
  fetchVideoEntities: vi.fn(),
  fetchEntityVideos: vi.fn(),
  fetchEntities: vi.fn(),
  createManualAssociation: vi.fn(),
  deleteManualAssociation: vi.fn(),
  classifyTag: vi.fn(),
  checkEntityDuplicate: vi.fn(),
  createEntity: vi.fn(),
  createEntityAlias: vi.fn(),
  fetchEntityDetail: vi.fn(),
  addExclusionPattern: vi.fn(),
  removeExclusionPattern: vi.fn(),
  fetchPhoneticMatches: vi.fn(),
  searchEntities: vi.fn(),
}));

const mockedScanEntity = vi.mocked(scanEntity);
const mockedScanVideoEntities = vi.mocked(scanVideoEntities);
const mockedGetScanJob = vi.mocked(getScanJob);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-abc123";
const VIDEO_ID = "dQw4w9WgXcQ";
const JOB_ID = "scan-job-xyz";

function makeJob(overrides: Partial<ScanJob> = {}): ScanJob {
  return {
    job_id: JOB_ID,
    kind: "entity",
    target_id: ENTITY_ID,
    status: "running",
    result: null,
    error: null,
    started_at: "2026-07-19T12:00:00Z",
    finished_at: null,
    ...overrides,
  };
}

function makeSucceededJob(
  resultOverrides: Partial<NonNullable<ScanJob["result"]>> = {},
  jobOverrides: Partial<ScanJob> = {}
): ScanJob {
  return makeJob({
    status: "succeeded",
    finished_at: "2026-07-19T12:03:00Z",
    result: {
      segments_scanned: 100,
      mentions_found: 5,
      mentions_skipped: 0,
      unique_entities: 2,
      unique_videos: 1,
      duration_seconds: 120.3,
      dry_run: false,
      ...resultOverrides,
    },
    ...jobOverrides,
  });
}

function makeFailedJob(error: string, jobOverrides: Partial<ScanJob> = {}): ScanJob {
  return makeJob({
    status: "failed",
    finished_at: "2026-07-19T12:01:00Z",
    error,
    ...jobOverrides,
  });
}

// ===========================================================================
// useScanEntity
// ===========================================================================

describe("useScanEntity — launch and terminal states", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("starts in idle state with no data", () => {
    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isPending).toBe(false);
    expect(result.current.isSuccess).toBe(false);
    expect(result.current.isError).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it("calls scanEntity with the provided entityId and options to launch the scan", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(makeSucceededJob());

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: ENTITY_ID,
        options: { sources: ["transcript", "title"] },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedScanEntity).toHaveBeenCalledWith(ENTITY_ID, {
      sources: ["transcript", "title"],
    });
  });

  it("isPending is true immediately after launch and while the job is running", async () => {
    let resolveJob!: (job: ScanJob) => void;
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockReturnValueOnce(
      new Promise<ScanJob>((resolve) => {
        resolveJob = resolve;
      })
    );

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isPending).toBe(true));

    // Resolve the poll so the test doesn't leave a dangling promise.
    await act(async () => {
      resolveJob(makeSucceededJob());
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("transitions to isSuccess with data.data exposing the result once the job succeeds", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(
      makeSucceededJob({ mentions_found: 12, unique_videos: 4 })
    );

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.isPending).toBe(false);
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.data.mentions_found).toBe(12);
    expect(result.current.data?.data.unique_videos).toBe(4);
  });

  it("fires the onSuccess callback with the terminal result once the job succeeds", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(
      makeSucceededJob({ mentions_found: 7, unique_videos: 3 })
    );
    const onSuccess = vi.fn();
    const onError = vi.fn();

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID }, { onSuccess, onError });
    });

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());

    expect(onSuccess).toHaveBeenCalledWith({
      data: expect.objectContaining({ mentions_found: 7, unique_videos: 3 }),
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("fires onError with the job's real failure reason when the job fails", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(
      makeFailedJob("Database connection lost during scan")
    );
    const onSuccess = vi.fn();
    const onError = vi.fn();

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID }, { onSuccess, onError });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(onError).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Database connection lost during scan" })
    );
    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.error?.message).toBe("Database connection lost during scan");
  });

  it("fires onError immediately with status 409 when a scan is already in progress", async () => {
    mockedScanEntity.mockRejectedValueOnce({
      type: "server",
      message: "A scan is already in progress for this entity",
      status: 409,
    });
    const onError = vi.fn();

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID }, { onError });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ status: 409 })
    );
    // No polling should occur — the scan never launched a job.
    expect(mockedGetScanJob).not.toHaveBeenCalled();
  });

  it("does not poll further once a 404 launch error occurs", async () => {
    mockedScanEntity.mockRejectedValueOnce({
      type: "server",
      message: "Entity not found",
      status: 404,
    });

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.status).toBe(404);
    expect(mockedGetScanJob).not.toHaveBeenCalled();
  });

  it("reset() clears the flow back to idle state", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(makeSucceededJob());

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    act(() => {
      result.current.reset();
    });

    expect(result.current.isSuccess).toBe(false);
    expect(result.current.isPending).toBe(false);
    expect(result.current.data).toBeUndefined();
  });
});

describe("useScanEntity — polling behaviour", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("polls getScanJob again while the job is still running, and stops once terminal", async () => {
    // Verifies the launch→poll→poll→terminal sequence without asserting on
    // exact interval timing (TanStack's refetchInterval scheduling is
    // exercised generically for this same pattern in useOnboarding.test.ts).
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob
      .mockResolvedValueOnce(makeJob({ status: "running" }))
      .mockResolvedValueOnce(makeJob({ status: "running" }))
      .mockResolvedValueOnce(makeSucceededJob());

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    // Still running after the first poll resolves.
    await waitFor(() => expect(mockedGetScanJob).toHaveBeenCalledTimes(1));
    expect(result.current.isPending).toBe(true);
    expect(result.current.isSuccess).toBe(false);

    // Manually trigger the next poll (bypassing the real 2s interval) by
    // invalidating the scan-job query — mirrors what refetchInterval does.
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["scan-job"], exact: false });
    });
    await waitFor(() => expect(mockedGetScanJob).toHaveBeenCalledTimes(2));
    expect(result.current.isPending).toBe(true);

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["scan-job"], exact: false });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGetScanJob).toHaveBeenCalledTimes(3);
  });
});

describe("useScanEntity — cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates ['entity-detail', entityId] and ['entity-videos', entityId] once the job succeeds", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(makeSucceededJob());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual(["entity-detail", ENTITY_ID]);
    expect(invalidatedKeys).toContainEqual(["entity-videos", ENTITY_ID]);
  });

  it("does NOT invalidate any caches when the job fails", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeJob());
    mockedGetScanJob.mockResolvedValueOnce(makeFailedJob("boom"));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("does NOT invalidate any caches on a 409 launch failure", async () => {
    mockedScanEntity.mockRejectedValueOnce({
      type: "server",
      message: "already running",
      status: 409,
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// useScanVideoEntities
// ===========================================================================

describe("useScanVideoEntities — launch and terminal states", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("starts in idle state with no data", () => {
    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isPending).toBe(false);
    expect(result.current.isSuccess).toBe(false);
    expect(result.current.isError).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it("calls scanVideoEntities with the provided videoId and options to launch the scan", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(
      makeJob({ kind: "video", target_id: VIDEO_ID })
    );
    mockedGetScanJob.mockResolvedValueOnce(
      makeSucceededJob({}, { kind: "video", target_id: VIDEO_ID })
    );

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        videoId: VIDEO_ID,
        options: { entity_type: "person" },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedScanVideoEntities).toHaveBeenCalledWith(VIDEO_ID, {
      entity_type: "person",
    });
  });

  it("transitions to isSuccess and exposes the result once the job succeeds", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(
      makeJob({ kind: "video", target_id: VIDEO_ID })
    );
    mockedGetScanJob.mockResolvedValueOnce(
      makeSucceededJob(
        { unique_entities: 5, mentions_found: 18 },
        { kind: "video", target_id: VIDEO_ID }
      )
    );

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.data.unique_entities).toBe(5);
    expect(result.current.data?.data.mentions_found).toBe(18);
  });

  it("fires onError with the job's real failure reason when the job fails", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(
      makeJob({ kind: "video", target_id: VIDEO_ID })
    );
    mockedGetScanJob.mockResolvedValueOnce(
      makeFailedJob("Transcript fetch timed out", {
        kind: "video",
        target_id: VIDEO_ID,
      })
    );
    const onError = vi.fn();

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID }, { onError });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Transcript fetch timed out" })
    );
  });

  it("fires onError immediately with status 409 when a scan is already in progress", async () => {
    mockedScanVideoEntities.mockRejectedValueOnce({
      type: "server",
      message: "A scan is already in progress for this video",
      status: 409,
    });
    const onError = vi.fn();

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID }, { onError });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ status: 409 }));
    expect(mockedGetScanJob).not.toHaveBeenCalled();
  });
});

describe("useScanVideoEntities — cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates only ['video-entities', videoId] on success", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(
      makeJob({ kind: "video", target_id: VIDEO_ID })
    );
    mockedGetScanJob.mockResolvedValueOnce(
      makeSucceededJob({}, { kind: "video", target_id: VIDEO_ID })
    );

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual(["video-entities", VIDEO_ID]);
    expect(invalidatedKeys).not.toContainEqual(["entity-detail", VIDEO_ID]);
    expect(invalidatedKeys).not.toContainEqual(["entity-videos", VIDEO_ID]);
  });

  it("does NOT invalidate any caches when the job fails", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(
      makeJob({ kind: "video", target_id: VIDEO_ID })
    );
    mockedGetScanJob.mockResolvedValueOnce(
      makeFailedJob("boom", { kind: "video", target_id: VIDEO_ID })
    );

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
