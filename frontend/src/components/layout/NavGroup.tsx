/**
 * NavGroup component - collapsible sidebar navigation group.
 *
 * Implements the Transcripts sidebar group from Feature 046 (US0).
 *
 * Accessibility:
 * - AR-001: button with aria-expanded for expand/collapse state
 * - AR-005: Keyboard navigable (Enter/Space toggles group)
 * - FR-014: Compact mode hides label at <1024px, shows icon + tooltip
 * - FR-015: title={tooltip} provides browser-native tooltips in icon-only mode
 */

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { NavRoute } from "../../router/routes";
import { NavItem } from "./NavItem";

/**
 * Props for the NavGroup component.
 */
interface NavGroupProps {
  /** Display label for the group header */
  label: string;
  /** Tooltip text for accessibility (shown in compact/icon-only mode) */
  tooltip: string;
  /** Icon component for the group header */
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
  /** Child routes rendered inside this group when expanded */
  routes: NavRoute[];
  /** Whether the group starts expanded before localStorage is checked */
  defaultExpanded?: boolean;
  /** localStorage key for persisting expand/collapse state */
  storageKey: string;
}

/**
 * Build className for the group header button based on whether any child is active.
 *
 * Visual Design mirrors NavItem:
 * - Active child: bg-slate-800 text-white border-l-[3px] border-blue-500
 * - Default: text-slate-400 hover:bg-slate-800/50 hover:text-slate-200
 */
function buildGroupHeaderClassName(hasActiveChild: boolean): string {
  const baseClasses = [
    "w-full flex items-center gap-2",
    "py-3 px-4 lg:px-4",
    "justify-center lg:justify-start",
    "text-sm",
    "min-h-[44px] min-w-[44px]",
    "focus:ring-2 focus:ring-blue-500 focus:outline-none",
    "transition-colors duration-150",
  ];

  const stateClasses = hasActiveChild
    ? [
        "bg-slate-800/50 text-white",
        "border-l-[3px] border-blue-500/60",
      ]
    : [
        "text-slate-400",
        "hover:bg-slate-800/50 hover:text-slate-200",
        "border-l-[3px] border-transparent",
      ];

  return [...baseClasses, ...stateClasses].join(" ");
}

/**
 * NavGroup renders a collapsible group of navigation links.
 *
 * Behaviour:
 * - Expand/collapse toggled by clicking the group header button
 * - State persisted to localStorage via storageKey
 * - Auto-expands when any child route matches the current pathname
 * - In compact (<1024px) mode: shows icon only; click navigates to first child
 * - In full (>=1024px) mode: shows icon + label + chevron; click toggles
 *
 * @param props - NavGroup properties
 */
export function NavGroup({
  label,
  tooltip,
  icon: Icon,
  routes,
  defaultExpanded = true,
  storageKey,
}: NavGroupProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // Determine whether any child route is active
  const hasActiveChild = routes.some(
    (child) =>
      location.pathname === child.path ||
      location.pathname.startsWith(child.path + "/")
  );

  // Initialize from localStorage, falling back to defaultExpanded
  const [isExpanded, setIsExpanded] = useState<boolean>(() => {
    const stored = localStorage.getItem(storageKey);
    if (stored !== null) {
      return stored === "true";
    }
    return defaultExpanded;
  });

  // Auto-expand when a child route becomes active
  useEffect(() => {
    if (hasActiveChild) {
      setIsExpanded(true);
    }
  }, [hasActiveChild]);

  // Persist expand/collapse state to localStorage
  useEffect(() => {
    localStorage.setItem(storageKey, String(isExpanded));
  }, [isExpanded, storageKey]);

  /**
   * Handle header button click.
   *
   * In compact mode (<1024px), the label is hidden; clicking should navigate
   * to the first child rather than toggling the group (which would be invisible).
   * We detect compact mode by checking window.innerWidth against the lg breakpoint (1024px).
   */
  function handleHeaderClick() {
    const isCompact = window.innerWidth < 1024;
    if (isCompact) {
      const firstChild = routes[0];
      if (firstChild) {
        navigate(firstChild.path);
      }
    } else {
      setIsExpanded((prev) => !prev);
    }
  }

  return (
    <li>
      {/* Group header button */}
      <button
        type="button"
        onClick={handleHeaderClick}
        title={tooltip}
        aria-expanded={isExpanded}
        className={buildGroupHeaderClassName(hasActiveChild)}
      >
        {/* Group icon */}
        <Icon className="h-6 w-6 flex-shrink-0" />

        {/* Group label — hidden in compact mode, visible at lg: */}
        <span className="hidden lg:inline flex-1 text-left">{label}</span>

        {/* Chevron indicator — hidden in compact mode */}
        <svg
          className={[
            "hidden lg:block h-4 w-4 flex-shrink-0 transition-transform duration-200",
            isExpanded ? "rotate-90" : "",
          ].join(" ")}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          aria-hidden="true"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {/* Child routes — only rendered when expanded */}
      {isExpanded && (
        <ul role="list" className="flex flex-col lg:pl-4">
          {routes.map((child) => (
            <li key={child.path}>
              <NavItem
                to={child.path}
                icon={child.icon}
                label={child.label}
                tooltip={child.tooltip}
              />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
