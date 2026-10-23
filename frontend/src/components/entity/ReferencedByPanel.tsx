/**
 * ReferencedByPanel — "Referenced by" on the entity detail page (Feature 087).
 *
 * Lists entities whose Wikidata statements point at the subject, grouped by
 * relationship. Each group shows the backend-supplied label AND attribution:
 * the attribution frames the membership as Wikidata's claim, not an assertion
 * of this app, so it is content, not decoration.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EntityName } from "../EntityName";
import { useReferencedBy } from "../../hooks/useReferencedBy";

interface ReferencedByPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function ReferencedByPanel({ entityId, className = "" }: ReferencedByPanelProps) {
  const { groups: rawGroups, isLoading, isError } = useReferencedBy(entityId);
  const groups = Array.isArray(rawGroups) ? rawGroups : [];
  const [selectedType, setSelectedType] = useState<string | null>(null);

  // Only types present on at least one member are offered, so no option is dead.
  const typeOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const g of groups) {
      for (const m of g.members ?? []) for (const t of m.instance_of ?? []) seen.add(t);
    }
    return [...seen].sort((a, b) => a.localeCompare(b));
  }, [rawGroups]);

  const showFilter = typeOptions.length >= 2;
  // A stale selection (data refetched without that type) falls back to unfiltered.
  const activeType = showFilter && selectedType && typeOptions.includes(selectedType) ? selectedType : null;

  const visibleGroups = useMemo(() => {
    if (activeType === null) return groups;
    return groups
      .map((g) => ({ ...g, members: (g.members ?? []).filter((m) => (m.instance_of ?? []).includes(activeType)) }))
      .filter((g) => g.members.length > 0);
  }, [rawGroups, activeType]);

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="referenced-by-heading"
      data-testid="referenced-by-panel"
    >
      <h2 id="referenced-by-heading" className="mb-3 text-sm font-semibold text-slate-800">
        Referenced by
      </h2>

      {isLoading && (
        <p role="status" className="text-sm text-slate-500" data-testid="referenced-by-loading">
          Finding entities that reference this one…
        </p>
      )}

      {!isLoading && isError && (
        <p role="alert" className="text-sm text-amber-800" data-testid="referenced-by-error">
          Couldn&apos;t load referencing entities. The rest of this page is unaffected.
        </p>
      )}

      {!isLoading && !isError && groups.length === 0 && (
        <p role="status" className="text-sm text-slate-600" data-testid="referenced-by-empty">
          No entities in your library reference this one.
        </p>
      )}

      {!isLoading && !isError && groups.length > 0 && (
        <div className="flex flex-col gap-4">
          {showFilter && (
            <div
              role="group"
              aria-labelledby="referenced-by-filter-label"
              className="flex flex-wrap items-center gap-1.5"
              data-testid="referenced-by-type-filter"
            >
              <span id="referenced-by-filter-label" className="text-xs text-slate-500">
                Filter by type
              </span>
              {[null, ...typeOptions].map((type) => {
                const pressed = type === activeType;
                return (
                  <button
                    key={type ?? "__all__"}
                    type="button"
                    aria-pressed={pressed}
                    onClick={() => setSelectedType(type)}
                    className={`rounded-full border px-2.5 py-0.5 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                      pressed
                        ? "border-indigo-600 bg-indigo-600 text-white"
                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    {type ?? "All"}
                  </button>
                );
              })}
            </div>
          )}
          {showFilter && (
            <p role="status" className="sr-only">
              {activeType === null
                ? "Showing all types"
                : `Filtered to ${activeType}: ${visibleGroups.reduce((n, g) => n + g.members.length, 0)} shown`}
            </p>
          )}
          {visibleGroups.map((group) => {
            const headingId = `referenced-by-group-${group.key}`;
            const attributionId = `${headingId}-attribution`;
            return (
              <section
                key={group.key}
                aria-labelledby={headingId}
                aria-describedby={attributionId}
                data-testid={`referenced-by-group-${group.key}`}
              >
                <h3 id={headingId} className="text-sm font-medium text-slate-800">
                  {group.label}
                </h3>
                <p id={attributionId} className="mb-1 text-xs text-slate-500">
                  {group.attribution}
                </p>
                <ul className="flex flex-col gap-1">
                  {group.members.map((m) => (
                    <li key={m.entity_id}>
                      <Link
                        to={`/entities/${m.entity_id}`}
                        className="block rounded px-2 py-1.5 text-sm hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                      >
                        <EntityName
                          name={m.canonical_name}
                          entityType={m.entity_type}
                          className="min-w-0 truncate"
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
                {group.member_count > group.members.length && (
                  <p className="mt-1 px-2 text-xs text-slate-500">
                    Showing {group.members.length} of {group.member_count}
                  </p>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
