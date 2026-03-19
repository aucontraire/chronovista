/**
 * TanStack Query hook for fetching suspected phonetic ASR variants of an entity name.
 *
 * Implements lazy loading (query disabled by default) and client-side filtering
 * by `displayThreshold` without triggering a refetch. When `displayThreshold`
 * falls below `serverFloor`, the server floor is bumped to match so the backend
 * never returns matches below what the client will show.
 *
 * @module hooks/usePhoneticMatches
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchPhoneticMatches } from "../api/entityMentions";
import type { PhoneticMatch } from "../types/corrections";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UsePhoneticMatchesParams {
  /** UUID of the named entity to fetch phonetic matches for */
  entityId: string;
  /**
   * Minimum confidence the backend should return (0.0–1.0).
   * Changing this value triggers a new network request.
   * @default 0.3
   */
  serverFloor?: number;
  /**
   * Minimum confidence shown to the user after client-side filtering.
   * Changing this value does NOT trigger a refetch.
   * If set below `serverFloor`, serverFloor is bumped up to match.
   * @default 0.5
   */
  displayThreshold?: number;
  /**
   * When false the query will not execute (for lazy loading — only fetch
   * when the collapsible section is expanded).
   * @default true
   */
  enabled?: boolean;
}

export interface UsePhoneticMatchesResult {
  /** Filtered results where confidence >= displayThreshold */
  data: PhoneticMatch[] | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  isSuccess: boolean;
  error: Error | null;
  /** The effective serverFloor used for the current query */
  effectiveServerFloor: number;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Hook that fetches suspected phonetic ASR variants for a named entity.
 *
 * Key behaviours:
 * - Query key includes `entityId` and `serverFloor` only — changing
 *   `displayThreshold` alone does not cause a refetch.
 * - Results are filtered client-side to `confidence >= displayThreshold`.
 * - When `displayThreshold` < `serverFloor`, the effective server floor is
 *   automatically bumped so the backend respects the display threshold.
 * - Query is disabled when `enabled` is false (lazy loading support).
 *
 * @param params - Configuration for the query
 * @returns TanStack Query result with client-filtered data
 *
 * @example
 * ```tsx
 * const { data, isLoading } = usePhoneticMatches({
 *   entityId: "entity-uuid-001",
 *   enabled: isExpanded,
 * });
 * const matches = data ?? [];
 * ```
 */
export function usePhoneticMatches({
  entityId,
  serverFloor: serverFloorProp = 0.3,
  displayThreshold = 0.5,
  enabled = true,
}: UsePhoneticMatchesParams): UsePhoneticMatchesResult {
  // When the user sets displayThreshold below serverFloor, bump up the
  // effective server floor so the backend does not return matches that would
  // be hidden anyway. This is tracked in state so a re-render fires and the
  // query key updates to trigger a fresh fetch.
  const [serverFloorOverride, setServerFloorOverride] = useState<number | null>(
    null
  );

  const effectiveServerFloor = useMemo(() => {
    const base = serverFloorOverride ?? serverFloorProp;
    // If displayThreshold has dropped below the current floor, update the
    // override so the next render picks it up (side-effect via useState is
    // handled after the memo runs).
    return base;
  }, [serverFloorProp, serverFloorOverride]);

  // Synchronise override when displayThreshold falls below the current floor.
  // We compare against the previously-computed effectiveServerFloor.
  if (displayThreshold < effectiveServerFloor) {
    setServerFloorOverride(displayThreshold);
  } else if (
    serverFloorOverride !== null &&
    displayThreshold >= serverFloorProp
  ) {
    // Reset override once displayThreshold is back above the original prop.
    setServerFloorOverride(null);
  }

  const queryResult = useQuery({
    queryKey: ["phonetic-matches", entityId, effectiveServerFloor],
    queryFn: ({ signal }) =>
      fetchPhoneticMatches(entityId, effectiveServerFloor, signal),
    enabled: enabled && Boolean(entityId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  // Apply client-side threshold filter.
  const filteredData = useMemo(() => {
    if (!queryResult.data) return queryResult.data;
    return queryResult.data.filter(
      (match) => match.confidence >= displayThreshold
    );
  }, [queryResult.data, displayThreshold]);

  return {
    data: filteredData,
    isLoading: queryResult.isLoading,
    isFetching: queryResult.isFetching,
    isError: queryResult.isError,
    isSuccess: queryResult.isSuccess,
    error: queryResult.error,
    effectiveServerFloor,
  };
}
