/**
 * Tests for useDeleteManualAssociation hook in hooks/useEntityMentions.ts.
 *
 * Coverage:
 * - onMutate: cancels in-flight queries for the affected video
 * - onMutate: snapshots existing cache before applying optimistic update
 * - onMutate optimistic removal: manual-only entity (mention_count === 0) is
 *   removed from the cache immediately
 * - onMutate optimistic has_manual clearing: multi-source entity (mention_count > 0)
 *   keeps its entry but has has_manual set to false and "manual" removed from sources
 * - onError: rolls back cache to snapshot on failure
 * - onSuccess: invalidates entity-related caches with refetchType "none" for
 *   video-entities, and triggers refetch for entitySearch / entity-videos / entity-detail
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch } from "../../api/config";
import { useDeleteManualAssociation } from "../useEntityMentions";
import type { VideoEntitiesResponse, VideoEntitySummary } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mock apiFetch so no real HTTP calls are made
// ---------------------------------------------------------------------------

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

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

const VIDEO_ID = "test-video-001";
const ENTITY_ID_MANUAL_ONLY = "ent-manual-only";
const ENTITY_ID_MULTI_SOURCE = "ent-multi-source";
const ENTITY_ID_TRANSCRIPT_ONLY = "ent-transcript-only";

function makeManualOnlyEntity(overrides: Partial<VideoEntitySummary> = {}): VideoEntitySummary {
  return {
    entity_id: ENTITY_ID_MANUAL_ONLY,
    canonical_name: "Elon Musk",
    entity_type: "person",
    description: "CEO of Tesla",
    mention_count: 0,
    first_mention_time: null,
    sources: ["manual"],
    has_manual: true,
    ...overrides,
  };
}

function makeMultiSourceEntity(overrides: Partial<VideoEntitySummary> = {}): VideoEntitySummary {
  return {
    entity_id: ENTITY_ID_MULTI_SOURCE,
    canonical_name: "SpaceX",
    entity_type: "organization",
    description: "Aerospace company",
    mention_count: 4,
    first_mention_time: 65.0,
    sources: ["transcript", "manual"],
    has_manual: true,
    ...overrides,
  };
}

function makeTranscriptOnlyEntity(overrides: Partial<VideoEntitySummary> = {}): VideoEntitySummary {
  return {
    entity_id: ENTITY_ID_TRANSCRIPT_ONLY,
    canonical_name: "MIT Media Lab",
    entity_type: "organization",
    description: null,
    mention_count: 8,
    first_mention_time: 30.0,
    sources: ["transcript"],
    has_manual: false,
    ...overrides,
  };
}

function makeVideoEntitiesResponse(entities: VideoEntitySummary[]): VideoEntitiesResponse {
  return { data: entities };
}

// The query key format used by useVideoEntities
function videoEntitiesKey(videoId: string, languageCode: string | null = null): unknown[] {
  return ["video-entities", videoId, languageCode];
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("useDeleteManualAssociation — onMutate optimistic updates", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Manual-only entity: removed from the list
  // -------------------------------------------------------------------------

  it("removes a manual-only entity (mention_count === 0) from the cache immediately on mutate", async () => {
    const initialEntities = [makeManualOnlyEntity(), makeTranscriptOnlyEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    // Delay apiFetch so we can inspect the cache AFTER onMutate fires
    mockedApiFetch.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(undefined), 100))
    );

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    // Immediately after mutate() is called onMutate runs synchronously with await
    await waitFor(() => result.current.isPending);

    const cached = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID)
    );

    // Manual-only entity must be gone
    const entityIds = cached?.data.map((e) => e.entity_id) ?? [];
    expect(entityIds).not.toContain(ENTITY_ID_MANUAL_ONLY);

    // Transcript-only entity must still be there
    expect(entityIds).toContain(ENTITY_ID_TRANSCRIPT_ONLY);
  });

  // -------------------------------------------------------------------------
  // Multi-source entity: has_manual cleared, "manual" removed from sources
  // -------------------------------------------------------------------------

  it("clears has_manual and removes 'manual' from sources for a multi-source entity (mention_count > 0)", async () => {
    const initialEntities = [makeMultiSourceEntity(), makeTranscriptOnlyEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    mockedApiFetch.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(undefined), 100))
    );

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MULTI_SOURCE });
    });

    await waitFor(() => result.current.isPending);

    const cached = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID)
    );

    const updatedEntity = cached?.data.find((e) => e.entity_id === ENTITY_ID_MULTI_SOURCE);

    // Entity remains (transcript mentions still exist)
    expect(updatedEntity).toBeDefined();
    // has_manual is cleared
    expect(updatedEntity?.has_manual).toBe(false);
    // "manual" is removed from sources
    expect(updatedEntity?.sources).not.toContain("manual");
    // "transcript" remains in sources
    expect(updatedEntity?.sources).toContain("transcript");
    // mention_count is unchanged (transcript hits are unaffected)
    expect(updatedEntity?.mention_count).toBe(4);
  });

  it("does NOT remove or alter a transcript-only entity when deleting a different entity's manual link", async () => {
    const initialEntities = [makeManualOnlyEntity(), makeTranscriptOnlyEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    mockedApiFetch.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(undefined), 100))
    );

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isPending);

    const cached = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID)
    );

    const transcriptEntity = cached?.data.find(
      (e) => e.entity_id === ENTITY_ID_TRANSCRIPT_ONLY
    );

    expect(transcriptEntity).toBeDefined();
    expect(transcriptEntity?.has_manual).toBe(false);
    expect(transcriptEntity?.sources).toEqual(["transcript"]);
    expect(transcriptEntity?.mention_count).toBe(8);
  });

  // -------------------------------------------------------------------------
  // Snapshot: multiple language-code cache variants updated
  // -------------------------------------------------------------------------

  it("applies the optimistic update to all language-code variants of the cache key", async () => {
    const initialEntities = [makeManualOnlyEntity()];

    // Seed both the no-language and language-specific cache entries
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID, null),
      makeVideoEntitiesResponse(initialEntities)
    );
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID, "en"),
      makeVideoEntitiesResponse(initialEntities)
    );

    mockedApiFetch.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(undefined), 100))
    );

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isPending);

    // Both cache variants must be updated
    const cachedDefault = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID, null)
    );
    const cachedEn = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID, "en")
    );

    expect(cachedDefault?.data.map((e) => e.entity_id)).not.toContain(ENTITY_ID_MANUAL_ONLY);
    expect(cachedEn?.data.map((e) => e.entity_id)).not.toContain(ENTITY_ID_MANUAL_ONLY);
  });
});

// ---------------------------------------------------------------------------
// onError rollback
// ---------------------------------------------------------------------------

describe("useDeleteManualAssociation — onError rollback", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("restores the cache to its pre-mutation state when the API call fails", async () => {
    const initialEntities = [makeManualOnlyEntity(), makeTranscriptOnlyEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    const apiError = { type: "server", message: "Internal Server Error", status: 500 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isError);

    const cached = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID)
    );

    // Both entities must be restored
    const entityIds = cached?.data.map((e) => e.entity_id) ?? [];
    expect(entityIds).toContain(ENTITY_ID_MANUAL_ONLY);
    expect(entityIds).toContain(ENTITY_ID_TRANSCRIPT_ONLY);

    // Manual-only entity properties must be restored to their original values
    const restoredManualEntity = cached?.data.find(
      (e) => e.entity_id === ENTITY_ID_MANUAL_ONLY
    );
    expect(restoredManualEntity?.has_manual).toBe(true);
    expect(restoredManualEntity?.sources).toContain("manual");
  });

  it("restores the multi-source entity's has_manual and sources after a failed delete", async () => {
    const initialEntities = [makeMultiSourceEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    mockedApiFetch.mockRejectedValueOnce({
      type: "server",
      message: "Server Error",
      status: 500,
    });

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MULTI_SOURCE });
    });

    await waitFor(() => result.current.isError);

    const cached = queryClient.getQueryData<VideoEntitiesResponse>(
      videoEntitiesKey(VIDEO_ID)
    );

    const restoredEntity = cached?.data.find(
      (e) => e.entity_id === ENTITY_ID_MULTI_SOURCE
    );

    expect(restoredEntity?.has_manual).toBe(true);
    expect(restoredEntity?.sources).toContain("manual");
    expect(restoredEntity?.sources).toContain("transcript");
  });
});

// ---------------------------------------------------------------------------
// onSuccess cache invalidation
// ---------------------------------------------------------------------------

describe("useDeleteManualAssociation — onSuccess cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("marks video-entities cache as stale (invalidates) after success", async () => {
    const initialEntities = [makeManualOnlyEntity()];
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse(initialEntities)
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    // video-entities must be invalidated with refetchType: "none"
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["video-entities", VIDEO_ID],
        refetchType: "none",
      })
    );
  });

  it("invalidates the entitySearch cache after success", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([makeManualOnlyEntity()])
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entitySearch"] })
    );
  });

  it("invalidates the entity-videos cache after success", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([makeManualOnlyEntity()])
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-videos"] })
    );
  });

  it("invalidates the entity-detail cache after success", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([makeManualOnlyEntity()])
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-detail"] })
    );
  });
});

// ---------------------------------------------------------------------------
// Mutation happy path: actually calls deleteManualAssociation
// ---------------------------------------------------------------------------

describe("useDeleteManualAssociation — mutation execution", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls apiFetch DELETE on the correct endpoint when mutate is invoked", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([])
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${VIDEO_ID}/entities/${ENTITY_ID_MANUAL_ONLY}/manual`,
      { method: "DELETE" }
    );
  });

  it("transitions to isSuccess after a successful DELETE", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([])
    );

    mockedApiFetch.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.isError).toBe(false);
  });

  it("transitions to isError after a failed DELETE", async () => {
    queryClient.setQueryData(
      videoEntitiesKey(VIDEO_ID),
      makeVideoEntitiesResponse([])
    );

    mockedApiFetch.mockRejectedValueOnce({
      type: "server",
      message: "Not Found",
      status: 404,
    });

    const { result } = renderHook(() => useDeleteManualAssociation(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ videoId: VIDEO_ID, entityId: ENTITY_ID_MANUAL_ONLY });
    });

    await waitFor(() => result.current.isError);

    expect(result.current.isError).toBe(true);
    expect(result.current.isSuccess).toBe(false);
  });
});
