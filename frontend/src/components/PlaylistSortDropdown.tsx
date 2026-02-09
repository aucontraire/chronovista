/**
 * PlaylistSortDropdown component for sorting playlists.
 *
 * Provides a dropdown menu with 6 sort options:
 * - Title: A → Z
 * - Title: Z → A
 * - Date Added: Newest First
 * - Date Added: Oldest First
 * - Video Count: Most First
 * - Video Count: Least First
 */

import { useId } from "react";

import type {
  PlaylistSortField,
  PlaylistSortOption,
  SortOrder,
} from "../types/playlist";

/**
 * Available sort options for the dropdown.
 */
export const PLAYLIST_SORT_OPTIONS: PlaylistSortOption[] = [
  { field: "title", order: "asc", label: "Title: A → Z" },
  { field: "title", order: "desc", label: "Title: Z → A" },
  { field: "created_at", order: "desc", label: "Date Added: Newest" },
  { field: "created_at", order: "asc", label: "Date Added: Oldest" },
  { field: "video_count", order: "desc", label: "Video Count: Most" },
  { field: "video_count", order: "asc", label: "Video Count: Least" },
];

/**
 * Props for PlaylistSortDropdown component.
 */
export interface PlaylistSortDropdownProps {
  /** Current sort field */
  sortBy: PlaylistSortField;
  /** Current sort order */
  sortOrder: SortOrder;
  /** Callback when sort changes */
  onSortChange: (field: PlaylistSortField, order: SortOrder) => void;
}

/**
 * Get the combined value string for the select element.
 */
function getSortValue(field: PlaylistSortField, order: SortOrder): string {
  return `${field}:${order}`;
}

/**
 * Parse the combined value string back to field and order.
 */
function parseSortValue(value: string): {
  field: PlaylistSortField;
  order: SortOrder;
} {
  const [field, order] = value.split(":") as [PlaylistSortField, SortOrder];
  return { field, order };
}

/**
 * PlaylistSortDropdown displays a select dropdown for sorting playlists.
 *
 * @param props - Component props
 * @returns JSX element with sort dropdown
 */
export function PlaylistSortDropdown({
  sortBy,
  sortOrder,
  onSortChange,
}: PlaylistSortDropdownProps) {
  const selectId = useId();
  const currentValue = getSortValue(sortBy, sortOrder);

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const { field, order } = parseSortValue(event.target.value);
    onSortChange(field, order);
  };

  return (
    <div className="flex items-center gap-2">
      <label
        htmlFor={selectId}
        className="text-sm font-medium text-gray-600 whitespace-nowrap"
      >
        Sort by
      </label>
      <select
        id={selectId}
        value={currentValue}
        onChange={handleChange}
        className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        aria-label="Sort playlists"
      >
        {PLAYLIST_SORT_OPTIONS.map((option) => (
          <option
            key={getSortValue(option.field, option.order)}
            value={getSortValue(option.field, option.order)}
          >
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
