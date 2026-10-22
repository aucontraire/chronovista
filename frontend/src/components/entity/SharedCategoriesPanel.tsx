/**
 * SharedCategoriesPanel — "Shares categories with" on the entity detail page
 * (Feature 085).
 *
 * A topical grouping: entities that sit under the same Wikipedia categories
 * as the subject. It is deliberately NOT framed as a relationship — sharing a
 * category asserts nothing about how two entities connect. Neighbours render
 * in server order (already ranked); the client never re-sorts.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { EntityName } from "../EntityName";
import {
  SHARED_CATEGORY_PAGE_SIZE,
  useSharedCategoryNeighbours,
} from "../../hooks/useSharedCategoryNeighbours";

/** Server-enforced ceiling; show-more stops here. */
const MAX_SHARED_CATEGORIES = 50;

interface SharedCategoriesPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function SharedCategoriesPanel({
  entityId,
  className = "",
}: SharedCategoriesPanelProps) {
  const [limit, setLimit] = useState(SHARED_CATEGORY_PAGE_SIZE);
  const { neighbours, isLoading, isError } = useSharedCategoryNeighbours(
    entityId,
    limit
  );

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="shared-categories-heading"
      data-testid="shared-categories-panel"
    >
      <h2
        id="shared-categories-heading"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        Shares categories with
      </h2>

      {isLoading && (
        <p
          role="status"
          className="text-sm text-slate-500"
          data-testid="shared-categories-loading"
        >
          Finding entities in shared categories…
        </p>
      )}

      {/* A panel failure degrades to a panel-level error and leaves the
          surrounding page usable. */}
      {!isLoading && isError && (
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="shared-categories-error"
        >
          Couldn&apos;t load shared categories. The rest of this page is
          unaffected.
        </p>
      )}

      {!isLoading && !isError && neighbours.length === 0 && (
        <p
          role="status"
          className="text-sm text-slate-600"
          data-testid="shared-categories-empty"
        >
          No other entities share categories with this one yet.
        </p>
      )}

      {!isLoading && !isError && neighbours.length > 0 && (
        <>
          <ul className="flex flex-col gap-1">
            {neighbours.map((n) => (
              <li key={n.entity_id} className="rounded px-2 py-1.5 text-sm hover:bg-slate-50">
                {/* Chips are links too, and anchors cannot nest, so the entity
                    link wraps only the name row. */}
                <Link
                  to={`/entities/${n.entity_id}`}
                  className="block rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                >
                  <span className="flex items-center justify-between gap-2">
                    <EntityName
                      name={n.canonical_name}
                      entityType={n.entity_type}
                      className="min-w-0 truncate"
                    />
                    <span className="shrink-0 text-xs text-slate-500">
                      {n.shared_category_count}{" "}
                      {n.shared_category_count === 1 ? "category" : "categories"}
                    </span>
                  </span>
                </Link>
                <span
                  className="mt-1 flex flex-wrap gap-1"
                  data-testid="shared-category-names"
                >
                  {n.shared_categories.map((category) => (
                    <Link
                      key={category.id}
                      to={`/wikipedia-categories/${category.id}`}
                      className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                    >
                      {category.name}
                    </Link>
                  ))}
                </span>
              </li>
            ))}
          </ul>

          {/* Hidden once the list is short of the requested limit (nothing
              further to reveal) or the server ceiling is reached. */}
          {neighbours.length >= limit && limit < MAX_SHARED_CATEGORIES && (
            <button
              type="button"
              onClick={() =>
                setLimit((current) =>
                  Math.min(
                    current + SHARED_CATEGORY_PAGE_SIZE,
                    MAX_SHARED_CATEGORIES
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
