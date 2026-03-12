/**
 * TanStack Query hooks for entity mention endpoints.
 *
 * Exports:
 * - useVideoEntities(videoId) — fetches entities for a video
 * - useEntityVideos(entityId, params) — infinite-scroll videos for an entity
 */

import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import {
  fetchVideoEntities,
  fetchEntityVideos,
  fetchEntities,
} from "../api/entityMentions";
import type {
  VideoEntitySummary,
  EntityVideoResult,
  EntityListItem,
  EntityPaginationMeta,
  FetchEntityVideosParams,
  FetchEntitiesParams,
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
    queryKey: ["entity-videos", entityId, params.language_code ?? null, limit],
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
