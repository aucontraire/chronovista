/**
 * useNeighborhood — the Explore-mode subgraph around one or more seed entities (Feature 115).
 *
 * Failure classification is shared with Connect (`classifyConnectionError`): 503 = graph
 * unavailable, 404 = a seed absent from the graph, anything else = error.
 */

import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";

import { fetchNeighborhood } from "../api/graph";
import type { GraphSubgraph, NeighborhoodParams } from "../api/graph";
import { isApiError } from "../api/config";
import { classifyConnectionError } from "./useConnection";
import type { ConnectionFailure } from "./useConnection";

export interface UseNeighborhoodOptions extends Omit<NeighborhoodParams, "seeds"> {
  /** Set false to skip the request (e.g. the graph is known unservable). */
  enabled?: boolean;
}

interface UseNeighborhoodReturn {
  subgraph: GraphSubgraph | undefined;
  isLoading: boolean;
  failure: ConnectionFailure | null;
  refetch: () => void;
}

function neighborhoodQuery(seeds: string[], options: UseNeighborhoodOptions) {
  const { enabled = true, radius, limit, ceiling, edgeTypes, maxCategorySize } = options;
  // Seed order is not meaningful; sort so equal sets share a cache entry.
  const seedKey = [...seeds].sort();
  const edgeKey = edgeTypes ? [...edgeTypes].sort() : null;
  return {
    queryKey: [
      "graphNeighborhood",
      seedKey,
      radius ?? null,
      limit ?? null,
      ceiling ?? null,
      edgeKey,
      maxCategorySize ?? null,
    ],
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      fetchNeighborhood(
        { seeds: seedKey, radius, limit, ceiling, edgeTypes: edgeKey ?? undefined, maxCategorySize },
        signal,
      ),
    enabled: seeds.length > 0 && enabled,
    staleTime: 60 * 1000,
    // Keep the current view on screen while a changed request loads or fails (FR-022).
    placeholderData: keepPreviousData,
    retry: (count: number, err: unknown) => {
      const status = isApiError(err) ? err.status : undefined;
      if (status === 503 || status === 404 || status === 422) return false;
      return count < 1;
    },
  };
}

export function useNeighborhood(
  seeds: string[],
  options: UseNeighborhoodOptions = {},
): UseNeighborhoodReturn {
  const { data, isLoading, error, refetch } = useQuery(neighborhoodQuery(seeds, options));
  return {
    subgraph: data,
    isLoading,
    failure: error ? classifyConnectionError(error) : null,
    refetch: () => void refetch(),
  };
}

interface UseExpansionsReturn {
  /** One entry per expanded entity, in expansion order; undefined while loading or failed. */
  results: (GraphSubgraph | undefined)[];
  pending: number;
  failed: number;
}

/**
 * The neighborhoods of nodes the user has expanded (Feature 115, FR-020). One query per expanded
 * entity, so they follow the layer toggles (`edgeTypes`) and are cached; the caller merges them
 * into the base view. Order is the order of `entityIds`.
 */
export function useExpansions(
  entityIds: string[],
  options: UseNeighborhoodOptions = {},
): UseExpansionsReturn {
  return useQueries({
    queries: entityIds.map((id) => neighborhoodQuery([id], options)),
    combine: (queries) => ({
      results: queries.map((q) => q.data),
      pending: queries.filter((q) => q.isLoading).length,
      failed: queries.filter((q) => q.isError).length,
    }),
  });
}
