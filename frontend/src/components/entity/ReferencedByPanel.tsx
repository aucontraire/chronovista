/**
 * ReferencedByPanel — "Referenced by" on the entity detail page (Feature 087).
 *
 * Lists entities whose Wikidata statements point at the subject, grouped by
 * relationship. Each group shows the backend-supplied label AND attribution:
 * the attribution frames the membership as Wikidata's claim, not an assertion
 * of this app, so it is content, not decoration.
 */

import { Link } from "react-router-dom";

import { EntityName } from "../EntityName";
import { useReferencedBy } from "../../hooks/useReferencedBy";

interface ReferencedByPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function ReferencedByPanel({ entityId, className = "" }: ReferencedByPanelProps) {
  const { groups, isLoading, isError } = useReferencedBy(entityId);

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
          {groups.map((group) => {
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
