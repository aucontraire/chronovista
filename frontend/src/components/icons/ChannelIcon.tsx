/**
 * ChannelIcon component - a broadcast/user icon for navigation.
 */

/**
 * ChannelIcon displays a person with signal waves icon.
 * Designed for use in navigation and channel-related UI elements.
 *
 * @param props - Standard SVG props for customization
 */
export const ChannelIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    {/* Person head */}
    <circle cx="9" cy="7" r="4" />
    {/* Person body */}
    <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
    {/* Signal wave 1 (inner) */}
    <path d="M16 11c1.5 0 2.5-1.5 2.5-3s-1-3-2.5-3" />
    {/* Signal wave 2 (outer) */}
    <path d="M19 8c1.5 0 3-1.5 3-4" />
  </svg>
);
