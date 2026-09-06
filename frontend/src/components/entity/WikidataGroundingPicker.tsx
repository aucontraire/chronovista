/**
 * WikidataGroundingPicker — reusable Wikidata candidate search + selection
 * control.
 *
 * Extracted from `CreateEntityModal` (Feature 067, US3) so the same
 * search → shortlist → select flow can be reused by the post-creation
 * re-grounding dialog (Feature 073, US1) without duplicating the debounce,
 * auto-search, and stale-search-discard logic.
 *
 * Encapsulates:
 * - Debouncing the caller-supplied `name` (450 ms) before searching, and
 *   surfacing a "searching…" state while the debounce is still settling
 * - Auto-searching once the debounced name/type are both present — no manual
 *   trigger required
 * - Discarding a stale search (and the caller's current selection) whenever
 *   `name`/`entityType` change, so an approval never silently carries over to
 *   a different name/type
 * - Rendering the ranked shortlist with type-match/statement/sitelink
 *   signals and a stub warning
 * - The "Grounded to …" chip once a candidate is selected, with a control to
 *   clear it
 * - An optional "Create without grounding" skip affordance
 *
 * Fully controlled for the one piece of state the caller must know about —
 * the selected candidate — via `selectedCandidate` / `onSelectCandidate`.
 * Everything else (the search text's debounce, the shortlist, the skip
 * flag) is internal.
 */

import { useCallback, useEffect, useId, useState } from "react";
import { useDebounce } from "../../hooks/useDebounce";
import { useWikidataCandidates } from "../../hooks/useEntityMentions";
import type { WikidataCandidate } from "../../api/entityMentions";

export interface WikidataGroundingPickerProps {
  /**
   * Proposed name to search Wikidata for. Passed raw (not pre-debounced) —
   * this component debounces it internally by 450 ms before searching, so
   * typing doesn't spam the lookup on every keystroke.
   */
  name: string;
  /** Entity type (e.g. "person", "organization", "place"). */
  entityType: string;
  /**
   * The candidate the caller currently has approved, if any. Fully
   * controlled — this component never holds its own copy of the selection
   * beyond what it reports via `onSelectCandidate`.
   */
  selectedCandidate: WikidataCandidate | null;
  /**
   * Fires whenever the selection changes: with a candidate when the user
   * picks one, or `null` when they clear it — including the implicit clear
   * this component performs whenever `name`/`entityType` change (a candidate
   * approved for one name/type must not silently carry over to another).
   */
  onSelectCandidate: (candidate: WikidataCandidate | null) => void;
  /** Disables every interactive control, e.g. while the caller's form is submitting. */
  disabled?: boolean;
  /** Section heading. Defaults to "Ground in Wikidata". */
  heading?: string;
  /** Whether to append an "— optional" qualifier next to the heading. */
  optional?: boolean;
  /** Whether to show the "Create without grounding" skip affordance. */
  allowSkip?: boolean;
}

/**
 * Search → shortlist → select control for grounding an entity to a Wikidata
 * item.
 *
 * @example
 * ```tsx
 * const [selected, setSelected] = useState<WikidataCandidate | null>(null);
 * <WikidataGroundingPicker
 *   name={name}
 *   entityType={entityType}
 *   selectedCandidate={selected}
 *   onSelectCandidate={setSelected}
 * />
 * ```
 */
