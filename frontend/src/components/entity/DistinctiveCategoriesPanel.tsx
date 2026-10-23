/**
 * DistinctiveCategoriesPanel — "Distinctive — only this entity" on the entity
 * detail page (Feature 089).
 *
 * Categories whose sole active member is the subject: the complement of the
 * shared-categories panel. Renders nothing while loading or when there are
 * none, so no empty sub-section appears or flashes.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import {
  DISTINCTIVE_CATEGORY_PAGE_SIZE,
  useDistinctiveCategories,
} from "../../hooks/useDistinctiveCategories";

/** Server-enforced ceiling; show-more stops here. */
const MAX_DISTINCTIVE_CATEGORIES = 200;

interface DistinctiveCategoriesPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function DistinctiveCategoriesPanel({
  entityId,
  className = "",
}: DistinctiveCategoriesPanelProps) {
  const [limit, setLimit] = useState(DISTINCTIVE_CATEGORY_PAGE_SIZE);
  const { categories, isLoading, isError } = useDistinctiveCategories(
    entityId,
    limit
  );

  // Absent while loading and when empty (the common case), so nothing flashes
  // in and out; a real failure is still surfaced.
  if (!isError && (isLoading || categories.length === 0)) {
    return null;
  }

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="distinctive-categories-heading"
      data-testid="distinctive-categories-panel"
    >
      <h2
        id="distinctive-categories-heading"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        Distinctive — only this entity
      </h2>

      {isError && (
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="distinctive-categories-error"
        >
          Couldn&apos;t load distinctive categories. The rest of this page is
          unaffected.
        </p>
      )}

      {!isError && categories.length > 0 && (
        <>
          <ul className="flex flex-wrap gap-1">
            {categories.map((category) => (
              <li key={category.id}>
                <Link
                  to={`/wikipedia-categories/${category.id}`}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                >
                  {category.name}
                </Link>
              </li>
            ))}
          </ul>

          {categories.length >= limit && limit < MAX_DISTINCTIVE_CATEGORIES && (
            <button
              type="button"
              onClick={() =>
                setLimit((current) =>
                  Math.min(
                    current + DISTINCTIVE_CATEGORY_PAGE_SIZE,
                    MAX_DISTINCTIVE_CATEGORIES
                  )
                )
              }
              className="mt-2 text-sm text-indigo-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
            >
              Show more
            </button>
          )}
        </>
      )}
    </section>
  );
}
