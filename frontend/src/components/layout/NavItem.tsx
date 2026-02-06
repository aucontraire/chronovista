/**
 * NavItem component - navigation link with active state indication.
 *
 * Implements User Story 2: Visual Indication of Current Location
 * with accessibility requirements AR-001 through AR-006.
 *
 * Implements User Story 5: Responsive Sidebar Layout
 * - FR-014: Labels visible at >=1024px, hidden below with icons-only
 * - FR-015: Tooltips via title attribute for icon-only mode
 */

import { NavLink } from "react-router-dom";

/**
 * Props for the NavItem component.
 */
interface NavItemProps {
  /** URL path for this navigation item */
  to: string;
  /** Icon component to display */
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
  /** Text label for the navigation item */
  label: string;
  /** Tooltip text for accessibility */
  tooltip: string;
}

/**
 * Build className based on active state.
 *
 * Visual Design:
 * - VD-001: Active state: bg-slate-800, text-white
 * - VD-002: Inactive: text-slate-400, hover:bg-slate-800/50, hover:text-slate-200
 * - VD-008: Navigation items: py-3 (12px), px-4 (16px)
 * - VD-009: Icons: 24x24px (h-6 w-6), 8px gap to label (gap-2)
 * - VD-010: Font size: text-sm (14px)
 * - VD-011: Active state: 3px left border in border-blue-500
 *
 * Accessibility:
 * - AR-004: 44x44px minimum touch targets
 * - AR-006: Visible focus ring
 */
function buildClassName(isActive: boolean): string {
  const baseClasses = [
    // Base styles for all states
    "flex items-center gap-2",
    // VD-008: responsive padding
    // Icons-only mode (<1024px): center icon with equal padding
    // Full mode (>=1024px): standard left padding for text alignment
    "py-3 px-4 lg:px-4",
    // Center content in icons-only mode, left-align in full mode
    "justify-center lg:justify-start",
    // VD-010: font size
    "text-sm",
    // AR-004: minimum touch target
    "min-h-[44px] min-w-[44px]",
    // AR-006: focus ring for keyboard navigation
    "focus:ring-2 focus:ring-blue-500 focus:outline-none",
    // Smooth transitions
    "transition-colors duration-150",
  ];

  const stateClasses = isActive
    ? [
        // VD-001: Active state styling
        "bg-slate-800 text-white",
        // VD-011: 3px left border in blue
        "border-l-[3px] border-blue-500",
      ]
    : [
        // VD-002: Inactive state styling
        "text-slate-400",
        "hover:bg-slate-800/50 hover:text-slate-200",
        // Compensate for border space to keep alignment
        "border-l-[3px] border-transparent",
      ];

  return [...baseClasses, ...stateClasses].join(" ");
}

/**
 * NavItem renders a navigation link with active/inactive styling.
 *
 * Note: React Router's NavLink automatically adds aria-current="page"
 * when the link is active (AR-002 compliance).
 *
 * Accessibility:
 * - AR-002: aria-current="page" on active item (automatic via NavLink)
 * - AR-005: Keyboard navigable (NavLink is naturally focusable)
 * - FR-015: title={tooltip} provides browser native tooltips in icon-only mode
 *
 * @param props - NavItem properties
 */
export function NavItem({ to, icon: Icon, label, tooltip }: NavItemProps) {
  return (
    <NavLink to={to} title={tooltip} className={({ isActive }) => buildClassName(isActive)}>
      {/* VD-009: Icon 24x24px with aria-hidden (already set in icon components) */}
      <Icon className="h-6 w-6 flex-shrink-0" />
      {/* FR-014: Label hidden below 1024px, visible at lg: breakpoint */}
      <span className="hidden lg:inline">{label}</span>
    </NavLink>
  );
}
