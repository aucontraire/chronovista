/**
 * usePinnedEntities — URL-addressable pin state for the channel entity panel
 * (Feature 070, US2).
 *
 * Pins are stored as repeated `entity_id` query params, matching the shape
 * `GET /videos` already accepts. Sharing one hook between `ChannelEntityPanel`
 * (which renders the pin toggles) and `ChannelDetailPage` (which fetches the
 * AND-intersection video list) keeps both readers of the URL in sync without
 * either owning the other's state (FR-006 / SC-004: shareable, reload-safe,
 * back/forward compatible).
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

const PARAM_KEY = "entity_id";

interface UsePinnedEntitiesReturn {
  /** Pinned entity UUIDs, in URL order. */
  pinnedEntityIds: string[];
  /** Whether the given entity is currently pinned. */
  isPinned: (entityId: string) => boolean;
  /** Pins the entity if absent, unpins it if present. */
  togglePin: (entityId: string) => void;
  /** Removes every pin at once (the empty-intersection unpin affordance). */
  clearPins: () => void;
}

/**
 * Hook for reading and mutating the pinned-entity set encoded in the URL.
 *
 * @example
 * ```tsx
 * const { pinnedEntityIds, isPinned, togglePin } = usePinnedEntities();
 * ```
 */
export function usePinnedEntities(): UsePinnedEntitiesReturn {
  const [searchParams, setSearchParams] = useSearchParams();

  // Dedupe on read: normal UI use can't create duplicates (togglePin toggles
  // via .includes), but a hand-edited/stale URL like `?entity_id=e1&entity_id=e1`
  // would otherwise inflate the displayed pin count and send a redundant param.
  const pinnedEntityIds = useMemo(
    () => [...new Set(searchParams.getAll(PARAM_KEY))],
    [searchParams]
  );

  const isPinned = useCallback(
    (entityId: string) => pinnedEntityIds.includes(entityId),
    [pinnedEntityIds]
  );

  const togglePin = useCallback(
    (entityId: string) => {
      setSearchParams((prev) => {
        const current = prev.getAll(PARAM_KEY);
        const next = new URLSearchParams(prev);
        next.delete(PARAM_KEY);
        const updated = current.includes(entityId)
          ? current.filter((id) => id !== entityId)
          : [...current, entityId];
        updated.forEach((id) => next.append(PARAM_KEY, id));
        return next;
      });
    },
    [setSearchParams]
  );

  const clearPins = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete(PARAM_KEY);
      return next;
    });
  }, [setSearchParams]);

  return { pinnedEntityIds, isPinned, togglePin, clearPins };
}
