/**
 * SearchIcon component - a magnifying glass icon for navigation.
 */

/**
 * SearchIcon displays a magnifying glass icon.
 * Designed for use in navigation and search-related UI elements.
 *
 * @param props - Standard SVG props for customization
 */
export const SearchIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg
    {...props}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    aria-hidden="true"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {/* Magnifying glass circle */}
    <circle cx="11" cy="11" r="8" />
    {/* Handle */}
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);
