/**
 * TanStack Query keys and read hooks for the candidate review UI (Feature 097).
 *
 * The keys live here so every query and invalidation across the candidate
 * pages agrees on one set of constants.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import {
  approveCandidate,
  fetchCandidateDetail,
  fetchCandidateTagFootprint,
  fetchCandidates,
  fetchCandidateSummary,
  fetchGenerationStatus,
  rejectCandidate,
  startGeneration,
} from "../api/candidates";
import type {
  CandidateDetail,
  CandidateVerdictResponse,
  CandidateSummary,
  FetchCandidatesParams,
  TagFootprintResponse,
  GenerationStatusResponse,
} from "../api/candidates";
import type { ApiError } from "../types/video";

/** Candidate list queries (parameters are appended by the hook). */
export const CANDIDATES_KEY = ["candidates"] as const;

/** Single-candidate detail query. */
export const candidateDetailKey = (id: string) =>
  ["candidate-detail", id] as const;

/** Queue summary counts query. */
export const CANDIDATE_SUMMARY_KEY = ["candidate-summary"] as const;

/** Candidate generation status query. */
export const GENERATION_STATUS_KEY = ["candidate-generation-status"] as const;

const DEFAULT_PAGE_SIZE = 20;
const INTERSECTION_THRESHOLD = 0.8;
const STALE_TIME = 5 * 60 * 1000;
const GC_TIME = 10 * 60 * 1000;

/** Do not retry a 404 — the candidate does not exist. */
const retryUnlessNotFound = (failureCount: number, error: unknown): boolean =>
  (error as ApiError | null)?.status !== 404 && failureCount < 3;

interface UseCandidatesListReturn {
  candidates: CandidateDetail[];
  total: number | null;
  loadedCount: number;
  isLoading: boolean;
  isError: boolean;
  error: ApiError | null;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  retry: () => void;
  /** Attach to a sentinel element for infinite-scroll loading. */
  loadMoreRef: React.RefObject<HTMLDivElement | null>;
}

