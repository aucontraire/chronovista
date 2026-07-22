/**
 * TanStack Query hooks for entity mention endpoints.
 *
 * Exports:
 * - useVideoEntities(videoId) — fetches entities for a video
 * - useEntityVideos(entityId, params) — infinite-scroll videos for an entity
 */

import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchVideoEntities,
  fetchEntityVideos,
  fetchEntities,
  createManualAssociation,
  deleteManualAssociation,
  classifyTag,
  checkEntityDuplicate,
  createEntity,
  updateEntity,
  scanEntity,
  scanVideoEntities,
  getScanJob,
} from "../api/entityMentions";
import type {
  VideoEntitySummary,
  VideoEntitiesResponse,
  EntityVideoResult,
  EntityListItem,
  EntityDetail,
  EntityPaginationMeta,
  ManualAssociationResponse,
  ClassifyTagResponse,
  DuplicateCheckResult,
  FetchEntityVideosParams,
  FetchEntitiesParams,
  CreateEntityRequest,
  CreateEntityResponse,
  UpdateEntityRequest,
  ScanRequest,
  ScanResultResponse,
  ScanJob,
} from "../api/entityMentions";
import type { ApiError } from "../types/video";

// ---------------------------------------------------------------------------
// useVideoEntities
// ---------------------------------------------------------------------------

interface UseVideoEntitiesReturn {
  /** Entities mentioned in the video, sorted by mention_count DESC */
  entities: VideoEntitySummary[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error, if any */
  error: ApiError | null;
}

/**
 * Hook that fetches the entity mention summary for a single video.
 *
 * Returns an empty array when no mentions exist (backend returns `{data: []}`).
 * The query is disabled until `videoId` is truthy.
 *
 * @param videoId - YouTube video ID
 * @param languageCode - Optional BCP-47 language code filter
 * @returns Entity list, loading state, and error state
 *
 * @example
 * ```tsx
 * const { entities, isLoading } = useVideoEntities("dQw4w9WgXcQ");
 * ```
 */
export function useVideoEntities(
  videoId: string,
  languageCode?: string
): UseVideoEntitiesReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["video-entities", videoId, languageCode ?? null],
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ signal }) => fetchVideoEntities(videoId, languageCode, signal),
    enabled: Boolean(videoId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,
  });

  return {
    entities: data?.data ?? [],
    isLoading,
    isError,
    error: (error as ApiError | null) ?? null,
  };
}

// ---------------------------------------------------------------------------
// useEntityVideos (infinite scroll)
// ---------------------------------------------------------------------------

const DEFAULT_PAGE_SIZE = 20;
const INTERSECTION_THRESHOLD = 0.8;

interface UseEntityVideosReturn {
  /** All loaded video results flattened */
  videos: EntityVideoResult[];
  /** Total number of videos available */
  total: number | null;
  /** Pagination metadata from the last page */
  pagination: EntityPaginationMeta | null;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error, if any */
  error: ApiError | null;
  /** Whether more pages are available */
  hasNextPage: boolean;
  /** Whether a next page is currently being fetched */
  isFetchingNextPage: boolean;
  /** Manually fetch the next page */
  fetchNextPage: () => void;
  /** Ref to attach to the sentinel element for auto-scroll loading */
  loadMoreRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Hook that fetches videos mentioning a given entity with infinite scroll.
 *
 * Attaches an IntersectionObserver to `loadMoreRef` for automatic next-page
 * loading when the user scrolls near the bottom of the list.
 *
 * @param entityId - UUID of the named entity
 * @param params - Optional filter params (language_code, limit)
 * @returns Video list, pagination state, loading flags, and sentinel ref
 *
 * @example
 * ```tsx
 * const { videos, loadMoreRef } = useEntityVideos(entityId);
 * return (
 *   <ul>
 *     {videos.map(v => <li key={v.video_id}>{v.video_title}</li>)}
 *   </ul>
 *   <div ref={loadMoreRef} />
 * );
 * ```
 */
export function useEntityVideos(
  entityId: string,
  params: Omit<FetchEntityVideosParams, "offset"> = {}
): UseEntityVideosReturn {
  const limit = params.limit ?? DEFAULT_PAGE_SIZE;
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const {
    data,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: ["entity-videos", entityId, params.language_code ?? null, params.source ?? null, limit],
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ pageParam, signal }) =>
      fetchEntityVideos(entityId, {
        ...params,
        limit,
        offset: pageParam,
      }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination.has_more) return undefined;
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    enabled: Boolean(entityId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  const videos = data?.pages.flatMap((p) => p.data) ?? [];
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination.total ?? null;
  const pagination = lastPage?.pagination ?? null;

  const handleIntersect = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  useEffect(() => {
    const element = loadMoreRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          handleIntersect();
        }
      },
      {
        threshold: INTERSECTION_THRESHOLD,
        rootMargin: "100px",
      }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [handleIntersect]);

