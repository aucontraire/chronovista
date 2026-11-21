/**
 * graphLayoutCache — remembers a graph's arrangement across the page unmounting, so coming back
 * to the same graph shows it exactly as it was left instead of re-running a (randomized) layout.
 *
 * Module-level on purpose: component state dies with the unmount. It is in-memory only (a page
 * reload re-lays out), bounded, and keyed by the caller (e.g. the seed pair). A cached entry is
 * only ever applied when it covers every node currently on screen, so a stale or different graph
 * falls through to a real layout.
 */

export interface SavedLayout {
  /** Node id → position. */
  positions: Record<string, { x: number; y: number }>;
  /** Pan/zoom as the user left them; null when saved while maximized (then the view is re-fitted). */
  viewport: { pan: { x: number; y: number }; zoom: number } | null;
}

const MAX_ENTRIES = 8;
const cache = new Map<string, SavedLayout>();

export function getSavedLayout(key: string): SavedLayout | undefined {
  return cache.get(key);
}

export function saveLayout(key: string, layout: SavedLayout): void {
  cache.delete(key); // re-insert → most recent last
  cache.set(key, layout);
  while (cache.size > MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}

/** For tests. */
export function clearSavedLayouts(): void {
  cache.clear();
}
