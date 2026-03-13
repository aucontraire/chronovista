/**
 * TanStack Query hook for the entity detail endpoint.
 *
 * Used by BatchCorrectionsPage and PatternInput to fetch alias names for an
 * entity so the mismatch warning can check the replacement text against both
 * the canonical name AND registered aliases (e.g. "AMLO" for
 * "Andrés Manuel López Obrador").
 *
 * The backend filters out `asr_error` aliases from the detail endpoint, so
 * the returned alias names are all genuine aliases safe for comparison.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchEntityDetail } from "../api/entityMentions";
import type { EntityDetail } from "../api/entityMentions";

// ---------------------------------------------------------------------------
// Return type
// ---------------------------------------------------------------------------

interface UseEntityDetailReturn {
  /** Full entity detail including alias array, or undefined while loading. */
  entityDetail: EntityDetail | undefined;
  /**
   * Alias names extracted from the entity detail for mismatch checking.
   * Empty array when the entity has no aliases or the query has not resolved.
   */
  aliasNames: string[];
  /** Whether the initial load is in progress. */
  isLoading: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetches entity detail (including genuine aliases) for a given entity ID.
 *
 * The query is disabled when `entityId` is null so no request is made until
 * an entity is selected. Results are cached for 5 minutes — alias sets change
 * infrequently and the cache is shared with any other consumers of the same
 * entity detail.
 *
 * @param entityId - UUID of the named entity, or null when no entity is selected
 * @returns Entity detail, derived alias names array, and loading flag
 *
 * @example
 * ```tsx
 * const { aliasNames } = useEntityDetail(selectedEntity?.id ?? null);
 * const hasMismatch = isEntityMismatch(replacement, entity.name, aliasNames);
 * ```
 */
export function useEntityDetail(entityId: string | null): UseEntityDetailReturn {
  const { data, isLoading } = useQuery({
    queryKey: ["entity-detail", entityId],
    queryFn: () => fetchEntityDetail(entityId!),
    enabled: entityId !== null,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,
  });

  const aliasNames = data?.aliases.map((a) => a.alias_name) ?? [];

  return {
    entityDetail: data,
    aliasNames,
    isLoading,
  };
}