export function WikidataGroundingPicker({
  name,
  entityType,
  selectedCandidate,
  onSelectCandidate,
  disabled = false,
  heading = "Ground in Wikidata",
  optional = true,
  allowSkip = true,
}: WikidataGroundingPickerProps) {
  const [groundingSkipped, setGroundingSkipped] = useState(false);

  // Radio group `name` for candidate selection — unique per mounted instance.
  const wikidataGroupName = useId();

  // Debounced so typing doesn't spam the lookup on every keystroke.
  const debouncedName = useDebounce(name, 450);
  const wikidata = useWikidataCandidates(debouncedName, entityType);
  // True while a debounced search is pending — lets the UI show a
  // "searching" state immediately instead of a blank gap before the
  // debounce settles.
  const isNameSettling =
    name !== "" && entityType !== "" && debouncedName !== name;

  // Discard a stale search (and the caller's selection) when the effective
  // name or type changes — a candidate approved for one name/type must not
  // silently carry over to a different one.
  useEffect(() => {
    setGroundingSkipped(false);
    wikidata.reset();
    onSelectCandidate(null);
    // Intentionally depends on name/entityType only, not on `wikidata` (a
    // new object every render) or `onSelectCandidate` (may not be stable
    // across the caller's renders), to avoid a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, entityType]);

  // Auto-search once the debounced name/type are both present — replaces a
  // manual "Search Wikidata" trigger so grounding is discoverable without
  // the user having to find a button.
  useEffect(() => {
    if (debouncedName !== "" && entityType !== "") {
      wikidata.search();
    }
    // Intentionally depends on the debounced name/entityType only, not on
    // `wikidata` (a new object every render), to avoid a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedName, entityType]);

  const handleSelect = useCallback(
    (candidate: WikidataCandidate) => {
      onSelectCandidate(candidate);
    },
    [onSelectCandidate]
  );

  const handleClearSelection = useCallback(() => {
    onSelectCandidate(null);
  }, [onSelectCandidate]);

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-gray-700">
          {heading}{" "}
          {optional && (
            <span className="text-xs font-normal text-gray-400">
              — optional
            </span>
          )}
        </span>
        {wikidata.hasSearched && (
          <button
            type="button"
            onClick={() => wikidata.search()}
            disabled={disabled || wikidata.isFetching}
            className="
              text-xs text-indigo-600 hover:text-indigo-700
              font-medium
              disabled:opacity-50 disabled:cursor-not-allowed
              focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 rounded
            "
          >
            Search again
          </button>
        )}
      </div>

      {!groundingSkipped && (
        <div className="space-y-2">
          {(isNameSettling || (wikidata.hasSearched && wikidata.isLoading)) && (
            <p
              role="status"
              aria-live="polite"
              className="flex items-center gap-2 text-xs text-gray-500"
            >
              <span
                className="w-3.5 h-3.5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"
                aria-hidden="true"
              />
              Searching Wikidata…
            </p>
          )}

          {!isNameSettling &&
            wikidata.hasSearched &&
            !wikidata.isLoading &&
            wikidata.unavailable && (
            <p
              role="status"
              aria-live="polite"
              className="px-3 py-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md"
            >
              Couldn&rsquo;t reach Wikidata. You can still create this entity
              without grounding.
            </p>
          )}

          {!isNameSettling &&
            wikidata.hasSearched &&
            !wikidata.isLoading &&
            !wikidata.unavailable &&
            wikidata.candidates.length === 0 && (
              <p
                role="status"
                aria-live="polite"
                className="px-3 py-2 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-md"
              >
                No matching entries found on Wikidata. You can still create
                this entity without grounding.
              </p>
            )}

          {!isNameSettling &&
            !wikidata.isLoading &&
            wikidata.candidates.length > 0 && (
            <fieldset>
              <legend className="sr-only">
                Select a Wikidata match to ground this entity (optional)
              </legend>
              <div
                role="radiogroup"
                aria-label="Wikidata candidates"
                className="space-y-2"
              >
                {wikidata.candidates.map((candidate) => {
                  const isSelected =
                    selectedCandidate?.qid === candidate.qid;
                  return (
                    <label
                      key={candidate.qid}
                      className={`
                        flex items-start gap-3
                        px-3 py-2.5
                        border rounded-lg cursor-pointer
                        ${
                          isSelected
                            ? "border-indigo-400 bg-indigo-50"
                            : "border-gray-200 hover:bg-gray-50"
                        }
                      `}
                    >
                      <input
                        type="radio"
                        name={wikidataGroupName}
                        value={candidate.qid}
                        checked={isSelected}
                        onChange={() => handleSelect(candidate)}
                        disabled={disabled}
                        className="mt-1"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900">
                            {candidate.label}
                          </span>
                          <span className="text-xs text-gray-400">
                            {candidate.qid}
                          </span>
                          {candidate.type_matches ? (
                            <span className="text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
                              Type match
                            </span>
                          ) : (
                            <span className="text-xs font-medium text-gray-500 bg-gray-100 border border-gray-200 rounded-full px-2 py-0.5">
                              Type may differ
                            </span>
                          )}
                        </div>
                        {candidate.description !== null && (
                          <p className="mt-0.5 text-xs text-gray-500">
                            {candidate.description}
                          </p>
                        )}
                        <p className="mt-1 text-xs text-gray-400">
                          {candidate.statement_count} statements ·{" "}
                          {candidate.sitelink_count} sitelinks
                        </p>
                        {candidate.is_stub && (
                          <p
                            role="note"
                            className="inline-block mt-1 px-2 py-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md"
                          >
                            Stub — limited Wikidata data available
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          )}

          {selectedCandidate !== null ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Grounded to</span>
              <span
                className="
                  inline-flex items-center gap-1.5
                  px-2.5 py-0.5
                  text-xs font-medium
                  bg-indigo-50 text-indigo-700 border border-indigo-200
                  rounded-full
                "
              >
                {selectedCandidate.label} ({selectedCandidate.qid})
                <button
                  type="button"
                  onClick={handleClearSelection}
                  disabled={disabled}
                  aria-label={`Remove grounding to ${selectedCandidate.label}`}
                  className="
                    inline-flex items-center justify-center
                    w-3.5 h-3.5 -mr-0.5
                    rounded-full
                    text-indigo-400 hover:text-indigo-700 hover:bg-indigo-100
                    focus:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500
                    disabled:opacity-50 disabled:cursor-not-allowed
                  "
                >
                  <svg
                    className="w-2.5 h-2.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </span>
            </div>
          ) : (
            allowSkip &&
            !isNameSettling &&
            wikidata.hasSearched &&
            !wikidata.isLoading && (
              <button
                type="button"
                onClick={() => setGroundingSkipped(true)}
                disabled={disabled}
                className="
                  text-xs text-gray-500 hover:text-gray-700
                  font-medium
                  disabled:opacity-50 disabled:cursor-not-allowed
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 rounded
                "
              >
                Create without grounding
              </button>
            )
          )}
        </div>
      )}

      {groundingSkipped && (
        <p className="text-xs text-gray-400">
          Creating without Wikidata grounding.
        </p>
      )}
    </div>
  );
}

export default WikidataGroundingPicker;
