/**
 * EntityTagFootprintSection — claim a tag that would newly associate videos
 * with this entity (Feature 097, US4).
 *
 * Shows every name+type-matching tag the backend returns, even at a delta of 0:
 * linking then adds no videos but formally owns the tag. Renders nothing when
 * there is no matching tag. A tag already linked to a different
 * entity is shown as an informational note only: re-assignment is not supported,
 * so no link action is offered for it.
 */

import { useId, useState } from "react";

import {
  LinkConsequenceInfo,
  TagInspectLink,
} from "./TagInspectControls";
import { useEntityTagFootprint, useLinkEntityTag } from "../../hooks/useEntityTags";

export interface EntityTagFootprintSectionProps {
  entityId: string;
  entityName: string;
  /** Sent with the link request so the server can create the identity link. */
  entityType: string;
}

export function EntityTagFootprintSection({
  entityId,
  entityName,
  entityType,
}: EntityTagFootprintSectionProps) {
  const headingId = useId();
  const { data } = useEntityTagFootprint(entityId);
  const link = useLinkEntityTag(entityId);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const matches = data?.matches ?? [];

  // Keep the section mounted while a success message is showing: the refetch
  // may change the match list, which would otherwise erase the confirmation.
  if (matches.length === 0 && successMsg === null) return null;

  async function doLink(normalizedForm: string) {
    setSuccessMsg(null);
    setErrorMsg(null);
    try {
      await link.mutateAsync({ normalizedForm, entityType });
      setSuccessMsg(`Linked "${normalizedForm}" to ${entityName}.`);
    } catch (err: unknown) {
      const detail = (err as { detail?: string } | null)?.detail;
      setErrorMsg(detail ?? "Could not link that tag. Please try again.");
    }
  }

  return (
    <section aria-labelledby={headingId} className="mb-6">
      <h2 id={headingId} className="text-lg font-semibold text-gray-900 mb-3">
        Tag footprint
      </h2>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        {matches.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {matches.map((m) => {
              const ownedByOther =
                m.owned_by_entity_id !== null && m.owned_by_entity_id !== entityId;
              const ownedByThis = m.owned_by_entity_id === entityId;
              return (
                <li key={m.normalized_form} className="py-2 first:pt-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-sm text-slate-900">
                      <TagInspectLink normalizedForm={m.normalized_form} />{" "}
                      {m.would_newly_associate > 0
                        ? `— associates ${m.would_newly_associate} more video${
                            m.would_newly_associate === 1 ? "" : "s"
                          }`
                        : "— its videos are already associated by name. Link to formally own this tag (adds 0 new videos)."}
                    </span>
                    {ownedByOther ? (
                      <p className="text-sm text-slate-600">
                        Already linked to another entity — unlink it in tag
                        management to claim it here.
                      </p>
                    ) : ownedByThis ? (
                      <span className="text-sm text-green-700">✓ Linked</span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => void doLink(m.normalized_form)}
                        disabled={link.isPending}
                        aria-label={`Link tag ${m.normalized_form}`}
                        className="px-3 py-1 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                      >
                        Link
                      </button>
                      <LinkConsequenceInfo />
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {successMsg && (
          <p className="mt-3 text-sm text-green-700" role="status">
            {successMsg}
          </p>
        )}
        {errorMsg && (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {errorMsg}
          </p>
        )}
      </div>
    </section>
  );
}
