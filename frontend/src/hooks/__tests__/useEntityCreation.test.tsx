/**
 * Tests for entity creation hooks in hooks/useEntityMentions.ts.
 *
 * Coverage:
 * - useClassifyTag: calls classifyTag() and invalidates entities, entitySearch,
 *   canonical-tags caches on success
 * - useCreateEntity: calls createEntity() and invalidates entities, entitySearch
 *   caches on success — canonical-tags is intentionally NOT invalidated
 * - useCheckDuplicate: query enabled/disabled logic based on name length and
 *   entityType presence
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import {
  classifyTag,
  checkEntityDuplicate,
  createEntity,
} from "../../api/entityMentions";
import {
  useClassifyTag,
  useCreateEntity,
  useCheckDuplicate,
} from "../useEntityMentions";
import type {
  ClassifyTagResponse,
  CreateEntityResponse,
  DuplicateCheckResult,
} from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/entityMentions", () => ({
  classifyTag: vi.fn(),
  checkEntityDuplicate: vi.fn(),
  createEntity: vi.fn(),
  // Other exports that may be imported transitively — provide no-op stubs.
  fetchVideoEntities: vi.fn(),
  fetchEntityVideos: vi.fn(),
  fetchEntities: vi.fn(),
  createManualAssociation: vi.fn(),
  deleteManualAssociation: vi.fn(),
  searchEntities: vi.fn(),
  createEntityAlias: vi.fn(),
  fetchEntityDetail: vi.fn(),
  addExclusionPattern: vi.fn(),
  removeExclusionPattern: vi.fn(),
  fetchPhoneticMatches: vi.fn(),
}));

const mockedClassifyTag = vi.mocked(classifyTag);
const mockedCreateEntity = vi.mocked(createEntity);
const mockedCheckEntityDuplicate = vi.mocked(checkEntityDuplicate);

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

function makeClassifyTagResponse(
  overrides: Partial<ClassifyTagResponse> = {}
): ClassifyTagResponse {
  return {
    entity_id: "ent-uuid-001",
    canonical_name: "React",
    entity_type: "organization",
    description: "JavaScript UI library",
    alias_count: 1,
    entity_created: true,
    operation_id: "op-uuid-001",
    ...overrides,
  };
}

function makeCreateEntityResponse(
  overrides: Partial<CreateEntityResponse> = {}
): CreateEntityResponse {
  return {
    entity_id: "ent-uuid-002",
    canonical_name: "Marie Curie",
    entity_type: "person",
    description: "Nobel Prize-winning physicist",
    alias_count: 0,
    ...overrides,
  };
}

function makeDuplicateCheckResult(
  overrides: Partial<DuplicateCheckResult> = {}
): DuplicateCheckResult {
  return {
    is_duplicate: false,
    existing_entity: null,
    ...overrides,
  };
}

// ===========================================================================
// useClassifyTag
// ===========================================================================

describe("useClassifyTag — mutation execution", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls classifyTag with the provided variables when mutate is invoked", async () => {
    mockedClassifyTag.mockResolvedValueOnce(makeClassifyTagResponse());

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        normalized_form: "React",
        entity_type: "organization",
        description: "JavaScript UI library",
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedClassifyTag).toHaveBeenCalledOnce();
    expect(mockedClassifyTag).toHaveBeenCalledWith({
      normalized_form: "React",
      entity_type: "organization",
      description: "JavaScript UI library",
    });
  });

  it("transitions to isSuccess and returns the API response data on success", async () => {
    const response = makeClassifyTagResponse({ entity_created: true });
    mockedClassifyTag.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.entity_created).toBe(true);
  });

  it("transitions to isError when the API call fails", async () => {
    mockedClassifyTag.mockRejectedValueOnce({
      type: "server",
      message: "Conflict",
      status: 409,
    });

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isError);

    expect(result.current.isError).toBe(true);
    expect(result.current.isSuccess).toBe(false);
  });
});

describe("useClassifyTag — onSuccess cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates the entities cache after success", async () => {
    mockedClassifyTag.mockResolvedValueOnce(makeClassifyTagResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entities"] })
    );
  });

  it("invalidates the entitySearch cache after success", async () => {
    mockedClassifyTag.mockResolvedValueOnce(makeClassifyTagResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entitySearch"] })
    );
  });

  it("invalidates the canonical-tags cache after success", async () => {
    mockedClassifyTag.mockResolvedValueOnce(makeClassifyTagResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["canonical-tags"] })
    );
  });

  it("invalidates all three caches (entities, entitySearch, canonical-tags) on a single success", async () => {
    mockedClassifyTag.mockResolvedValueOnce(makeClassifyTagResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "TypeScript", entity_type: "product" });
    });

    await waitFor(() => result.current.isSuccess);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );

    expect(invalidatedKeys).toContainEqual(["entities"]);
    expect(invalidatedKeys).toContainEqual(["entitySearch"]);
    expect(invalidatedKeys).toContainEqual(["canonical-tags"]);
  });

  it("does NOT invalidate canonical-tags when the mutation fails", async () => {
    mockedClassifyTag.mockRejectedValueOnce({
      type: "server",
      message: "Internal Server Error",
      status: 500,
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useClassifyTag(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ normalized_form: "React", entity_type: "organization" });
    });

    await waitFor(() => result.current.isError);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );

    expect(invalidatedKeys).not.toContainEqual(["canonical-tags"]);
  });
});

// ===========================================================================
// useCreateEntity
// ===========================================================================

describe("useCreateEntity — mutation execution", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("calls createEntity with the provided payload when mutate is invoked", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse());

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        name: "Marie Curie",
        entity_type: "person",
        description: "Nobel Prize-winning physicist",
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedCreateEntity).toHaveBeenCalledOnce();
    expect(mockedCreateEntity).toHaveBeenCalledWith({
      name: "Marie Curie",
      entity_type: "person",
      description: "Nobel Prize-winning physicist",
    });
  });

  it("transitions to isSuccess and returns the API response data on success", async () => {
    const response = makeCreateEntityResponse({ canonical_name: "Marie Curie" });
    mockedCreateEntity.mockResolvedValueOnce(response);

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.canonical_name).toBe("Marie Curie");
  });

  it("transitions to isError when the API call fails", async () => {
    mockedCreateEntity.mockRejectedValueOnce({
      type: "server",
      message: "Conflict — entity already exists",
      status: 409,
    });

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isError);

    expect(result.current.isError).toBe(true);
    expect(result.current.isSuccess).toBe(false);
  });

  it("forwards optional aliases array to createEntity", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse({ alias_count: 2 }));

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({
        name: "Marie Curie",
        entity_type: "person",
        aliases: ["Maria Sklodowska-Curie", "Mme Curie"],
      });
    });

    await waitFor(() => result.current.isSuccess);

    expect(mockedCreateEntity).toHaveBeenCalledWith(
      expect.objectContaining({ aliases: ["Maria Sklodowska-Curie", "Mme Curie"] })
    );
  });
});

describe("useCreateEntity — onSuccess cache invalidation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("invalidates the entities cache after success", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entities"] })
    );
  });

  it("invalidates the entitySearch cache after success", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isSuccess);

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entitySearch"] })
    );
  });

  it("does NOT invalidate canonical-tags after success — standalone entities are not linked to the tag taxonomy", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isSuccess);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );

    expect(invalidatedKeys).not.toContainEqual(["canonical-tags"]);
  });

  it("invalidates exactly entities and entitySearch — no other caches", async () => {
    mockedCreateEntity.mockResolvedValueOnce(makeCreateEntityResponse());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateEntity(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ name: "Marie Curie", entity_type: "person" });
    });

    await waitFor(() => result.current.isSuccess);

    // Exactly two invalidation calls
    expect(invalidateSpy).toHaveBeenCalledTimes(2);

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual(["entities"]);
    expect(invalidatedKeys).toContainEqual(["entitySearch"]);
  });
});

// ===========================================================================
// useCheckDuplicate
// ===========================================================================

describe("useCheckDuplicate — enabled/disabled logic", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    // Use resetAllMocks (not just clearAllMocks) so that any unconsumed
    // mockResolvedValueOnce entries from previous tests are flushed from
    // the implementation queue before the next test sets up its own mock.
    vi.resetAllMocks();
  });

  it("does not fetch when name is empty", () => {
    const { result } = renderHook(
      () => useCheckDuplicate("", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("does not fetch when name has fewer than 2 characters", () => {
    const { result } = renderHook(
      () => useCheckDuplicate("A", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("does not fetch when name is exactly 1 character", () => {
    renderHook(
      () => useCheckDuplicate("X", "organization"),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
  });

  it("does not fetch when entityType is empty string even if name is long enough", () => {
    const { result } = renderHook(
      () => useCheckDuplicate("Marie Curie", ""),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("does not fetch when name is only whitespace (trims to < 2 chars)", () => {
    renderHook(
      () => useCheckDuplicate("  ", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
  });

  it("fires the query when name has at least 2 non-whitespace characters and entityType is present", async () => {
    mockedCheckEntityDuplicate.mockResolvedValueOnce(makeDuplicateCheckResult());

    const { result } = renderHook(
      () => useCheckDuplicate("Ma", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedCheckEntityDuplicate).toHaveBeenCalledOnce();
  });

  it("fires the query when name has exactly 2 characters and entityType is present", async () => {
    mockedCheckEntityDuplicate.mockResolvedValueOnce(makeDuplicateCheckResult());

    const { result } = renderHook(
      () => useCheckDuplicate("Ma", "organization"),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedCheckEntityDuplicate).toHaveBeenCalledOnce();
  });

  it("calls checkEntityDuplicate with the trimmed name and entityType", async () => {
    mockedCheckEntityDuplicate.mockResolvedValueOnce(makeDuplicateCheckResult());

    const { result } = renderHook(
      () => useCheckDuplicate("  Marie Curie  ", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedCheckEntityDuplicate).toHaveBeenCalledWith(
      "Marie Curie",
      "person",
      expect.any(AbortSignal)
    );
  });

  it("returns is_duplicate=true and existing_entity when a duplicate is found", async () => {
    const duplicateResult = makeDuplicateCheckResult({
      is_duplicate: true,
      existing_entity: {
        entity_id: "ent-existing-001",
        canonical_name: "Marie Curie",
        entity_type: "person",
        description: "Physicist",
      },
    });
    mockedCheckEntityDuplicate.mockResolvedValueOnce(duplicateResult);

    const { result } = renderHook(
      () => useCheckDuplicate("Marie Curie", "person"),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.data).toEqual(duplicateResult));

    expect(result.current.data?.is_duplicate).toBe(true);
    expect(result.current.data?.existing_entity?.entity_id).toBe("ent-existing-001");
  });

  it("returns is_duplicate=false and existing_entity=null when no duplicate exists", async () => {
    const nodupeResult = makeDuplicateCheckResult();
    mockedCheckEntityDuplicate.mockResolvedValueOnce(nodupeResult);

    const { result } = renderHook(
      () => useCheckDuplicate("New Entity Name", "place"),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.data).toEqual(nodupeResult));

    expect(result.current.data?.is_duplicate).toBe(false);
    expect(result.current.data?.existing_entity).toBeNull();
  });

  it("re-fires the query when name changes from short to long enough", async () => {
    mockedCheckEntityDuplicate.mockResolvedValue(makeDuplicateCheckResult());

    const { result, rerender } = renderHook(
      ({ name }: { name: string }) => useCheckDuplicate(name, "person"),
      {
        wrapper: createWrapper(queryClient),
        initialProps: { name: "A" },
      }
    );

    // Short name — query must be disabled
    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");

    // Extend to 2+ characters — query must fire
    rerender({ name: "Al" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockedCheckEntityDuplicate).toHaveBeenCalledOnce();
  });

  it("does not re-fire the query when name changes but stays below the 2-char threshold", () => {
    const { rerender } = renderHook(
      ({ name }: { name: string }) => useCheckDuplicate(name, "person"),
      {
        wrapper: createWrapper(queryClient),
        initialProps: { name: "" },
      }
    );

    rerender({ name: "A" });

    expect(mockedCheckEntityDuplicate).not.toHaveBeenCalled();
  });

  it("becomes idle again when entityType is cleared after previously being set", async () => {
    mockedCheckEntityDuplicate.mockResolvedValue(makeDuplicateCheckResult());

    const { result, rerender } = renderHook(
      ({ entityType }: { entityType: string }) =>
        useCheckDuplicate("Marie Curie", entityType),
      {
        wrapper: createWrapper(queryClient),
        initialProps: { entityType: "person" },
      }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedCheckEntityDuplicate).toHaveBeenCalledOnce();

    // Clear entity type — query should disable
    rerender({ entityType: "" });

    // After clearing, the query is no longer enabled
    expect(result.current.fetchStatus).toBe("idle");
  });
});
