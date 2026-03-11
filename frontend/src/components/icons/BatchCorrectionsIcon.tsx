/**
 * BatchCorrectionsIcon component - a find-and-replace icon for the batch
 * corrections navigation entry.
 *
 * Uses a magnifying glass with a pencil overlay to convey "find and edit".
 */

/**
 * BatchCorrectionsIcon displays a search-and-replace icon.
 *
 * @param props - Standard SVG props for customization
 */
export const BatchCorrectionsIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    {/* Magnifying glass */}
    <path d="M10.5 10.5a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z" />
    <path d="M13.5 13.5 21 21" />
    {/* Pencil/edit mark — conveys replacement */}
    <path d="M16.5 3.75 20.25 7.5l-6.75 6.75-3.75.75.75-3.75 6-6.75Z" />
    <path d="M15 5.25l3.75 3.75" />
  </svg>
);