  return {
    videos,
    total,
    pagination,
    isLoading,
    isError,
    error: (error as ApiError | null) ?? null,
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    fetchNextPage: () => void fetchNextPage(),
    loadMoreRef,
  };
}

// ---------------------------------------------------------------------------
// useEntities (infinite scroll entity list)
// ---------------------------------------------------------------------------

interface UseEntitiesReturn {
  /** All loaded entity items flattened across pages */
  entities: EntityListItem[];
  /** Total number of entities available */
  total: number | null;
  /** Number of entities currently loaded */
  loadedCount: number;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether any error occurred */
  isError: boolean;
  /** The error, if any */
  error: ApiError | null;
  /** Whether more pages are available */
  hasNextPage: boolean;
  /** Whether a next page is currently being fetched */
  isFetchingNextPage: boolean;
  /** Function to manually fetch the next page */
  fetchNextPage: () => void;
  /** Function to retry after an error */
  retry: () => void;
  /** Ref to attach to the sentinel element for auto-scroll loading */
  loadMoreRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Hook that fetches the paginated entity list with infinite scroll.
 *
 * Attaches an IntersectionObserver to `loadMoreRef` for automatic next-page
 * loading when the user scrolls near the bottom of the list.
 *
 * @param params - Optional filter/sort params (type, has_mentions, search, sort, limit)
 * @returns Entity list, pagination state, loading flags, and sentinel ref
 *
 * @example
 * ```tsx
 * const { entities, loadMoreRef } = useEntities({ type: "person", sort: "mentions" });
 * return (
 *   <>
 *     {entities.map(e => <EntityCard key={e.entity_id} entity={e} />)}
 *     <div ref={loadMoreRef} />
 *   </>
 * );
 * ```
 */
export function useEntities(
  params: Omit<FetchEntitiesParams, "offset"> = {}
): UseEntitiesReturn {
  const limit = params.limit ?? DEFAULT_PAGE_SIZE;
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const {
    data,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: [
      "entities",
      params.type ?? null,
      params.has_mentions ?? null,
      params.search ?? null,
      params.sort ?? null,
      limit,
    ],
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ pageParam, signal }) =>
      fetchEntities({
        ...params,
        limit,
        offset: pageParam,
      }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination.has_more) return undefined;
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  const entities = data?.pages.flatMap((p) => p.data) ?? [];
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination.total ?? null;
  const loadedCount = entities.length;

  const handleIntersect = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  useEffect(() => {
    const element = loadMoreRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          handleIntersect();
        }
      },
      {
        threshold: INTERSECTION_THRESHOLD,
        rootMargin: "100px",
      }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [handleIntersect]);

  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);

  return {
    entities,
    total,
    loadedCount,
    isLoading,
    isError,
    error: (error as ApiError | null) ?? null,
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    fetchNextPage: () => void fetchNextPage(),
    retry,
    loadMoreRef,
  };
}

// ---------------------------------------------------------------------------
// useCreateManualAssociation
// ---------------------------------------------------------------------------

/** Variables passed to the manual association mutation. */
export interface CreateManualAssociationVariables {
  /** YouTube video ID */
  videoId: string;
  /** Named entity UUID */
  entityId: string;
}

