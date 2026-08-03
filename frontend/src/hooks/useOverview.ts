/**
 * useOverview hook — library aggregates for the Overview Dashboard (Feature 061).
 *
 * One request serves every card, so the figures are computed together and
 * cannot disagree with each other.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchOverview, type Overview } from "../api/overview";

/** Query key for the overview aggregates. */
export const OVERVIEW_KEY = ["overview"] as const;

interface UseOverviewReturn {
  /** The aggregates, or undefined until the first load resolves */
  overview: Overview | undefined;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether the request failed */
  isError: boolean;
  /** The error, if any */
  error: unknown;
  /** Retry without a full page reload (FR-027c) */
  retry: () => void;
}

/**
 * Fetch the Overview Dashboard aggregates.
 *
 * @example
 * ```tsx
 * const { overview, isLoading, isError, retry } = useOverview();
 * ```
 */
export function useOverview(): UseOverviewReturn {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: OVERVIEW_KEY,
    queryFn: ({ signal }) => fetchOverview(signal),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  return {
    overview: data,
    isLoading,
    isError,
    error,
    retry: () => void refetch(),
  };
}
