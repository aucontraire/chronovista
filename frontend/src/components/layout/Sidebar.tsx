/**
 * Sidebar component - main navigation sidebar for the application.
 *
 * Implements User Story 2: Visual Indication of Current Location
 * with accessibility requirements AR-001 through AR-006.
 *
 * Implements User Story 5: Responsive Sidebar Layout
 * - FR-014: Responsive sidebar with full labels at >=1024px, icons-only below
 * - VD-006: Width 64px (icons-only) or 240px (full labels)
 */

import { navRoutes } from "../../router/routes";
import { NavItem } from "./NavItem";

/**
 * Sidebar renders the main navigation sidebar.
 *
 * Visual Design:
 * - VD-003: Sidebar background: bg-slate-900
 * - VD-006: Sidebar width: 64px (w-16) icons-only, 240px (lg:w-60) full labels
 *
 * Responsive Breakpoints:
 * - >=1024px (lg:): Full width 240px with icons + labels
 * - <1024px: Narrow width 64px with icons only + tooltips
 *
 * Accessibility:
 * - AR-001: <nav aria-label="Main navigation">
 * - AR-003: Icons have aria-hidden="true" (handled in icon components)
 * - AR-005: Keyboard navigable (Tab/Shift+Tab) via NavLink
 *
 * Layout:
 * - Fixed height: min-h-screen
 * - Flex column layout with padding
 */
export function Sidebar() {
  return (
    // AR-001: nav with accessible label
    <nav
      aria-label="Main navigation"
      className={[
        // VD-003: sidebar background
        "bg-slate-900",
        // VD-006: responsive sidebar width
        // w-16 = 64px (icons-only) for screens < 1024px
        // lg:w-60 = 240px (full labels) for screens >= 1024px
        "w-16 lg:w-60",
        // Full height layout
        "min-h-screen",
        // Flex column for vertical navigation
        "flex flex-col",
        // Padding for visual spacing
        "py-4",
        // Add spacing between sections
        "space-y-6",
      ].join(" ")}
    >
      {/* Navigation items */}
      <ul className="flex flex-col" role="list">
        {navRoutes.map((route) => (
          <li key={route.path}>
            <NavItem
              to={route.path}
              icon={route.icon}
              label={route.label}
              tooltip={route.tooltip}
            />
          </li>
        ))}
      </ul>
    </nav>
  );
}
