/**
 * EntityEnrichmentSection — displays external knowledge-base enrichment data
 * for a named entity (Feature 067, US2), plus the "Change link" affordance
 * for re-grounding it to a different Wikidata match (Feature 073, US1).
 *
 * Renders:
 * - Grounded properties (a heterogeneous key/value bag) as a definition list
 * - External identifier links (e.g. Wikidata, DBpedia), each opening in a new
 *   tab, with a "verified" badge for human-verified identifiers
 * - A subtle "Not grounded" empty state when no enrichment data is available
 * - A "Change link" control (FR-010) that opens an inline editor with a
 *   `WikidataGroundingPicker` and an editable description field, pre-filled
 *   from the selected match's description (FR-011) — empty when the match
 *   has none, never falling back to the entity's current description.
 * - A "Refresh" control (FR-010, US2), shown only when the entity currently
 *   has a Wikidata link — re-fetches facts for that link without changing
 *   the link or description, and without opening the picker.
 *
 * The backend intentionally does not send `status` or `link_provenance` — the
 * only signals this component reads from `enrichment` are `grounded`,
 * `properties`, and `identifiers`.
 *
 * "Change link" (re-link) and "Refresh" each use their own `useRegroundEntity`
 * mutation instance so one action's pending/error state never bleeds into the
 * other's UI (e.g. Refresh must never show "Refreshing…" because a re-link
 * confirm happens to be in flight).
 */

import { useEffect, useRef, useState } from "react";
import type {
  EntityEnrichment,
  EntityPropertyValue,
  WikidataCandidate,
} from "../../api/entityMentions";
import { useRegroundEntity } from "../../hooks/useRegroundEntity";
import { WikidataGroundingPicker } from "./WikidataGroundingPicker";

