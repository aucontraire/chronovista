/**
 * TagsIcon component - a price-tag icon representing the Tags nav group.
 *
 * Used as the group icon for the Tags sidebar navigation group (Feature 056).
 */

/**
 * TagsIcon displays an outlined tag icon for the Tags nav group.
 *
 * @param props - Standard SVG props for customization
 */
export const TagsIcon = (props: React.SVGProps<SVGSVGElement>) => (
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
    <path d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.83.699 2.529 0l4.318-4.318a1.79 1.79 0 0 0 0-2.529L10.507 3.659A2.25 2.25 0 0 0 9.568 3Z" />
    <path d="M6 6h.008v.008H6V6Z" />
  </svg>
);
