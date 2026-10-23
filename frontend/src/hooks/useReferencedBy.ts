/**
 * useReferencedBy — data for the "Referenced by" panel (Feature 087).
 * A single (non-infinite) query: the backend returns all groups.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchReferencedBy } from "../api/entityMentions";
import type { ReferencedByGroup } from "../api/entityMentions";

interface UseReferencedByReturn {
  groups: ReferencedByGroup[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useReferencedBy(entityId: string | undefined): UseReferencedByReturn {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["referencedBy", entityId ?? null],
    queryFn: ({ signal }) => fetchReferencedBy(entityId as string, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
  });

  return { groups: Array.isArray(data) ? data : [], isLoading, isError, error };
}
