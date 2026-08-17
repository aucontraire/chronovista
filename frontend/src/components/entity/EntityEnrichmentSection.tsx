/**
 * EntityEnrichmentSection — displays external knowledge-base enrichment data
 * for a named entity (Feature 067, US2).
 *
 * Renders:
 * - Grounded properties (a heterogeneous key/value bag) as a definition list
 * - External identifier links (e.g. Wikidata, DBpedia), each opening in a new
 *   tab, with a "verified" badge for human-verified identifiers
 * - A subtle "Not grounded" empty state when no enrichment data is available
 *
 * The backend intentionally does not send `status` or `link_provenance` — the
 * only signals this component reads are `grounded`, `properties`, and
 * `identifiers`.
 */

import type {
  EntityEnrichment,
  EntityPropertyValue,
} from "../../api/entityMentions";

export interface EntityEnrichmentSectionProps {
  /** Enrichment data from the entity detail response; absent on older payloads. */
  enrichment?: EntityEnrichment;
}

/**
 * Turns a snake_case property key into a human-readable label, e.g.
 * "country_of_citizenship" -> "Country Of Citizenship".
 */
function humanizePropertyKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatPropertyValues(value: EntityPropertyValue): string {
  return (value.values ?? []).join(", ");
}

function VerifiedBadge() {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-100 text-emerald-700 border border-emerald-200"
      aria-label="human-verified"
      title="Human-verified"
    >
      Verified
    </span>
  );
}

export function EntityEnrichmentSection({
  enrichment,
}: EntityEnrichmentSectionProps) {
  const properties = enrichment?.properties ?? {};
  const identifiers = enrichment?.identifiers ?? [];
  const propertyEntries = Object.entries(properties);
  const hasProperties = propertyEntries.length > 0;
  const hasIdentifiers = identifiers.length > 0;
  const isNotGrounded =
    !enrichment || !enrichment.grounded || (!hasProperties && !hasIdentifiers);

  return (
    <section aria-labelledby="entity-enrichment-heading" className="mb-6">
      <h2
        id="entity-enrichment-heading"
        className="text-lg font-semibold text-gray-900 mb-3"
      >
        Enrichment
      </h2>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        {isNotGrounded ? (
          <p
            className="text-sm text-gray-400 italic"
            data-testid="enrichment-not-grounded"
          >
            Not grounded — no external knowledge-base match found for this
            entity.
          </p>
        ) : (
          <div className="space-y-4">
            {hasProperties && (
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                {propertyEntries.map(([key, value]) => (
                  <div key={key} className="flex flex-col">
                    <dt className="text-xs font-medium text-gray-500">
                      {humanizePropertyKey(key)}
                    </dt>
                    <dd className="text-sm text-gray-800">
                      {formatPropertyValues(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}

            {hasIdentifiers && (
              <div className={hasProperties ? "pt-3 border-t border-slate-100" : ""}>
                <h3 className="text-xs font-medium text-gray-500 mb-2">
                  External identifiers
                </h3>
                <ul className="flex flex-wrap gap-2">
                  {identifiers.map((identifier) => (
                    <li key={`${identifier.source}-${identifier.id}`}>
                      <a
                        href={identifier.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full hover:bg-indigo-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 transition-colors"
                      >
                        <span className="capitalize">{identifier.source}</span>
                        {identifier.verified && <VerifiedBadge />}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
