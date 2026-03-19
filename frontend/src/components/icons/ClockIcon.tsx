/**
 * ClockIcon component - a clock icon representing history or time.
 *
 * Used as the icon for the Batch History navigation entry.
 */

/**
 * ClockIcon displays a clock face icon.
 *
 * @param props - Standard SVG props for customization
 */
export const ClockIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg
    {...props}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    aria-hidden="true"
    strokeWidth={1.5}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
);