/** Infinite-scroll list of ranked pending candidates. */
export function useCandidatesList(
  params: Omit<FetchCandidatesParams, "offset"> = {}
): UseCandidatesListReturn {
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
      ...CANDIDATES_KEY,
      params.triage ?? null,
      params.type_hint ?? null,
      params.min_token_count ?? null,
      params.possible_duplicate ?? null,
      params.source_channel ?? null,
      params.sort ?? null,
      limit,
    ],
    queryFn: ({ pageParam, signal }) =>
      fetchCandidates({ ...params, limit, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.pagination.has_more) return undefined;
      return lastPage.pagination.offset + lastPage.pagination.limit;
    },
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });

  const candidates = data?.pages.flatMap((p) => p.data) ?? [];
  const lastPage = data?.pages[data.pages.length - 1];
  const total = lastPage?.pagination.total ?? null;

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
        if (entries[0]?.isIntersecting) handleIntersect();
      },
      { threshold: INTERSECTION_THRESHOLD, rootMargin: "100px" }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [handleIntersect]);

  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);

  return {
    candidates,
    total,
    loadedCount: candidates.length,
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

/** Queue counts by review status and pending triage. */
export function useCandidateSummary() {
  return useQuery<CandidateSummary>({
    queryKey: CANDIDATE_SUMMARY_KEY,
    queryFn: async ({ signal }) => (await fetchCandidateSummary(signal)).data,
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: retryUnlessNotFound,
  });
}

/** One candidate by id; disabled until `id` is truthy. */
export function useCandidateDetail(id: string | undefined) {
  return useQuery<CandidateDetail>({
    queryKey: candidateDetailKey(id ?? ""),
    queryFn: ({ signal }) => fetchCandidateDetail(id as string, signal),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: retryUnlessNotFound,
  });
}

/** Variables for a candidate verdict mutation. */
export interface CandidateVerdictVariables {
  candidateId: string;
}

/**
 * Query-key families invalidated after a verdict. An approval creates an
 * entity, so every surface that reads entities or entity-video associations
 * must refetch (mirrors `useScanEntity`).
 */
const verdictInvalidationKeys = (candidateId: string) =>
  [
    CANDIDATES_KEY,
    CANDIDATE_SUMMARY_KEY,
    candidateDetailKey(candidateId),
    ["entity-detail"],
    ["entity-videos"],
    ["video-entities"],
    ["entities"],
    ["entitySearch"],
  ] as const;

function useVerdictMutation(
  mutationFn: (candidateId: string) => Promise<CandidateVerdictResponse>
) {
  const queryClient = useQueryClient();
  return useMutation<CandidateVerdictResponse, ApiError, CandidateVerdictVariables>({
    mutationFn: ({ candidateId }) => mutationFn(candidateId),
    onSuccess: (_data, { candidateId }) => {
      for (const queryKey of verdictInvalidationKeys(candidateId)) {
        void queryClient.invalidateQueries({ queryKey: queryKey as unknown as unknown[] });
      }
    },
  });
}

/** Approve a candidate (creates the entity or reports it already existed). */
export function useApproveCandidate() {
  return useVerdictMutation(approveCandidate);
}

/** Reject a candidate. */
export function useRejectCandidate() {
  return useVerdictMutation(rejectCandidate);
}

/**
 * Polls the candidate generation status.
 *
 * Polls every 2 s while the server reports `running`, stops at a terminal
 * status. On reaching a terminal status the queue and summary are invalidated
 * exactly once per run id (a ref guards against re-renders re-firing it).
 */
export function useGenerationStatus() {
  const queryClient = useQueryClient();

  const result = useQuery<GenerationStatusResponse>({
    queryKey: GENERATION_STATUS_KEY,
    queryFn: ({ signal }) => fetchGenerationStatus(signal),
    refetchInterval: (query) =>
      query.state.data?.run?.status === "running" ? 2_000 : false,
    staleTime: 2_000,
    gcTime: GC_TIME,
  });

  const invalidatedForRunRef = useRef<string | null>(null);
  const runId = result.data?.run?.id;
  const runStatus = result.data?.run?.status;

  useEffect(() => {
    if (runStatus === "running") {
      // A new run is in flight; re-arm so its terminal state fires once.
      if (invalidatedForRunRef.current === runId) {
        invalidatedForRunRef.current = null;
      }
      return;
    }
    if (
      runId !== undefined &&
      (runStatus === "completed" || runStatus === "failed") &&
      invalidatedForRunRef.current !== runId
    ) {
      invalidatedForRunRef.current = runId;
      void queryClient.invalidateQueries({ queryKey: CANDIDATES_KEY });
      void queryClient.invalidateQueries({ queryKey: CANDIDATE_SUMMARY_KEY });
    }
  }, [runId, runStatus, queryClient]);

  return result;
}

/** Result of a start request: a 409 is reported as `alreadyRunning`, not thrown. */
export interface StartGenerationResult {
  alreadyRunning: boolean;
}

/** Starts a generation run; refreshes the status so the page picks it up. */
export function useStartGeneration() {
  const queryClient = useQueryClient();
  return useMutation<StartGenerationResult, ApiError, void>({
    mutationFn: async () => {
      try {
        await startGeneration();
        return { alreadyRunning: false };
      } catch (err) {
        if ((err as ApiError | null)?.status === 409) {
          return { alreadyRunning: true };
        }
        throw err;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GENERATION_STATUS_KEY });
    },
  });
}

/** Pre-approval tag footprint of a candidate; disabled until `id` is truthy. */
export function useCandidateTagFootprint(id: string | undefined) {
  return useQuery<TagFootprintResponse>({
    queryKey: ["candidate-tag-footprint", id ?? ""],
    queryFn: ({ signal }) => fetchCandidateTagFootprint(id as string, signal),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: retryUnlessNotFound,
  });
}
