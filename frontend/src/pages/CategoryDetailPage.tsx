/**
 * CategoryDetailPage — the active library entities in one Wikipedia category
 * (Feature 086). Reached from a category chip on the entity page.
 *
 * Membership is an editorial fact, so the page states it plainly. Members
 * load incrementally (bounded first page, IntersectionObserver sentinel) and
 * each links to its own entity page.
 */

import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import { EntityName } from "../components/EntityName";
import { ErrorState } from "../components/ErrorState";
import { SkipLink } from "../components/SkipLink";
import { useCategoryDetail } from "../hooks/useCategoryDetail";
import { useCategoryEntities } from "../hooks/useCategoryEntities";

const MAIN_CONTENT_ID = "category-main-content";

function MembersLoading() {
  return (
    <div
      role="status"
      aria-label="Loading entities"
      aria-busy="true"
      aria-live="polite"
      className="flex flex-col gap-2 animate-pulse"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <div
          key={i}
          className="h-10 rounded-lg bg-gray-200"
          aria-hidden="true"
        />
      ))}
      <span className="sr-only">Loading entities...</span>
    </div>
  );
}

function entityCountText(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "entity" : "entities"}`;
}

export function CategoryDetailPage() {
  const { categoryId } = useParams<{ categoryId: string }>();
  const detail = useCategoryDetail(categoryId);
  const members = useCategoryEntities(categoryId);

  const categoryName = detail.category?.name;
  useEffect(() => {
    document.title = categoryName
      ? `${categoryName} - ChronoVista`
      : "Category - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, [categoryName]);

  const shell = (children: React.ReactNode) => (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8"
      >
        {children}
      </main>
    </>
  );

  if (detail.isLoading) {
    return shell(<MembersLoading />);
  }

  if (detail.isNotFound) {
    return shell(
      <div
        role="alert"
        className="rounded-xl border border-gray-200 bg-white p-8 text-center"
        data-testid="category-not-found"
      >
        <h1 className="mb-2 text-2xl font-bold text-gray-900">
          Category not found
        </h1>
        <p className="mb-6 text-gray-600">
          This category does not exist or the link is not valid.
        </p>
        <Link
          to="/entities"
          className="text-indigo-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          Browse all entities
        </Link>
      </div>
    );
  }

  if (detail.isError || !detail.category) {
    return shell(
      <ErrorState
        error={detail.error}
        title="Could not load category"
        onRetry={detail.retry}
      />
    );
  }

  const { category } = detail;

  return shell(
    <>
      <header className="mb-6">
        <p className="text-sm text-gray-500">Wikipedia category</p>
        <h1 className="text-3xl font-bold text-gray-900">{category.name}</h1>
        <p className="mt-1 text-sm text-gray-600" data-testid="category-count">
          {entityCountText(category.member_count)} in your library
        </p>
        <a
          href={category.wikipedia_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="View this category on Wikipedia (opens in a new tab)"
          className="mt-2 inline-flex items-center gap-1 text-sm text-indigo-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
          data-testid="category-wikipedia-link"
        >
          View on Wikipedia
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-3.5 w-3.5"
            aria-hidden="true"
          >
            <path d="M11 3a1 1 0 1 0 0 2h2.586l-6.293 6.293a1 1 0 1 0 1.414 1.414L15 6.414V9a1 1 0 1 0 2 0V4a1 1 0 0 0-1-1h-5Z" />
            <path d="M5 5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-3a1 1 0 1 0-2 0v3H5V7h3a1 1 0 0 0 0-2H5Z" />
          </svg>
        </a>
        {category.is_broad && (
          <p
            className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
            data-testid="category-broad-note"
          >
            This is a broad grouping: it covers a wide range of entities.
          </p>
        )}
      </header>

      <section aria-labelledby="category-members-heading">
        <h2
          id="category-members-heading"
          className="mb-3 text-lg font-semibold text-gray-900"
        >
          Entities in this category
        </h2>

        {members.isLoading && <MembersLoading />}

        {/* Non-blocking: the header above stays usable. */}
        {members.isError && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-center"
            data-testid="category-members-error"
          >
            <p className="mb-2 font-medium text-red-800">
              Couldn&apos;t load the entities in this category.
            </p>
            <button
              type="button"
              onClick={members.retry}
              className="rounded-md bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Retry
            </button>
          </div>
        )}

        {!members.isLoading &&
          !members.isError &&
          members.entities.length === 0 && (
            <p
              role="status"
              className="rounded-lg border border-gray-200 bg-white p-6 text-center text-gray-600"
              data-testid="category-empty"
            >
              No entities in your library are in this category.
            </p>
          )}

        {members.entities.length > 0 && (
          <ul className="flex flex-col gap-2" aria-label="Entities in this category">
            {members.entities.map((entity) => (
              <li key={entity.entity_id}>
                <Link
                  to={`/entities/${entity.entity_id}`}
                  className="flex items-center rounded-lg border border-gray-100 bg-white px-4 py-2 shadow-sm hover:border-gray-200 hover:shadow focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
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
            className="py-3 text-center text-sm text-gray-500"
          >
            Loading more entities...
          </p>
        )}

        {!members.isError && (
          <div ref={members.loadMoreRef} className="h-4" aria-hidden="true" />
        )}

        {!members.hasNextPage &&
          !members.isError &&
          members.entities.length > 0 && (
            <p
              className="py-3 text-center text-sm text-gray-500"
              data-testid="category-all-loaded"
            >
              All {entityCountText(members.entities.length)} loaded
            </p>
          )}
      </section>
    </>
  );
}
