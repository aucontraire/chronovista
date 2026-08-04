/**
 * useCooccurringEntities — data for the appears-with panel (Feature 062, US3).
 *
 * Fetches independently of the entity detail page's initial render (FR-037).
 * This is the feature's slowest query — roughly ten times the intersection
 * itself — so computing it synchronously would dominate load time for exactly
 * the entities users open most: the well-connected ones. That is the
 * difference between a panel that arrives a moment later and a page that feels
 * broken.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchCooccurringEntities } from "../api/entityMentions";
import type { CooccurringEntity } from "../api/entityMentions";

/** Default bound; matches the server default (FR-023). */
export const COOCCURRING_PAGE_SIZE = 12;

interface UseCooccurringEntitiesReturn {
  partners: CooccurringEntity[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export function useCooccurringEntities(
  entityId: string | undefined,
  limit: number = COOCCURRING_PAGE_SIZE,
  minEvidence?: "transcript"
): UseCooccurringEntitiesReturn {
  const { data, isLoading, isError, error } = useQuery({
    // minEvidence is part of the key, so changing the scope starts a NEW query
    // rather than reusing the old one's data. Combined with the abort signal
    // below, an in-flight result computed under the previous scope is
    // discarded instead of being rendered against the new one (FR-024c).
    queryKey: ["cooccurringEntities", entityId ?? null, limit, minEvidence ?? null],
    queryFn: ({ signal }) =>
      fetchCooccurringEntities(entityId as string, limit, minEvidence, signal),
    enabled: Boolean(entityId),
    staleTime: 60 * 1000,
  });

  return {
    partners: data ?? [],
    isLoading,
    isError,
    error,
  };
}
