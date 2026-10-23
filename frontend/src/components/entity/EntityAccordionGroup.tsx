/**
 * EntityAccordionGroup - a titled, independently-collapsible region used to
 * organise the entity detail page into a few named groups (Feature 089).
 *
 * Mirrors the NavGroup collapsible idiom: a native header <button> carrying
 * `aria-expanded` / `aria-controls`, and a rotating chevron. Children stay
 * mounted while collapsed (the region is `hidden`) so section state such as
 * in-progress forms and running queries survives a collapse/expand.
 *
 * Open/closed state is ephemeral local state; it is intentionally not
 * persisted.
 *
 * @example
 * <EntityAccordionGroup title="Connections">
 *   <CooccurringPanel entityId={id} />
 * </EntityAccordionGroup>
 */

import { useId, useState } from "react";

export interface EntityAccordionGroupProps {
  /** Group heading shown in the header button. */
  title: string;
  /** Whether the group starts expanded. Defaults to true. */
  defaultOpen?: boolean;
  /** Group content. */
  children: React.ReactNode;
  /** Stable test hook placed on the outer wrapper. */
  "data-testid"?: string;
}

export function EntityAccordionGroup({
  title,
  defaultOpen = true,
  children,
  "data-testid": testId,
}: EntityAccordionGroupProps) {
  const [open, setOpen] = useState<boolean>(defaultOpen);
  const baseId = useId();
  const headerId = `${baseId}-header`;
  const contentId = `${baseId}-content`;

  return (
    <div data-testid={testId} className="mb-6">
      <button
        type="button"
        id={headerId}
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center gap-2 py-2 mb-3 text-left text-sm font-semibold uppercase tracking-wide text-gray-600 border-b border-gray-200 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded-sm"
      >
        <svg
          className={[
            "h-4 w-4 flex-shrink-0 transition-transform duration-200",
            open ? "rotate-90" : "",
          ].join(" ")}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M9 5l7 7-7 7" />
        </svg>
        <span className="flex-1 min-w-0 break-words">{title}</span>
      </button>

      <div
        id={contentId}
        role="region"
        aria-labelledby={headerId}
        hidden={!open}
        className="min-w-0"
      >
        {children}
      </div>
    </div>
  );
}
