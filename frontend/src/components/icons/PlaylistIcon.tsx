/**
 * PlaylistIcon component - a stacked list icon for playlist navigation.
 */

/**
 * PlaylistIcon displays a stacked bars/list icon representing a playlist.
 * Designed for use in navigation and playlist-related UI elements.
 *
 * @param props - Standard SVG props for customization
 */
export const PlaylistIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    {/* Top list item */}
    <path d="M3 6h18" />
    {/* Middle list item */}
    <path d="M3 12h18" />
    {/* Bottom list item */}
    <path d="M3 18h18" />
    {/* Play indicator on right side */}
    <polygon points="20 12 16 9 16 15" fill="currentColor" />
  </svg>
);
