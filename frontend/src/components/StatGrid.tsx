/**
 * StatGrid — a labelled grid of numeric figures.
 *
 * Extracted from `settings/AboutSection.tsx`'s `DatabaseStatsGrid` when the
 * Overview Dashboard needed the same pattern for its inventory and its rollups
 * (Feature 061, T055). Three call sites, so the abstraction is earned rather
 * than anticipated.
 *
 * Figures are rendered as a semantic description list: the label is the term,
 * the number is the definition. `tabular-nums` keeps digits aligned across
 * tiles so columns of figures stay readable.
 *
 * A tile is interactive only when it carries an `href` (FR-025) — the
 * distinction is structural, not a styling convention that could drift.
 */

import { Link } from "react-router-dom";

export interface StatGridItem {
  /** The term. Must read as a noun phrase — it is the accessible label. */
  label: string;
  value: number;
  /**
   * Explicit qualifying text under the figure, e.g. "System list".
   *
   * Carries meaning that must not depend on colour or styling alone
   * (FR-022, FR-034).
   */
  note?: string;
  /** When set the figure links here; when absent the tile is inert (FR-025). */
  href?: string;
  /**
   * Accessible name for the link, when `href` is set.
   *
   * The visible link text is a bare number, which tells a screen-reader user
   * nothing about where it goes.
   */
  linkLabel?: string;
}

interface StatGridProps {
  items: StatGridItem[];
  /** Visible heading; also names the list for assistive technology. */
  heading: string;
  /** DOM id linking the heading to the list via `aria-labelledby`. */
  headingId: string;
  /**
   * Heading level, so the grid nests correctly wherever it is placed.
   *
   * Not cosmetic: a fixed level would make this heading a sibling of the
   * section that contains it, breaking the document outline screen-reader
   * users navigate by.
   */
  headingLevel?: "h3" | "h4";
  /** Render placeholder tiles instead of figures. */
  loading?: boolean;
  /** How many placeholders to show while loading. */
  skeletonCount?: number;
}

const TILE = "bg-slate-50 border border-slate-100 rounded-lg px-4 py-3";

export function StatGrid({
  items,
  heading,
  headingId,
  headingLevel: Heading = "h3",
  loading = false,
  skeletonCount = 3,
}: StatGridProps) {
  return (
    <div>
      <Heading
        id={headingId}
        className="text-sm font-semibold text-slate-700 mb-3"
      >
        {heading}
      </Heading>

      {loading ? (
        <div
          className="grid grid-cols-2 sm:grid-cols-3 gap-3"
          aria-busy="true"
          data-testid={`${headingId}-loading`}
        >
          <span className="sr-only">Loading {heading}…</span>
          {Array.from({ length: skeletonCount }, (_, i) => (
            <div key={i} className={TILE} aria-hidden="true">
              <div className="animate-pulse">
                <div className="h-3 w-20 bg-slate-200 rounded mb-2" />
                <div className="h-6 w-12 bg-slate-200 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <dl
          aria-labelledby={headingId}
          className="grid grid-cols-2 sm:grid-cols-3 gap-3"
        >
          {items.map(({ label, value, note, href, linkLabel }) => (
            <div key={label} className={TILE}>
              <dt className="text-xs font-medium text-slate-500 mb-0.5">
                {label}
              </dt>
              <dd className="text-xl font-semibold text-slate-900 tabular-nums">
                {href ? (
                  <Link
                    to={href}
                    aria-label={linkLabel ?? `${label}: ${value}`}
                    className="text-blue-700 underline underline-offset-2 hover:text-blue-800 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                  >
                    {value.toLocaleString()}
                  </Link>
                ) : (
                  value.toLocaleString()
                )}
              </dd>
              {note ? (
                <p className="mt-1 text-xs text-slate-500">{note}</p>
              ) : null}
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
