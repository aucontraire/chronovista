/**
 * VideoIcon component - a film/video icon for navigation.
 */

/**
 * VideoIcon displays a video/film icon using a rectangle with play triangle.
 * Designed for use in navigation and UI elements.
 *
 * @param props - Standard SVG props for customization
 */
export const VideoIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    {/* Video rectangle */}
    <rect x="2" y="4" width="20" height="16" rx="2" ry="2" />
    {/* Play triangle */}
    <polygon points="10,8 16,12 10,16" />
  </svg>
);
