/**
 * Tests for useScanEntity and useScanVideoEntities mutation hooks
 * in hooks/useEntityMentions.ts (Feature 052).
 *
 * Coverage:
 * - useScanEntity: calls scanEntity() API with correct entityId and options
 * - useScanEntity: transitions through isPending → isSuccess states
 * - useScanEntity: transitions through isPending → isError states
 * - useScanEntity: invalidates ["entity-detail", entityId] on success
 * - useScanEntity: invalidates ["entity-videos", entityId] on success
 * - useScanEntity: does NOT invalidate on failure
 * - useScanVideoEntities: calls scanVideoEntities() API with correct videoId and options
 * - useScanVideoEntities: transitions through isPending → isSuccess states
 * - useScanVideoEntities: transitions through isPending → isError states
 * - useScanVideoEntities: invalidates ["video-entities", videoId] on success
 * - useScanVideoEntities: does NOT invalidate on failure
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { scanEntity, scanVideoEntities } from "../../api/entityMentions";
import { useScanEntity, useScanVideoEntities } from "../useEntityMentions";
import type { ScanResultResponse } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  scanEntity: vi.fn(),
  scanVideoEntities: vi.fn(),
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

function makeScanResultResponse(
  overrides: Partial<ScanResultResponse["data"]> = {}
): ScanResultResponse {
  return {
    data: {
      segments_scanned: 100,
      mentions_found: 5,
      mentions_skipped: 0,
      unique_entities: 2,
      unique_videos: 1,
      duration_seconds: 0.3,
      dry_run: false,
      ...overrides,
    },
  };
}

// ===========================================================================
// useScanEntity
// ===========================================================================

describe("useScanEntity — mutation execution", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls scanEntity with the provided entityId when mutate is invoked", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse());

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedScanEntity).toHaveBeenCalledOnce();
    expect(mockedScanEntity).toHaveBeenCalledWith(ENTITY_ID, undefined);
  });

  it("calls scanEntity with options when options are provided", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse({ dry_run: true }));

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: ENTITY_ID,
        options: { dry_run: true, language_code: "en" },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedScanEntity).toHaveBeenCalledWith(ENTITY_ID, {
      dry_run: true,
      language_code: "en",
    });
  });

  it("transitions to isSuccess and exposes response data", async () => {
    const response = makeScanResultResponse({ mentions_found: 10, unique_videos: 3 });
    mockedScanEntity.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.data.mentions_found).toBe(10);
    expect(result.current.data?.data.unique_videos).toBe(3);
  });

  it("transitions to isError when scanEntity throws", async () => {
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

    await waitFor(() => result.current.isError);

    expect(result.current.isError).toBe(true);
    expect(result.current.isSuccess).toBe(false);
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

  it("exposes zero-result scan data when mentions_found is 0", async () => {
    const response = makeScanResultResponse({ mentions_found: 0, unique_videos: 0 });
    mockedScanEntity.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.data?.data.mentions_found).toBe(0);
    expect(result.current.data?.data.unique_videos).toBe(0);
  });
});

describe("useScanEntity — onSuccess cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates ['entity-detail', entityId] after a successful scan", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-detail", ENTITY_ID] })
    );
  });

  it("invalidates ['entity-videos', entityId] after a successful scan", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-videos", ENTITY_ID] })
    );
  });

  it("invalidates both entity-detail and entity-videos on a single success", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );

    expect(invalidatedKeys).toContainEqual(["entity-detail", ENTITY_ID]);
    expect(invalidatedKeys).toContainEqual(["entity-videos", ENTITY_ID]);
  });

  it("uses the correct entityId in cache keys — not a different entity's ID", async () => {
    mockedScanEntity.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const SPECIFIC_ENTITY_ID = "specific-entity-xyz";

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: SPECIFIC_ENTITY_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-detail", SPECIFIC_ENTITY_ID] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-videos", SPECIFIC_ENTITY_ID] })
    );
  });

  it("does NOT invalidate caches when the scan mutation fails", async () => {
    mockedScanEntity.mockRejectedValueOnce({
      type: "server",
      message: "Internal server error",
      status: 500,
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ entityId: ENTITY_ID });
    });

    await waitFor(() => result.current.isError);

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// useScanVideoEntities
// ===========================================================================

describe("useScanVideoEntities — mutation execution", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls scanVideoEntities with the provided videoId when mutate is invoked", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(makeScanResultResponse());

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedScanVideoEntities).toHaveBeenCalledOnce();
    expect(mockedScanVideoEntities).toHaveBeenCalledWith(VIDEO_ID, undefined);
  });

  it("calls scanVideoEntities with options when options are provided", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(makeScanResultResponse());

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        videoId: VIDEO_ID,
        options: { entity_type: "person", language_code: "fr" },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedScanVideoEntities).toHaveBeenCalledWith(VIDEO_ID, {
      entity_type: "person",
      language_code: "fr",
    });
  });

  it("transitions to isSuccess and exposes response data", async () => {
    const response = makeScanResultResponse({
      unique_entities: 5,
      mentions_found: 18,
    });
    mockedScanVideoEntities.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.data.unique_entities).toBe(5);
    expect(result.current.data?.data.mentions_found).toBe(18);
  });

  it("transitions to isError when scanVideoEntities throws", async () => {
    mockedScanVideoEntities.mockRejectedValueOnce({
      type: "server",
      message: "Video not found",
      status: 404,
    });

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isError);

    expect(result.current.isError).toBe(true);
    expect(result.current.isSuccess).toBe(false);
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

  it("exposes zero-result scan data when no entities were found in the video", async () => {
    const response = makeScanResultResponse({
      mentions_found: 0,
      unique_entities: 0,
    });
    mockedScanVideoEntities.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.data?.data.mentions_found).toBe(0);
    expect(result.current.data?.data.unique_entities).toBe(0);
  });
});

describe("useScanVideoEntities — onSuccess cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates ['video-entities', videoId] after a successful scan", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["video-entities", VIDEO_ID] })
    );
  });

  it("uses the correct videoId in the cache key", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const SPECIFIC_VIDEO_ID = "specific-video-abc";

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: SPECIFIC_VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["video-entities", SPECIFIC_VIDEO_ID] })
    );
  });

  it("does NOT invalidate caches when the scan mutation fails", async () => {
    mockedScanVideoEntities.mockRejectedValueOnce({
      type: "server",
      message: "Internal server error",
      status: 500,
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isError);

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("does NOT invalidate entity-detail or entity-videos (those belong to useScanEntity)", async () => {
    mockedScanVideoEntities.mockResolvedValueOnce(makeScanResultResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useScanVideoEntities(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID });
    });

    await waitFor(() => result.current.isSuccess);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0]
    );

    expect(invalidatedKeys).not.toContain("entity-detail");
    expect(invalidatedKeys).not.toContain("entity-videos");
  });
});
