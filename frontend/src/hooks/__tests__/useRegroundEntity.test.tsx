/**
 * Tests for useRegroundEntity (Feature 073, US1, T009).
 *
 * Coverage:
 * - Calls regroundEntity(entityId, data) with the exact variables passed to `mutate`
 * - On success, invalidates BOTH `["entity-detail", entityId]` and `["entities"]`
 * - Surfaces a mutation error via isError/error without throwing
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { regroundEntity } from "../../api/entityMentions";
import { useRegroundEntity } from "../useRegroundEntity";
import type { EntityDetail } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  regroundEntity: vi.fn(),
}));

const mockedRegroundEntity = vi.mocked(regroundEntity);

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

function makeEntityDetail(overrides: Partial<EntityDetail> = {}): EntityDetail {
  return {
    entity_id: "ent-00000000-0000-0000-0000-000000000001",
    canonical_name: "Test Person",
    entity_type: "person",
    description: "curator-confirmed text",
    status: "active",
    mention_count: 3,
    video_count: 2,
    by_source: { manual: 0, transcript: 2, title: 0, description: 0, tag: 0 },
    aliases: [],
    exclusion_patterns: [],
    enrichment: { grounded: true, properties: {}, identifiers: [] },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useRegroundEntity", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls regroundEntity with the entityId and body from mutate variables", async () => {
    mockedRegroundEntity.mockResolvedValueOnce(makeEntityDetail());

    const { result } = renderHook(() => useRegroundEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: "ent-00000000-0000-0000-0000-000000000001",
        data: {
          approved_identifier: { source: "wikidata", id: "Q00000042" },
          description: "curator-confirmed text",
        },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedRegroundEntity).toHaveBeenCalledWith(
      "ent-00000000-0000-0000-0000-000000000001",
      {
        approved_identifier: { source: "wikidata", id: "Q00000042" },
        description: "curator-confirmed text",
      }
    );
  });

  it("invalidates the entity-detail cache for the re-grounded entity after success", async () => {
    mockedRegroundEntity.mockResolvedValueOnce(makeEntityDetail());
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRegroundEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: "ent-00000000-0000-0000-0000-000000000001",
        data: { approved_identifier: { source: "wikidata", id: "Q00000042" } },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["entity-detail", "ent-00000000-0000-0000-0000-000000000001"],
      })
    );
  });

  it("invalidates the entities list cache after success", async () => {
    mockedRegroundEntity.mockResolvedValueOnce(makeEntityDetail());
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRegroundEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: "ent-00000000-0000-0000-0000-000000000001",
        data: { approved_identifier: { source: "wikidata", id: "Q00000042" } },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entities"] })
    );
  });

  it("invalidates both entity-detail and entities on a single success", async () => {
    mockedRegroundEntity.mockResolvedValueOnce(makeEntityDetail());
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRegroundEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: "ent-00000000-0000-0000-0000-000000000001",
        data: { approved_identifier: { source: "wikidata", id: "Q00000042" } },
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });

  it("surfaces a failure via isError without throwing", async () => {
    mockedRegroundEntity.mockRejectedValueOnce({
      type: "server",
      message: "Entity not found.",
      status: 404,
    });

    const { result } = renderHook(() => useRegroundEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        entityId: "ent-00000000-0000-0000-0000-000000000001",
        data: { approved_identifier: { source: "wikidata", id: "Q00000042" } },
      });
    });

    await waitFor(() => result.current.isError);

    expect(result.current.isSuccess).toBe(false);
  });
});