export interface EntityEnrichmentSectionProps {
  /** UUID of the named entity — required to submit a re-link. */
  entityId: string;
  /** Entity type (e.g. "person", "organization", "place"), used to rank/filter Wikidata matches. */
  entityType: string;
  /** The entity's current display name — used as the initial Wikidata search query. */
  canonicalName: string;
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
  entityId,
  entityType,
  canonicalName,
  enrichment,
}: EntityEnrichmentSectionProps) {
  const properties = enrichment?.properties ?? {};
  const identifiers = enrichment?.identifiers ?? [];
  const propertyEntries = Object.entries(properties);
  const hasProperties = propertyEntries.length > 0;
  const hasIdentifiers = identifiers.length > 0;
  const isNotGrounded =
    !enrichment || !enrichment.grounded || (!hasProperties && !hasIdentifiers);
  // Refresh needs a *current Wikidata link* specifically — the backend 400s
  // otherwise — so check the identifiers list directly rather than the more
  // permissive `grounded`/`isNotGrounded` signals above.
  const hasWikidataLink = identifiers.some(
    (identifier) => identifier.source === "wikidata"
  );

  // ---------------------------------------------------------------------------
  // "Change link" editor (Feature 073, US1)
  //
  // Mirrors the `EntityNameEditor` / `AliasRow` `isEditing` toggle pattern
  // already used on this page: a trigger button, an inline panel with
  // labeled controls and Confirm/Cancel, Escape-to-cancel, and focus
  // returned to the trigger on close.
  // ---------------------------------------------------------------------------

  const [isEditingLink, setIsEditingLink] = useState(false);
  const [searchName, setSearchName] = useState(canonicalName);
  const [selectedCandidate, setSelectedCandidate] =
    useState<WikidataCandidate | null>(null);
  const [descriptionInput, setDescriptionInput] = useState("");
  // Feature 067 (US3)-style "Option C": true once the user has edited the
  // Description field themselves, so a later candidate selection never
  // clobbers (or re-populates) what they typed.
  const [descriptionTouched, setDescriptionTouched] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const changeLinkButtonRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const linkMutation = useRegroundEntity();

  useEffect(() => {
    if (isEditingLink) {
      searchInputRef.current?.focus();
    }
  }, [isEditingLink]);

  // ---------------------------------------------------------------------------
  // "Refresh" (Feature 073, US2)
  //
  // A single action on the entity's CURRENT Wikidata link: re-fetches facts
  // without touching the link or the description, and without opening the
  // "Change link" editor/picker. Its own mutation instance (see module doc)
  // keeps its pending/error state independent of the re-link flow.
  // ---------------------------------------------------------------------------

  const refreshMutation = useRegroundEntity();
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshMessageType, setRefreshMessageType] = useState<
    "success" | "error" | null
  >(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
      }
    };
  }, []);

  function handleRefresh() {
    if (refreshMutation.isPending) return; // no double-submit

    setRefreshMessage(null);
    setRefreshMessageType(null);
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    refreshMutation.mutate(
      // No `approved_identifier` and no `description` key at all — this is
      // the refresh branch (re-fetch facts for the CURRENT link only). Never
      // send `approved_identifier: ""` or any identifier here; that would be
      // a re-link, not a refresh.
      { entityId, data: {} },
      {
        onSuccess: () => {
          setRefreshMessage("Refreshing Wikidata facts…");
          setRefreshMessageType("success");
          refreshTimerRef.current = setTimeout(() => {
            setRefreshMessage(null);
            setRefreshMessageType(null);
          }, 3000);
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          const msg =
            status === 400
              ? "This entity has no current Wikidata link to refresh."
              : status === 404
                ? "Entity not found. Please refresh the page."
                : "Failed to refresh Wikidata data. Please try again.";
          setRefreshMessage(msg);
          setRefreshMessageType("error");
        },
      }
    );
  }

  function enterEditMode() {
    setSearchName(canonicalName);
    setSelectedCandidate(null);
    setDescriptionInput("");
    setDescriptionTouched(false);
    setErrorMsg(null);
    setIsEditingLink(true);
  }

  function exitEditMode() {
    setIsEditingLink(false);
    // Return focus to the trigger for keyboard users (WCAG 2.4.3).
    requestAnimationFrame(() => changeLinkButtonRef.current?.focus());
  }

  function handleCancel() {
    setErrorMsg(null);
    exitEditMode();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    event.stopPropagation();
    if (event.key === "Escape") {
      handleCancel();
    }
  }

  function handleSelectCandidate(candidate: WikidataCandidate | null) {
    setSelectedCandidate(candidate);
    // FR-011: pre-fill an editable field with the selected match's
    // description; leave it empty when the match has none — never fall back
    // to the entity's current description. Never overwrites text the user
    // already typed.
    if (candidate !== null && !descriptionTouched && descriptionInput.trim() === "") {
      setDescriptionInput(candidate.description ?? "");
    }
  }

  function handleConfirm() {
    if (linkMutation.isPending || selectedCandidate === null) return;

    setErrorMsg(null);
    linkMutation.mutate(
      {
        entityId,
        data: {
          approved_identifier: { source: "wikidata", id: selectedCandidate.qid },
          // FR-011: the entity's description is updated to exactly the value
          // the curator confirms, whatever that is (including cleared).
          description: descriptionInput,
        },
      },
      {
        onSuccess: () => {
          exitEditMode();
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          if (status === 404) {
            setErrorMsg("Entity not found. Please refresh the page.");
          } else if (status === 422) {
            setErrorMsg(err.message || "Invalid request.");
          } else {
            setErrorMsg(
              "Failed to update the Wikidata link. Please try again."
            );
          }
          // Editor stays open and the user's input is preserved.
        },
      }
    );
  }

  return (
    <section aria-labelledby="entity-enrichment-heading" className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2
          id="entity-enrichment-heading"
          className="text-lg font-semibold text-gray-900"
        >
          Enrichment
        </h2>
        {!isEditingLink && (
          <div className="flex items-center gap-2">
            {hasWikidataLink && (
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshMutation.isPending || linkMutation.isPending}
                aria-label={`Refresh Wikidata data for ${canonicalName}`}
                aria-busy={refreshMutation.isPending ? "true" : undefined}
                className="
                  inline-flex items-center gap-1
                  min-h-[32px]
                  px-2.5 py-1
                  text-xs font-medium text-slate-600
                  bg-slate-100 hover:bg-slate-200
                  border border-slate-200
                  rounded-full
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors
                "
              >
                {refreshMutation.isPending ? "Refreshing…" : "Refresh"}
              </button>
            )}
            <button
              ref={changeLinkButtonRef}
              type="button"
              onClick={enterEditMode}
              disabled={refreshMutation.isPending}
              aria-label={`Change Wikidata link for ${canonicalName}`}
              className="
                inline-flex items-center gap-1
                min-h-[32px]
                px-2.5 py-1
                text-xs font-medium text-slate-600
                bg-slate-100 hover:bg-slate-200
                border border-slate-200
                rounded-full
                focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors
              "
            >
              Change link
            </button>
          </div>
        )}
      </div>

      {!isEditingLink && refreshMessage && (
        <p
          role={refreshMessageType === "error" ? "alert" : "status"}
          aria-live="polite"
          className={`mb-3 text-sm rounded-md px-3 py-1.5 border ${
            refreshMessageType === "error"
              ? "text-red-700 bg-red-50 border-red-200"
              : "text-slate-600 bg-slate-100 border-slate-200"
          }`}
        >
          {refreshMessage}
        </p>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        {isEditingLink ? (
          <div
            className="space-y-3"
            onKeyDown={handleKeyDown}
            role="group"
            aria-label={`Change Wikidata link for ${canonicalName}`}
          >
            <div>
              <label
                htmlFor="reground-search-name"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Search Wikidata for
              </label>
              <input
                ref={searchInputRef}
                id="reground-search-name"
                type="text"
                value={searchName}
                onChange={(e) => setSearchName(e.target.value)}
                disabled={linkMutation.isPending}
                className="
                  w-full px-3 py-2
                  text-sm text-gray-900
                  border border-slate-300 rounded-md
                  focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                  disabled:bg-slate-100 disabled:text-slate-500
                "
              />
            </div>

            {searchName.trim() !== "" && (
              <WikidataGroundingPicker
                name={searchName}
                entityType={entityType}
                selectedCandidate={selectedCandidate}
                onSelectCandidate={handleSelectCandidate}
                disabled={linkMutation.isPending}
                heading="Wikidata matches"
                optional={false}
                allowSkip={false}
              />
            )}

            <div>
              <label
                htmlFor="reground-description-input"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Description
              </label>
              <textarea
                id="reground-description-input"
                value={descriptionInput}
                onChange={(e) => {
                  setDescriptionInput(e.target.value);
                  setDescriptionTouched(true);
                }}
                disabled={linkMutation.isPending}
                rows={3}
                placeholder="Short description of this entity…"
                className="
                  w-full px-3 py-2
                  text-sm text-gray-900
                  border border-slate-300 rounded-md
                  resize-none
                  focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                  disabled:bg-slate-100 disabled:text-slate-500
                "
              />
            </div>

            {linkMutation.isPending && (
              <p
                role="status"
                aria-live="polite"
                className="text-sm text-slate-600 bg-slate-100 border border-slate-200 rounded-md px-3 py-1.5"
              >
                Saving…
              </p>
            )}

            {errorMsg && (
              <p
                role="alert"
                className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-1.5"
              >
                {errorMsg}
              </p>
            )}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleConfirm}
                disabled={
                  linkMutation.isPending || selectedCandidate === null
                }
                aria-busy={linkMutation.isPending ? "true" : undefined}
                className="
                  min-h-[44px] min-w-[44px]
                  px-4 py-2
                  text-sm font-medium text-white
                  bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400
                  rounded-md
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
                  disabled:cursor-not-allowed
                  transition-colors
                "
              >
                {linkMutation.isPending ? "Saving…" : "Confirm link"}
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={linkMutation.isPending}
                className="
                  min-h-[44px] min-w-[44px]
                  px-4 py-2
                  text-sm font-medium text-slate-700
                  bg-white hover:bg-slate-50
                  border border-slate-300
                  rounded-md
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors
                "
              >
                Cancel
              </button>
            </div>
          </div>
        ) : isNotGrounded ? (
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
