/**
 * SidebarCategories component - displays categories in sidebar navigation.
 *
 * Implements US10 - Categories Sidebar Navigation
 * - FR-032: Display category names with video counts
 * - FR-033: Hide categories with 0 videos by default with toggle
 * - FR-034: Clickable navigation to filtered video lists
 *
 * Accessibility:
 * - Semantic HTML structure
 * - Keyboard navigable links
 * - Screen reader friendly labels
 * - Focus management for interactive elements
 */

import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import type { SidebarCategory } from "../../hooks/useSidebarCategories";

interface SidebarCategoriesProps {
  /** Array of category objects with video counts */
  categories: SidebarCategory[];
  /** Whether the data is currently loading */
  isLoading?: boolean;
}

/**
 * SidebarCategories renders a collapsible list of categories with video counts.
 *
 * Features:
 * - T076: List of category names with video counts
 * - T077: Integrated with existing Sidebar
 * - T078: Clickable links to /videos?category={id}
 * - T079: Zero-video category handling (hidden by default with toggle)
 * - T079b: Toggle state persisted in localStorage
 * - T080: Video count displayed next to each category name
 *
 * Visual Design:
 * - Collapsible section with header
 * - Muted styling for video counts
 * - Hover states for links
 * - Responsive spacing
 *
 * Accessibility:
 * - Semantic list structure with <ul>/<li>
 * - Keyboard navigable with Tab/Enter
 * - Screen reader accessible labels
 * - Focus states for keyboard users
 *
 * @example
 * ```tsx
 * const { categories, isLoading } = useSidebarCategories();
 *
 * <SidebarCategories
 *   categories={categories}
 *   isLoading={isLoading}
 * />
 * ```
 */
export function SidebarCategories({
  categories,
  isLoading = false,
}: SidebarCategoriesProps) {
  // T079b: Persist toggle state in localStorage
  const [showAll, setShowAll] = useState(() => {
    const stored = localStorage.getItem(
      "chronovista.sidebar.showAllCategories"
    );
    return stored === "true";
  });

  // Persist changes to localStorage
  useEffect(() => {
    localStorage.setItem(
      "chronovista.sidebar.showAllCategories",
      String(showAll)
    );
  }, [showAll]);

  // T079: Filter categories with 0 videos when showAll is false
  const visibleCategories = showAll
    ? categories
    : categories.filter((c) => c.video_count > 0);

  // Count hidden categories for toggle button label
  const hiddenCount = categories.filter((c) => c.video_count === 0).length;

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-2 px-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
          Categories
        </h3>
        <div className="animate-pulse space-y-2">
          <div className="h-4 rounded bg-slate-700"></div>
          <div className="h-4 rounded bg-slate-700"></div>
          <div className="h-4 rounded bg-slate-700"></div>
        </div>
      </div>
    );
  }

  // Empty state
  if (categories.length === 0) {
    return (
      <div className="space-y-2 px-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
          Categories
        </h3>
        <p className="text-xs text-gray-500">No categories available</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 px-2">
      {/* Section header */}
      <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
        Categories
      </h3>

      {/* T076: Category list */}
      <ul className="space-y-1" role="list">
        {visibleCategories.map((category) => (
          <li key={category.category_id}>
            {/* T078: Clickable link navigating to /videos?category={id} */}
            <Link
              to={category.href}
              className={[
                "flex items-center justify-between rounded px-2 py-1.5 text-sm transition-colors",
                "text-gray-300 hover:bg-slate-800 hover:text-white",
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900",
              ].join(" ")}
            >
              {/* Category name */}
              <span className="truncate">{category.name}</span>

              {/* T080: Video count with muted styling */}
              <span className="ml-2 text-xs text-gray-500">
                {category.video_count}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {/* T079: Toggle button for showing/hiding empty categories */}
      {hiddenCount > 0 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className={[
            "text-xs transition-colors",
            "text-blue-400 hover:text-blue-300 hover:underline",
            "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900",
          ].join(" ")}
          aria-expanded={showAll}
          aria-label={
            showAll
              ? "Hide empty categories"
              : `Show ${hiddenCount} empty categories`
          }
        >
          {showAll
            ? "Hide empty categories"
            : `Show all (${hiddenCount} empty)`}
        </button>
      )}
    </div>
  );
}
