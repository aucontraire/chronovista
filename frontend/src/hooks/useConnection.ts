/**
 * Connection Explorer data hooks (Feature 113, FR-015).
 *
 * `useConnection` keeps the three non-success outcomes distinct, because the UI
 * must never conflate them (FR-009):
 *  - 503 → `unavailable`  (graph rebuilding / not loaded / unreachable)
 *  - 404 → `not_in_graph` (a valid id absent from the current graph)
 *  - anything else → `error`
 */

import { useQuery } from "@tanstack/react-query";

import { fetchConnection, fetchGraphHealth, fetchGraphPresence } from "../api/graph";
import type { GraphConnection, GraphHealth } from "../api/graph";
import { isApiError } from "../api/config";

export type ConnectionFailure =
  | { kind: "unavailable" }
  | { kind: "not_in_graph"; detail: string | undefined }
  | { kind: "error" };

export function classifyConnectionError(error: unknown): ConnectionFailure {
  const status = isApiError(error) ? error.status : undefined;
  if (status === 503) return { kind: "unavailable" };
  if (status === 404) {
    const detail =
      typeof error === "object" && error !== null && "detail" in error
        ? String((error as { detail: unknown }).detail)
        : undefined;
    return { kind: "not_in_graph", detail };
  }
  return { kind: "error" };
}

interface UseConnectionReturn {
  connection: GraphConnection | undefined;
  isLoading: boolean;
  failure: ConnectionFailure | null;
  refetch: () => void;
}

export interface UseConnectionOptions {
  maxHops?: number;
  maxCategorySize?: number;
  /** Set false to skip the request (e.g. the graph is known unservable). */
  enabled?: boolean;
}

export function useConnection(
  a: string | null,
  b: string | null,
  options: UseConnectionOptions = {},
): UseConnectionReturn {
  const { maxHops, maxCategorySize, enabled = true } = options;
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["graphConnection", a, b, maxHops ?? null, maxCategorySize ?? null],
    queryFn: ({ signal }) =>
      fetchConnection(
        { a: a as string, b: b as string, maxHops, maxCategorySize },
        signal,
      ),
    enabled: Boolean(a && b) && a !== b && enabled,
    staleTime: 60 * 1000,
    // 503/404 are answers, not transient faults worth retrying.
    retry: (count, err) => {
      const status = isApiError(err) ? err.status : undefined;
      if (status === 503 || status === 404 || status === 422) return false;
      return count < 1;
    },
  });
  return {
    connection: data,
    isLoading,
    failure: error ? classifyConnectionError(error) : null,
    refetch: () => void refetch(),
  };
}

export function useGraphHealth(): { health: GraphHealth | undefined; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ["graphHealth"],
    queryFn: ({ signal }) => fetchGraphHealth(signal),
    staleTime: 15 * 1000,
    retry: false,
  });
  return { health: data, isLoading };
}

/** Which of `entityIds` are in the current graph (FR-002). */
export function useGraphPresence(entityIds: string[]): {
  present: ReadonlySet<string>;
  isLoading: boolean;
} {
  const key = [...entityIds].sort();
  const { data, isLoading } = useQuery({
    queryKey: ["graphPresence", key],
    queryFn: ({ signal }) => fetchGraphPresence(entityIds, signal),
    enabled: entityIds.length > 0,
    staleTime: 60 * 1000,
    retry: false,
  });
  return { present: new Set(data ?? []), isLoading: entityIds.length > 0 && isLoading };
}
