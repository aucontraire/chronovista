/**
 * CandidatesIcon component - a clipboard-with-check icon representing review queues.
 */

/**
 * CandidatesIcon displays a checked clipboard for candidate review navigation.
 *
 * @param props - Standard SVG props for customization
 */
export const CandidatesIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    <path d="M9 12.75 11.25 15 15 9.75M10.5 3.75h3a1.5 1.5 0 0 1 1.5 1.5v.75H9v-.75a1.5 1.5 0 0 1 1.5-1.5Zm-3.75 2.25h-.75a1.5 1.5 0 0 0-1.5 1.5v12a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-12a1.5 1.5 0 0 0-1.5-1.5h-.75" />
  </svg>
);
