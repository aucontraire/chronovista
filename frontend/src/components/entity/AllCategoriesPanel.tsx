/**
 * AllCategoriesPanel — "All categories" on the entity detail page
 * (Feature 090).
 *
 * Every Wikipedia category the entity belongs to, uncapped by any sharing
 * threshold, in server order (member count ascending, most specific first).
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import {
  DEFAULT_ENTITY_CATEGORIES_PAGE_SIZE,
  useAllCategories,
} from "../../hooks/useAllCategories";

/** Server-enforced ceiling; show-more stops here. */
const MAX_ENTITY_CATEGORIES = 200;

interface AllCategoriesPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function AllCategoriesPanel({
  entityId,
  className = "",
}: AllCategoriesPanelProps) {
  const [limit, setLimit] = useState(DEFAULT_ENTITY_CATEGORIES_PAGE_SIZE);
  const { categories, isLoading, isError } = useAllCategories(entityId, limit);

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="all-categories-panel"
      data-testid="all-categories-panel"
    >
      <h2
        id="all-categories-panel"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        All categories
      </h2>

      {isError && (
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="all-categories-error"
        >
          Couldn&apos;t load categories. The rest of this page is unaffected.
        </p>
      )}

      {!isError && isLoading && categories.length === 0 && (
        <p role="status" className="text-sm text-slate-600">
          Loading categories…
        </p>
      )}

      {!isError && !isLoading && categories.length === 0 && (
        <p className="text-sm text-slate-600" data-testid="all-categories-empty">
          This entity doesn&apos;t belong to any categories.
        </p>
      )}

      {!isError && categories.length > 0 && (
        <>
          <ul className="flex flex-wrap gap-1">
            {categories.map((category) => (
              <li key={category.id}>
                <Link
                  to={`/wikipedia-categories/${category.id}`}
                  className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                >
                  {category.name}
                  <span className="text-slate-500">
                    {category.member_count}{" "}
                    {category.member_count === 1 ? "member" : "members"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          {categories.length >= limit && limit < MAX_ENTITY_CATEGORIES && (
            <button
              type="button"
              onClick={() =>
                setLimit((current) =>
                  Math.min(
                    current + DEFAULT_ENTITY_CATEGORIES_PAGE_SIZE,
                    MAX_ENTITY_CATEGORIES
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
