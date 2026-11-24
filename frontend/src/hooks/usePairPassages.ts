/**
 * usePairPassages — paged data for the discussion-passages panel (Features 114/118).
 *
 * Infinite scroll over VIDEO-grain items (each carrying its grouped passages): each page fetches `EVIDENCE_PAGE_SIZE` videos at an
 * advancing offset, and `getNextPageParam` follows the server's offset-aware `truncated` flag — so a
 * dense pair (hundreds of videos) streams in on scroll instead of being collapsed away. Independent
 * of the connection query so the panel can arrive a moment later and degrade on its own (a backend
 * error leaves the rest of the connection view intact — FR-018). The endpoint has no 503 (it reads
 * Postgres), so there is no three-way failure classification.
 */

import { useCallback } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";

import { fetchFartherVideos, fetchPairPassages } from "../api/graph";
import type {
  FartherVideo,
  PairPassages,
  ProximityWindow,
  VideoPassages,
} from "../api/graph";

/** Query-key root of the passages query; invalidate it to refresh open panels. */
export const PAIR_PASSAGES_KEY = "pairPassages" as const;

/** Page size; matches the server default (FR-010). */
export const EVIDENCE_PAGE_SIZE = 12;

/** Page size of the "farther apart" list. */
export const FARTHER_PAGE_SIZE = 20;

/** Poll cadence while the server is still recomputing some transcripts (FR-015c). */
export const PENDING_REFETCH_MS = 3000;

/** Refetch every 3 s while the FIRST page reports pending scopes, else stop. */
export function pendingRefetchInterval(query: {
  state: { data: { pages: PairPassages[] } | undefined };
}): number | false {
  const pending = query.state.data?.pages[0]?.pending_scopes ?? 0;
  return pending > 0 ? PENDING_REFETCH_MS : false;
}

interface UsePairPassagesReturn {
  /** All loaded video items, flattened across pages. */
  items: VideoPassages[];
  /** The first page — source of the counts and the empty-state basis; undefined until loaded. */
  first: PairPassages | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  /** True when a follow-up page failed while earlier pages are still loaded. */
  isFetchNextPageError: boolean;
  fetchNextPage: () => void;
  refetch: () => void;
}

export function usePairPassages(
  a: string | null,
  b: string | null,
  window: ProximityWindow,
): UsePairPassagesReturn {
  const query = useInfiniteQuery({
    queryKey: [PAIR_PASSAGES_KEY, a ?? null, b ?? null, window],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      fetchPairPassages(
        {
          a: a as string,
          b: b as string,
          window,
          limit: EVIDENCE_PAGE_SIZE,
          offset: pageParam,
        },
        signal,
      ),
    getNextPageParam: (lastPage) =>
      lastPage.truncated && lastPage.returned > 0
        ? lastPage.offset + lastPage.returned
        : undefined,
    enabled: Boolean(a && b) && a !== b,
    staleTime: 60 * 1000,
    refetchInterval: pendingRefetchInterval,
  });

  const { fetchNextPage, refetch } = query;
  // Stable identity: the panel's IntersectionObserver effect depends on it.
  const loadMore = useCallback(() => {
    void fetchNextPage();
  }, [fetchNextPage]);

  return {
    items: query.data?.pages.flatMap((page) => page.items) ?? [],
    first: query.data?.pages[0],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    isFetchNextPageError: query.isFetchNextPageError,
    fetchNextPage: loadMore,
    refetch: () => {
      void refetch();
    },
  };
}

interface UseFartherVideosReturn {
  items: FartherVideo[];
  /** Videos where both are spoken but never within the window. */
  total: number | undefined;
  isLoading: boolean;
  isError: boolean;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}

/** Videos where both are spoken but never within the window; fetched only once `enabled`. */
export function useFartherVideos(
  a: string | null,
  b: string | null,
  window: ProximityWindow,
  enabled: boolean,
): UseFartherVideosReturn {
  const query = useInfiniteQuery({
    queryKey: ["fartherVideos", a ?? null, b ?? null, window],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      fetchFartherVideos(
        {
          a: a as string,
          b: b as string,
          window,
          limit: FARTHER_PAGE_SIZE,
          offset: pageParam,
        },
        signal,
      ),
    getNextPageParam: (lastPage) =>
      lastPage.truncated && lastPage.returned > 0
        ? lastPage.offset + lastPage.returned
        : undefined,
    enabled: enabled && Boolean(a && b) && a !== b,
    staleTime: 60 * 1000,
  });

  const { fetchNextPage } = query;
  const loadMore = useCallback(() => {
    void fetchNextPage();
  }, [fetchNextPage]);

  return {
    items: query.data?.pages.flatMap((page) => page.items) ?? [],
    total: query.data?.pages[0]?.total,
    isLoading: query.isLoading,
    isError: query.isError,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: loadMore,
  };
}
