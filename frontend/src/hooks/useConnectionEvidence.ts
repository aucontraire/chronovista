/**
 * useConnectionEvidence — paged data for the transcript-evidence panel (Feature 114).
 *
 * Infinite scroll over VIDEO-grain items: each page fetches `EVIDENCE_PAGE_SIZE` videos at an
 * advancing offset, and `getNextPageParam` follows the server's offset-aware `truncated` flag — so a
 * dense pair (hundreds of videos) streams in on scroll instead of being collapsed away. Independent
 * of the connection query so the panel can arrive a moment later and degrade on its own (a backend
 * error leaves the rest of the connection view intact — FR-018). The endpoint has no 503 (it reads
 * Postgres), so there is no three-way failure classification.
 */

import { useCallback } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";

import { fetchConnectionEvidence } from "../api/graph";
import type { ConnectionEvidence, EvidenceItem } from "../api/graph";

/** Page size; matches the server default (FR-010). */
export const EVIDENCE_PAGE_SIZE = 12;

interface UseConnectionEvidenceReturn {
  /** All loaded video items, flattened across pages. */
  items: EvidenceItem[];
  /** The first page — source of the counts and the empty-state basis; undefined until loaded. */
  first: ConnectionEvidence | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  /** True when a follow-up page failed while earlier pages are still loaded. */
  isFetchNextPageError: boolean;
  fetchNextPage: () => void;
}

export function useConnectionEvidence(
  a: string | null,
  b: string | null,
): UseConnectionEvidenceReturn {
  const query = useInfiniteQuery({
    queryKey: ["connectionEvidence", a ?? null, b ?? null],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      fetchConnectionEvidence(
        {
          a: a as string,
          b: b as string,
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
  });

  const { fetchNextPage } = query;
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
  };
}
