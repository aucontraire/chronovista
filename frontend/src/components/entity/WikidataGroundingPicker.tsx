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
 * - "Show more" pagination that appends the next page of candidates, so a
 *   match for a common name that ranks below the first page stays reachable
 * - A paste-a-Wikidata-QID fallback for a match that ranks below wherever
 *   paging has reached, with an optional `onPendingInvalidQidChange` report
 *   so the caller can warn before submit that typed-but-invalid text would
 *   otherwise be silently discarded
 * - The "Grounded to …" chip once a candidate is selected, with a control to
 *   clear it
 * - An optional "Create without grounding" skip affordance
 *
 * Fully controlled for the one piece of state the caller must know about —
 * the selected candidate — via `selectedCandidate` / `onSelectCandidate`.
 * Everything else (the search text's debounce, the shortlist, the skip
 * flag) is internal.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent } from "react";
import { useDebounce } from "../../hooks/useDebounce";
import { useWikidataCandidates } from "../../hooks/useEntityMentions";
import type { WikidataCandidate, WikidataCandidateByQidData } from "../../api/entityMentions";

/** A Wikidata QID: "Q" followed by digits with no leading zero, e.g. "Q42". */
const QID_FORMAT = /^Q[1-9]\d*$/;

/**
 * Extracts a Wikidata QID from either a bare QID or a genuine wikidata.org
 * item URL (`/wiki/Qn` or `/entity/Qn`). Deliberately narrow — it does not
 * grab any Q-token out of arbitrary text — so a non-wikidata URL or stray
 * text stays invalid rather than silently matching.
 */
