/**
 * WatchedFilterTabs Component (Feature 061)
 *
 * Tri-state filter for a playlist's video list: All / Watched / Unwatched.
 *
 * Implements:
 * - FR-006: three filter values, defaulting to All
 * - FR-030: keyboard operable, selected value exposed to assistive technology
 * - FR-035: visible focus indicator
 *
 * This is a small dedicated control rather than a generalization of
 * `PlaylistFilterTabs`. That component serves one use case across four call
 * sites and has its own substantial test suite; widening its type parameter for
 * a second consumer would be abstracting on the second use, which the Rule of
 * Three forbids, and would put working code at risk inside a read-only feature.
 * Its keyboard model (arrow/Home/End with activation on move) is reproduced here
 * deliberately, so both controls behave identically for a keyboard user.
 */

import { useEffect, useRef } from "react";

import type { WatchedStatus } from "../hooks/usePlaylistVideos";

interface WatchedFilterTabsProps {
  /** Currently selected watched-status filter */
  currentFilter: WatchedStatus;
  /** Callback when the selection changes */
  onFilterChange: (filter: WatchedStatus) => void;
  /**
   * Counts shown as badges.
   *
   * These come from the stats header and are the *playlist* figures — they do
   * not change as the filter moves (FR-005b), so the badges stay stable while
   * the list below them changes.
   */
  counts?: {
    all?: number;
    watched?: number;
    unwatched?: number;
  };
  /** Optional className for custom styling */
  className?: string;
}

const TABS: Array<{
  id: WatchedStatus;
  label: string;
  ariaLabel: string;
}> = [
  { id: "all", label: "All", ariaLabel: "Show all videos" },
  { id: "watched", label: "Watched", ariaLabel: "Show only watched videos" },
  {
    id: "unwatched",
    label: "Unwatched",
    ariaLabel: "Show only unwatched videos",
  },
];

/**
 * Tri-state watched-status filter with keyboard navigation.
 *
 * @example
 * ```tsx
 * <WatchedFilterTabs
 *   currentFilter={watchedStatus}
 *   onFilterChange={setWatchedStatus}
 *   counts={{ all: 4973, watched: 2581, unwatched: 2392 }}
 * />
 * ```
 */
export function WatchedFilterTabs({
  currentFilter,
  onFilterChange,
  counts,
  className = "",
}: WatchedFilterTabsProps) {
  const tablistRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tablist = tablistRef.current;
    if (!tablist) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (!target.matches('[role="tab"]')) return;

      const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
      const currentIndex = tabs.indexOf(target);

      let nextIndex: number | null = null;

      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          nextIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
          break;
        case "ArrowRight":
          e.preventDefault();
          nextIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
          break;
        case "Home":
          e.preventDefault();
          nextIndex = 0;
          break;
        case "End":
          e.preventDefault();
          nextIndex = tabs.length - 1;
          break;
      }

      if (nextIndex !== null) {
        const nextTab = tabs[nextIndex] as HTMLButtonElement;
        nextTab.focus();
        const filterId = nextTab.dataset.watchedStatus as WatchedStatus;
        if (filterId) {
          onFilterChange(filterId);
        }
      }
    };

    tablist.addEventListener("keydown", handleKeyDown);
    return () => tablist.removeEventListener("keydown", handleKeyDown);
  }, [onFilterChange]);

  return (
    <div
      ref={tablistRef}
      role="tablist"
      aria-label="Filter videos by watched status"
      className={`inline-flex items-center gap-1 ${className}`}
    >
      {TABS.map((tab) => {
        const isSelected = currentFilter === tab.id;
        const count = counts?.[tab.id];

        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isSelected}
            aria-label={tab.ariaLabel}
            data-watched-status={tab.id}
            onClick={() => onFilterChange(tab.id)}
            tabIndex={isSelected ? 0 : -1}
            className={`
              px-3 py-1.5 text-sm font-medium rounded-md transition-colors
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
              ${
                isSelected
                  ? "bg-blue-600 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }
            `}
          >
            <span className="flex items-center gap-1.5">
              {tab.label}
              {count !== undefined && (
                <span
                  className={`text-xs tabular-nums ${
                    isSelected ? "text-blue-100" : "text-slate-500"
                  }`}
                >
                  {count.toLocaleString()}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
