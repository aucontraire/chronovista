/**
 * CategoryMembersPanel — "Category members" on the entity detail page
 * (Feature 090).
 *
 * An in-context inverse view: pick one of this entity's categories and see
 * its other active members without leaving the page. The selector reuses the
 * cached `useAllCategories` list; the members reuse `useCategoryEntities`.
 */

import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { EntityName } from "../EntityName";
import { useAllCategories } from "../../hooks/useAllCategories";
import { useCategoryEntities } from "../../hooks/useCategoryEntities";

/** Server ceiling; the selector must reach every category the All tab can. */
const MAX_ENTITY_CATEGORIES = 200;

interface CategoryMembersPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

interface MembersListProps {
  categoryId: string;
  subjectId: string;
}

function MembersList({ categoryId, subjectId }: MembersListProps) {
  const members = useCategoryEntities(categoryId);
  const others = members.entities.filter(
    (entity) => entity.entity_id !== subjectId
  );

  return (
    <div className="mt-3" data-testid="category-members-list">
      {members.isLoading && (
        <p
          role="status"
          aria-busy="true"
          className="text-sm text-slate-600"
          data-testid="category-members-loading"
        >
          Loading members…
        </p>
      )}

      {members.isError && (
        <div
          role="alert"
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          data-testid="category-members-error"
        >
          <p className="mb-2">
            Couldn&apos;t load the members of this category. The rest of this
            page is unaffected.
          </p>
          <button
            type="button"
            onClick={members.retry}
            className="text-indigo-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            Retry
          </button>
        </div>
      )}

      {!members.isLoading &&
        !members.isError &&
        !members.hasNextPage &&
        others.length === 0 && (
        <p
          className="text-sm text-slate-600"
          data-testid="category-members-empty"
        >
          No other entities in your library are in this category.
        </p>
      )}

      {others.length > 0 && (
        <ul
          className="flex flex-col gap-2"
          aria-label="Other entities in this category"
        >
          {others.map((entity) => (
            <li key={entity.entity_id}>
              <Link
                to={`/entities/${entity.entity_id}`}
                className="flex items-center rounded-lg border border-gray-100 bg-white px-3 py-2 shadow-sm hover:border-gray-200 hover:shadow focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                <EntityName
                  name={entity.canonical_name}
                  entityType={entity.entity_type}
                />
              </Link>
            </li>
          ))}
        </ul>
      )}

      {members.isFetchingNextPage && (
        <p
          role="status"
          aria-live="polite"
          className="py-2 text-center text-sm text-gray-500"
        >
          Loading more entities…
        </p>
      )}

      {!members.isError && (
        <div ref={members.loadMoreRef} className="h-4" aria-hidden="true" />
      )}
    </div>
  );
}

export function CategoryMembersPanel({
  entityId,
  className = "",
}: CategoryMembersPanelProps) {
  const selectId = useId();
  const { categories, isLoading, isError } = useAllCategories(
    entityId,
    MAX_ENTITY_CATEGORIES
  );
  const [chosenId, setChosenId] = useState<string | null>(null);

  // Default to the first (most specific) category; fall back if a prior
  // choice is no longer in the list.
  const selectedId =
    categories.find((category) => category.id === chosenId)?.id ??
    categories[0]?.id;

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="category-members-panel"
      data-testid="category-members-panel"
    >
      <h2
        id="category-members-panel"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        Category members
      </h2>

      {isError && (
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="category-members-categories-error"
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
        <p
          className="text-sm text-slate-600"
          data-testid="category-members-no-categories"
        >
          This entity doesn&apos;t belong to any categories.
        </p>
      )}

      {!isError && categories.length > 0 && selectedId && (
        <>
          <label
            htmlFor={selectId}
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Category
          </label>
          <select
            id={selectId}
            value={selectedId}
            onChange={(event) => setChosenId(event.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            data-testid="category-members-select"
          >
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name} ({category.member_count})
              </option>
            ))}
          </select>

          <MembersList categoryId={selectedId} subjectId={entityId} />
        </>
      )}
    </section>
  );
}