/**
 * Mutation hook for creating a manual entity–video association.
 *
 * On success, invalidates the caches for:
 * - `videoEntities` (so the EntityMentionsPanel refreshes)
 * - `entitySearch`  (so is_linked flags update in autocomplete)
 * - `entity-videos` (so the entity detail page refreshes)
 *
 * Error handling is left to the caller — use `mutation.isError` and
 * `mutation.error` to display inline error messages.
 *
 * @returns UseMutationResult with `mutate({ videoId, entityId })`
 *
 * @example
 * ```tsx
 * const mutation = useCreateManualAssociation();
 * mutation.mutate({ videoId: "dQw4w9WgXcQ", entityId: "ent-uuid" });
 * ```
 */
export function useCreateManualAssociation() {
  const queryClient = useQueryClient();

  return useMutation<ManualAssociationResponse, ApiError, CreateManualAssociationVariables>({
    mutationFn: ({ videoId, entityId }: CreateManualAssociationVariables) =>
      createManualAssociation(videoId, entityId),

    onSuccess: (_data, variables) => {
      // Invalidate caches that depend on entity–video associations.
      void queryClient.invalidateQueries({
        queryKey: ["video-entities", variables.videoId],
      });
      void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-videos"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useDeleteManualAssociation
// ---------------------------------------------------------------------------

/** Variables passed to the delete manual association mutation. */
export interface DeleteManualAssociationVariables {
  videoId: string;
  entityId: string;
}

/**
 * Mutation hook for deleting a manual entity-video association.
 *
 * Uses optimistic updates to immediately reflect the deletion in the
 * `video-entities` cache so the EntityMentionsPanel updates without waiting
 * for a network refetch.  All queries whose key starts with
 * `["video-entities", videoId]` are updated in-place:
 * - Manual-only entity (mention_count === 0): removed from the list.
 * - Multi-source entity (mention_count > 0): `has_manual` set to false and
 *   "manual" removed from `sources`.
 *
 * On success, also invalidates caches for:
 * - `entity-videos` (entity detail page refreshes)
 * - `entity-detail` (entity detail header refreshes)
 * - `entitySearch` (is_linked flags update in autocomplete)
 *
 * On error, rolls back the optimistic update to restore previous state.
 *
 * @returns UseMutationResult with `mutate({ videoId, entityId })`
 *
 * @example
 * ```tsx
 * const mutation = useDeleteManualAssociation();
 * mutation.mutate({ videoId: "dQw4w9WgXcQ", entityId: "ent-uuid" });
 * ```
 */
export function useDeleteManualAssociation() {
  const queryClient = useQueryClient();

  return useMutation<
    void,
    ApiError,
    DeleteManualAssociationVariables,
    { snapshots: Array<[readonly unknown[], VideoEntitiesResponse | undefined]> }
  >({
    mutationFn: ({ videoId, entityId }) =>
      deleteManualAssociation(videoId, entityId),

    onMutate: async (variables) => {
      // Cancel any in-flight refetches for this video's entities so they don't
      // overwrite the optimistic update we're about to apply.
      await queryClient.cancelQueries({
        queryKey: ["video-entities", variables.videoId],
      });

      // Snapshot all cached variants of the video-entities query (may include
      // queries with different languageCode values as the third key element).
      const matchedQueries = queryClient.getQueriesData<VideoEntitiesResponse>({
        queryKey: ["video-entities", variables.videoId],
      });

      // Apply optimistic update to every matching cache entry.
      for (const [queryKey, previousData] of matchedQueries) {
        if (!previousData) continue;

        const updatedEntities = previousData.data
          // Remove manual-only entities from the list.
          .filter(
            (entity) =>
              !(entity.entity_id === variables.entityId && entity.mention_count === 0)
          )
          // For multi-source entities: clear has_manual and remove "manual" from sources.
          .map((entity) => {
            if (entity.entity_id !== variables.entityId) return entity;
            return {
              ...entity,
              has_manual: false,
              sources: entity.sources.filter((s) => s !== "manual"),
            };
          });

        queryClient.setQueryData<VideoEntitiesResponse>(queryKey, {
          ...previousData,
          data: updatedEntities,
        });
      }

      // Return the snapshots so we can roll back on error.
      return {
        snapshots: matchedQueries as Array<
          [readonly unknown[], VideoEntitiesResponse | undefined]
        >,
      };
    },

    onError: (_err, _variables, context) => {
      // Roll back the optimistic update on failure.
      if (context?.snapshots) {
        for (const [queryKey, previousData] of context.snapshots) {
          queryClient.setQueryData<VideoEntitiesResponse>(queryKey, previousData);
        }
      }
    },

    onSuccess: (_data, variables) => {
      // The optimistic update in onMutate already applied the correct
      // post-deletion state to the cache.  We intentionally mark video-entities
      // as stale WITHOUT triggering an immediate background refetch (refetchType:
      // 'none') so the refetch cannot race the optimistic update and overwrite it
      // with a potentially-stale server response.  TanStack Query will refetch on
      // the next cache-invalidating event (e.g. component remount, window focus).
      void queryClient.invalidateQueries({
        queryKey: ["video-entities", variables.videoId],
        refetchType: "none",
      });
      // These caches were NOT optimistically updated, so an immediate refetch is
      // correct and desired — they need fresh server data to reflect the deletion.
      void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-videos"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-detail"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useClassifyTag
// ---------------------------------------------------------------------------

/** Variables passed to the classify tag mutation. */
export interface ClassifyTagVariables {
  /** The canonical name / normalized tag text to classify */
  normalized_form: string;
  /** Entity type (e.g. "person", "organization", "place") */
  entity_type: string;
  /** Optional human-readable description */
  description?: string;
  /**
   * Optional entity display name, stored verbatim (no re-casing). Falls back
   * to the backend's auto-derived (title-cased) name when omitted
   * (Feature 057, FR-008/FR-009/FR-010).
   */
  display_name?: string;
}

/**
 * Mutation hook for classifying a raw tag as a named entity.
 *
 * On success, invalidates caches for:
 * - `entities`       (entity list page refreshes)
 * - `entitySearch`   (autocomplete results refresh)
 * - `canonical-tags` (canonical tag data refreshes)
 *
 * Error handling is left to the caller — use `mutation.isError` and
 * `mutation.error` to display inline error messages.
 *
 * @returns UseMutationResult with `mutate({ normalized_form, entity_type, description? })`
 *
 * @example
 * ```tsx
 * const mutation = useClassifyTag();
 * mutation.mutate({ normalized_form: "React", entity_type: "organization" });
 * ```
 */
export function useClassifyTag() {
  const queryClient = useQueryClient();

  return useMutation<ClassifyTagResponse, ApiError, ClassifyTagVariables>({
    mutationFn: (variables: ClassifyTagVariables) => classifyTag(variables),

    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
      void queryClient.invalidateQueries({ queryKey: ["canonical-tags"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useCreateEntity
// ---------------------------------------------------------------------------

/**
 * Mutation hook for creating a standalone named entity.
 *
 * On success, invalidates caches for:
 * - `entities`     (entity list page refreshes)
 * - `entitySearch` (autocomplete results refresh)
 *
 * Note: `canonical-tags` is intentionally NOT invalidated here because
 * standalone entities are not linked to the tag taxonomy.
 *
 * Error handling is left to the caller — use `mutation.isError` and
 * `mutation.error` to display inline error messages.
 *
 * @returns UseMutationResult with `mutate(data: CreateEntityRequest)`
 *
 * @example
 * ```tsx
 * const mutation = useCreateEntity();
 * mutation.mutate({ name: "Marie Curie", entity_type: "person" });
 * ```
 */
export function useCreateEntity() {
  const queryClient = useQueryClient();

  return useMutation<CreateEntityResponse, ApiError, CreateEntityRequest>({
    mutationFn: (data) => createEntity(data),

    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
      // Note: NO ["canonical-tags"] invalidation — standalone entities aren't linked to tags
    },
  });
}

// ---------------------------------------------------------------------------
// useUpdateEntity
// ---------------------------------------------------------------------------

/** Variables passed to the entity update mutation. */
export interface UpdateEntityVariables {
  /** UUID of the named entity to update */
  entityId: string;
  /** Fields to update (at least one of canonical_name/description) */
  data: UpdateEntityRequest;
}

/**
 * Mutation hook for updating a named entity's display name and/or
 * description (Feature 057). Never touches the tag(s) the entity is linked
 * to.
 *
 * On success, invalidates caches for:
 * - `entity-detail` (entity detail header/description refreshes)
 * - `entities`      (entity list page refreshes)
 * - `entity-videos` (entity's videos view refreshes, e.g. entity-name
 *   highlighting in description context snippets)
 *
 * Error handling is left to the caller — use `mutation.isError` / the
 * per-call `onError` callback to display inline 400/404/409 errors while
 * keeping the editor open with the user's input preserved (FR-022).
 *
 * @returns UseMutationResult with `mutate({ entityId, data })`
 *
 * @example
 * ```tsx
 * const mutation = useUpdateEntity();
 * mutation.mutate({ entityId, data: { canonical_name: "OpenAI" } });
 * ```
 */
export function useUpdateEntity() {
  const queryClient = useQueryClient();

  return useMutation<EntityDetail, ApiError, UpdateEntityVariables>({
    mutationFn: ({ entityId, data }) => updateEntity(entityId, data),

    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", variables.entityId],
      });
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({
        queryKey: ["entity-videos", variables.entityId],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// useCheckDuplicate
// ---------------------------------------------------------------------------

/**
 * Query hook that checks whether a named entity with the given name and type
 * already exists in the database.
 *
 * The query is disabled until `name` has at least 2 non-whitespace characters
 * and `entityType` is non-empty, avoiding unnecessary requests while the user
 * is still typing.
 *
 * @param name - Candidate canonical name (query fires when trimmed length >= 2)
 * @param entityType - Entity type string (e.g. "person", "organization")
 * @returns TanStack Query result containing DuplicateCheckResult
 *
 * @example
 * ```tsx
 * const { data } = useCheckDuplicate(nameInput, selectedType);
 * if (data?.is_duplicate) {
 *   // show warning with data.existing_entity
 * }
 * ```
 */
export function useCheckDuplicate(name: string, entityType: string) {
  const enabled = name.trim().length >= 2 && entityType !== "";

  return useQuery<DuplicateCheckResult, ApiError>({
    queryKey: ["checkDuplicate", name.trim(), entityType],
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ signal }) => checkEntityDuplicate(name.trim(), entityType, signal),
    enabled,
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Scan job polling (shared launch→poll flow for entity/video scans)
// ---------------------------------------------------------------------------
//
// Entity-mention scans are launched as an async background job on the
// backend (202) rather than blocking the request for the scan's full
// duration, which can exceed the client timeout on large corpora. The flow
// is:
//   1. `mutate()` POSTs to launch the scan and receives a job_id.
//   2. A polling query fetches GET /scan-jobs/{job_id} every 2s while the
//      job's status is "running".
//   3. Once the job reaches a terminal status, the relevant caches are
//      invalidated (once per job) and the caller's onSuccess/onError
//      callback fires with a shape matching the old synchronous response.

/** Poll interval, in milliseconds, while a scan job is running. */
const SCAN_POLL_INTERVAL_MS = 2000;

/** Query key for a scan job's polled status. */
function scanJobKey(jobId: string | null) {
  return ["scan-job", jobId] as const;
}

/**
 * Polls GET /scan-jobs/{jobId} every `SCAN_POLL_INTERVAL_MS` while the job's
 * status is "running". Disabled when `jobId` is null.
 */
function useScanJobPoll(jobId: string | null) {
  return useQuery<ScanJob, ApiError>({
    queryKey: scanJobKey(jobId),
    // FR-004/FR-005: TanStack Query provides signal; cancelled on key change or unmount.
    queryFn: ({ signal }) => getScanJob(jobId as string, signal),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ? SCAN_POLL_INTERVAL_MS : false;
    },
    staleTime: SCAN_POLL_INTERVAL_MS,
    gcTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** Callbacks invoked once a launched scan job reaches a terminal status. */
export interface ScanFlowCallbacks {
  /** Fired when the job succeeds; `data` mirrors the pre-async ScanResultResponse shape. */
  onSuccess?: (data: ScanResultResponse) => void;
  /** Fired when the job fails, or when the launch request itself fails (e.g. 404/409). */
  onError?: (error: ApiError) => void;
}

/** Public shape returned by useScanEntity / useScanVideoEntities. */
export interface UseScanFlowResult<TVariables> {
  /** Launches the scan; `callbacks` fire once the job reaches a terminal status. */
  mutate: (variables: TVariables, callbacks?: ScanFlowCallbacks) => void;
  /** True from the moment `mutate` is called until the job reaches a terminal status. */
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  /** The launch error, or a synthesized ApiError from a failed job's `error` string. */
  error: ApiError | null;
  /** The terminal scan result, once the job has succeeded. */
  data: ScanResultResponse | undefined;
  /** Resets the flow back to idle (e.g. before retrying). */
  reset: () => void;
}

/**
 * Internal factory shared by useScanEntity and useScanVideoEntities.
 *
 * Wraps a launch mutation and a job-status polling query behind a
 * mutation-like interface so call sites barely change from the previous
 * synchronous mutation: `mutate(variables, { onSuccess, onError })`,
 * `isPending`, `data`, `error`.
 *
 * @param launch - Fetcher that POSTs the scan request and returns the job_id
 * @param getInvalidationKeys - Given the job's target_id, returns the query
 *   keys to invalidate once the job succeeds
 */
function useScanJobFlow<TVariables>(
  launch: (variables: TVariables) => Promise<ScanJob>,
  getInvalidationKeys: (targetId: string) => readonly (readonly unknown[])[]
): UseScanFlowResult<TVariables> {
  const queryClient = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const callbacksRef = useRef<ScanFlowCallbacks | null>(null);
  // Guards against firing the terminal callback/invalidation more than once
  // for the same job (the poll query can re-render with the same terminal
  // status multiple times).
  const settledJobIdRef = useRef<string | null>(null);

  const launchMutation = useMutation<ScanJob, ApiError, TVariables>({
    mutationFn: launch,
    onSuccess: (job) => {
      settledJobIdRef.current = null;
      setActiveJobId(job.job_id);
    },
    onError: (err) => {
      const callbacks = callbacksRef.current;
      callbacksRef.current = null;
      callbacks?.onError?.(err);
    },
  });

  const { data: job } = useScanJobPoll(activeJobId);

  useEffect(() => {
    if (!job || job.status === "running") return;
    if (activeJobId === null || settledJobIdRef.current === activeJobId) return;
    settledJobIdRef.current = activeJobId;

    const callbacks = callbacksRef.current;
    callbacksRef.current = null;

    if (job.status === "succeeded") {
      for (const queryKey of getInvalidationKeys(job.target_id)) {
        void queryClient.invalidateQueries({ queryKey: queryKey as unknown[] });
      }
      if (job.result) {
        callbacks?.onSuccess?.({ data: job.result });
      }
    } else {
      callbacks?.onError?.({
        type: "server",
        message: job.error ?? "Scan failed.",
      });
    }
  }, [job, activeJobId, queryClient, getInvalidationKeys]);

  const mutate = useCallback(
    (variables: TVariables, callbacks?: ScanFlowCallbacks) => {
      callbacksRef.current = callbacks ?? null;
      settledJobIdRef.current = null;
      setActiveJobId(null);
      launchMutation.mutate(variables);
    },
    [launchMutation]
  );

  const reset = useCallback(() => {
    setActiveJobId(null);
    settledJobIdRef.current = null;
    callbacksRef.current = null;
    launchMutation.reset();
  }, [launchMutation]);

  const isPending =
    launchMutation.isPending ||
    (activeJobId !== null && (job === undefined || job.status === "running"));
  const isSuccess = job?.status === "succeeded";
  const isError = launchMutation.isError || job?.status === "failed";
  const error: ApiError | null =
    launchMutation.error ??
    (job?.status === "failed"
      ? { type: "server", message: job.error ?? "Scan failed." }
      : null);
  const data: ScanResultResponse | undefined =
    job?.status === "succeeded" && job.result ? { data: job.result } : undefined;

  return { mutate, isPending, isSuccess, isError, error, data, reset };
}

// ---------------------------------------------------------------------------
// useScanEntity
// ---------------------------------------------------------------------------

/** Variables passed to the scan entity mutation. */
export interface ScanEntityVariables {
  /** UUID of the named entity to scan for */
  entityId: string;
  /** Optional scan parameters (language filter, dry_run, full_rescan) */
  options?: ScanRequest;
}

/**
 * Launch→poll hook that triggers an async transcript scan for a single named
 * entity across all videos, then polls the job to completion.
 *
 * The scan runs as a background job on the backend (202 response). This
 * hook polls `GET /scan-jobs/{job_id}` every 2s while the job is running and
 * resolves via the `onSuccess`/`onError` callbacks once it reaches a
 * terminal status — mirroring the ergonomics of a single long-running
 * mutation without holding the HTTP connection open.
 *
 * On success, invalidates caches for:
 * - `entity-detail` (so the entity header reflects updated mention counts)
 * - `entity-videos` (so the entity-to-videos list refreshes)
 *
 * A 409 launch error ("scan already in progress") and a failed job both
 * surface via `onError` — inspect `error.status` (409 for "already running")
 * vs. `error.message` (the job's real failure reason) to distinguish them.
 *
 * @returns `{ mutate({ entityId, options? }, { onSuccess, onError }), isPending, data, error, ... }`
 *
 * @example
 * ```tsx
 * const scan = useScanEntity();
 * scan.mutate(
 *   { entityId: "ent-uuid" },
 *   {
 *     onSuccess: (data) => console.log(data.data.mentions_found),
 *     onError: (err) => console.error(err.message),
 *   }
 * );
 * ```
 */
export function useScanEntity(): UseScanFlowResult<ScanEntityVariables> {
  const launch = useCallback(
    ({ entityId, options }: ScanEntityVariables) => scanEntity(entityId, options),
    []
  );
  const getInvalidationKeys = useCallback(
    (targetId: string) => [
      ["entity-detail", targetId],
      ["entity-videos", targetId],
    ],
    []
  );
  return useScanJobFlow(launch, getInvalidationKeys);
}

// ---------------------------------------------------------------------------
// useScanVideoEntities
// ---------------------------------------------------------------------------

/** Variables passed to the scan video entities mutation. */
export interface ScanVideoEntitiesVariables {
  /** YouTube video ID whose transcripts should be scanned */
  videoId: string;
  /** Optional scan parameters (language filter, dry_run, full_rescan) */
  options?: ScanRequest;
}

/**
 * Launch→poll hook that triggers an async entity scan across all known
 * entities for a single video's transcripts, then polls the job to
 * completion.
 *
 * See `useScanEntity` for the shared launch→poll behaviour. On success,
 * invalidates the cache for:
 * - `video-entities` (so the EntityMentionsPanel refreshes with new detections)
 *
 * @returns `{ mutate({ videoId, options? }, { onSuccess, onError }), isPending, data, error, ... }`
 *
 * @example
 * ```tsx
 * const scan = useScanVideoEntities();
 * scan.mutate({ videoId: "dQw4w9WgXcQ" }, { onSuccess: (data) => { ... } });
 * ```
 */
export function useScanVideoEntities(): UseScanFlowResult<ScanVideoEntitiesVariables> {
  const launch = useCallback(
    ({ videoId, options }: ScanVideoEntitiesVariables) =>
      scanVideoEntities(videoId, options),
    []
  );
  const getInvalidationKeys = useCallback(
    (targetId: string) => [["video-entities", targetId]],
    []
  );
  return useScanJobFlow(launch, getInvalidationKeys);
}