function extractQid(raw: string): string | null {
  const s = raw.trim();
  const bare = s.toUpperCase();
  if (QID_FORMAT.test(bare)) return bare;
  const m = s.match(/wikidata\.org\/(?:wiki|entity)\/(Q[1-9]\d*)(?:[#?].*)?$/i);
  return m?.[1] ? m[1].toUpperCase() : null;
}

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
  /**
   * Reports the pasted QID field's text whenever it is non-empty AND does
   * not resolve to a valid QID (bare or wikidata.org URL) — `""` when the
   * field is empty, holds a valid QID/URL, or after a successful resolve.
   * Lets the caller warn before submitting that this text was typed but
   * never applied. Omit for callers (e.g. the re-grounding dialog) that
   * don't need this.
   */
  onPendingInvalidQidChange?: (text: string) => void;
}

/**
 * Imperative handle exposed via ref — lets a caller with its own confirm
 * flow (e.g. CreateEntityModal's unapplied-invalid-QID confirm) move focus
 * into the paste-a-QID input after dismissing itself, rather than guessing
 * at the picker's internal DOM structure.
 */
export interface WikidataGroundingPickerHandle {
  /** Moves focus into the paste-a-QID input; the field's current text is left untouched. */
  focusQidInput: () => void;
}

/**
 * Search → shortlist → select control for grounding an entity to a Wikidata
 * item.
 *
 * Exposes a `WikidataGroundingPickerHandle` via ref (currently just
 * `focusQidInput()`); the ref is entirely optional and unused callers are
 * unaffected.
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
export const WikidataGroundingPicker = forwardRef<
  WikidataGroundingPickerHandle,
  WikidataGroundingPickerProps
>(function WikidataGroundingPicker(
  {
    name,
    entityType,
    selectedCandidate,
    onSelectCandidate,
    disabled = false,
    heading = "Ground in Wikidata",
    optional = true,
    allowSkip = true,
    onPendingInvalidQidChange,
  },
  ref
) {
  const [groundingSkipped, setGroundingSkipped] = useState(false);
  const [qidInput, setQidInput] = useState("");
  const [qidResult, setQidResult] = useState<WikidataCandidateByQidData | null>(null);

  // Radio group `name` for candidate selection — unique per mounted instance.
  const wikidataGroupName = useId();
  const qidInputId = useId();
  const qidInputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(
    ref,
    () => ({
      focusQidInput: () => {
        qidInputRef.current?.focus();
      },
    }),
    []
  );

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
    setQidInput("");
    setQidResult(null);
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

  const extractedQid = extractQid(qidInput);
  const isQidValid = extractedQid !== null;
  const trimmedQidInput = qidInput.trim();
  const showQidHint = trimmedQidInput !== "" && !isQidValid && qidResult === null;
  // Reported to the caller regardless of `qidResult` (unlike the hint) — a
  // typed-but-invalid value is "pending" whether or not a stale resolve
  // message happens to also be showing.
  const pendingInvalidQid = trimmedQidInput !== "" && !isQidValid ? trimmedQidInput : "";

  // Lets the caller (e.g. CreateEntityModal) warn before submit that this
  // text was typed but never resolved to a valid QID.
  useEffect(() => {
    onPendingInvalidQidChange?.(pendingInvalidQid);
    // Intentionally depends on the derived value only, not on
    // `onPendingInvalidQidChange` (may not be stable across the caller's
    // renders), to avoid a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingInvalidQid]);

  const handleResolveQid = useCallback(async () => {
    if (extractedQid === null) return;
    try {
      const result = await wikidata.resolveByQid(extractedQid);
      if (result.candidate !== null) {
        onSelectCandidate(result.candidate);
        setQidResult(null);
        setQidInput("");
      } else {
        setQidResult(result);
      }
    } catch {
      setQidResult({ candidate: null, unavailable: true });
    }
    // `wikidata` is a new object every render; only its (stable) methods matter here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extractedQid, onSelectCandidate]);

  const handleQidKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void handleResolveQid();
      }
    },
    [handleResolveQid]
  );

  return (
    <div>
      <div className="mb-1.5">
        <span className="text-sm font-medium text-gray-700">
          {heading}{" "}
          {optional && (
            <span className="text-xs font-normal text-gray-400">
              — optional
            </span>
          )}
        </span>
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

          {!isNameSettling &&
            wikidata.candidates.length > 0 &&
            (wikidata.canShowMore || wikidata.isFetchingMore) && (
              <button
                type="button"
                onClick={() => wikidata.showMore()}
                disabled={disabled || wikidata.isFetchingMore}
                className="
                  flex items-center gap-2 text-xs text-indigo-600 hover:text-indigo-700
                  font-medium
                  disabled:opacity-50 disabled:cursor-not-allowed
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 rounded
                "
              >
                {wikidata.isFetchingMore && (
                  <span
                    className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"
                    aria-hidden="true"
                  />
                )}
                {wikidata.isFetchingMore ? "Loading more…" : "Show more"}
              </button>
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

          <div className="pt-1 border-t border-gray-100">
            <label
              htmlFor={qidInputId}
              className="block text-xs text-gray-500 mb-1"
            >
              Can&rsquo;t find it? Paste a Wikidata QID
            </label>
            <div className="flex items-center gap-2">
              <input
                ref={qidInputRef}
                id={qidInputId}
                type="text"
                value={qidInput}
                onChange={(event) => {
                  setQidInput(event.target.value);
                  setQidResult(null);
                }}
                onKeyDown={handleQidKeyDown}
                placeholder="Q42"
                disabled={disabled}
                className="
                  flex-1 min-w-0 px-2.5 py-1.5 text-sm
                  border border-gray-300 rounded-md
                  focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                  disabled:opacity-50 disabled:cursor-not-allowed
                "
              />
              <button
                type="button"
                onClick={() => void handleResolveQid()}
                disabled={disabled || !isQidValid || wikidata.isResolvingQid}
                className="
                  shrink-0 px-2.5 py-1.5 text-xs font-medium
                  text-indigo-600 border border-indigo-200 rounded-md
                  hover:bg-indigo-50
                  disabled:opacity-50 disabled:cursor-not-allowed
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
                "
              >
                {wikidata.isResolvingQid ? "Resolving…" : "Use this QID"}
              </button>
            </div>
            {showQidHint && (
              <p
                role="status"
                aria-live="polite"
                className="mt-1.5 text-xs text-amber-700"
              >
                Enter a Wikidata QID like Q42, or paste its wikidata.org link.
              </p>
            )}
            {qidResult !== null && (
              <p
                role="status"
                aria-live="polite"
                className="mt-1.5 text-xs text-amber-700"
              >
                {qidResult.unavailable ? (
                  <>
                    Couldn&rsquo;t reach Wikidata. You can still create this
                    entity without grounding.
                  </>
                ) : (
                  "No Wikidata item with that ID."
                )}
              </p>
            )}
          </div>
        </div>
      )}

      {groundingSkipped && (
        <p className="text-xs text-gray-400">
          Creating without Wikidata grounding.
        </p>
      )}
    </div>
  );
});

WikidataGroundingPicker.displayName = "WikidataGroundingPicker";

export default WikidataGroundingPicker;
