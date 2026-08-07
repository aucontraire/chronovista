/**
 * EntityTagSection — attach a canonical tag to an entity (Feature 064, US1/US2).
 *
 * An entity created before its tags acquired videos has no tag pointing at it,
 * so its video count omits every tag-associated video. The recovery a curator
 * reaches for — "this entity looks empty, attach its tag" — had no control to
 * click.
 *
 * The client never decides between linking and merging. It sends only the tag;
 * the server picks from the entity's state and reports which it chose. That is
 * what keeps "the entity's tag always wins" (FR-003) from being overridable
 * here, and it is why the request carries no `entity_type`.
 *
 * Search sets `exclude_linked`, so a tag representing another entity — or this
 * entity's own — is never offered (FR-007).
 *
 * Accessibility: a full ARIA combobox, matching `TagAutocomplete` rather than
 * the plainer `TagMergeSelector`. The two existing tag pickers disagree; this
 * follows the accessible one instead of adding a third variant (FR-023).
 */

import { useId, useRef, useState } from "react";

import { useCanonicalTags } from "../../hooks/useCanonicalTags";
import {
  useAddEntityTag,
  useEntityTags,
  useUnlinkEntityTag,
  useUnMergeEntityTag,
} from "../../hooks/useEntityTags";
import type { LinkedTagSummary } from "../../api/entityMentions";
import type { CanonicalTagListItem } from "../../types/canonical-tags";

/** Minimum characters before a contains-mode search runs. */
const MIN_QUERY_LENGTH = 2;

export interface EntityTagSectionProps {
  /** The entity being edited. */
  entityId: string;
  /** Display name, used in confirmations so they name the consequence. */
  entityName: string;
}

export function EntityTagSection({
  entityId,
  entityName,
}: EntityTagSectionProps) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<CanonicalTagListItem | null>(null);
  const [highlighted, setHighlighted] = useState(-1);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Off by default (FR-012): the group's history is corrective detail, not the
  // first thing a curator needs.
  const [showAbsorbed, setShowAbsorbed] = useState(false);
  // Set when the server refuses a multi-source reversal, so the confirmation
  // repeats the tags it named rather than a bare "are you sure?".
  const [pendingUnMerge, setPendingUnMerge] = useState<{
    normalizedForm: string;
    displayForm: string;
    detail: string;
  } | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const headingId = useId();
  const inputId = useId();
  const labelId = useId();
  const descriptionId = useId();
  const listboxId = useId();

  const addTag = useAddEntityTag(entityId);
  const { data: tagData, isLoading: isLoadingTags } = useEntityTags(entityId);
  const unMerge = useUnMergeEntityTag(entityId);
  const unlink = useUnlinkEntityTag(entityId);

  // Read the list defensively. This section sits inside a much larger page, and
  // a shape it did not expect must degrade to "show no tags" rather than throw
  // — a render error here would blank the entity page entirely, including the
  // aliases and videos that have nothing to do with tags.
  const linkedTags: LinkedTagSummary[] = Array.isArray(tagData?.linked_tags)
    ? tagData.linked_tags
    : [];
  const needsAttention = tagData?.needs_attention === true;
  const hasTagData = !isLoadingTags && Array.isArray(tagData?.linked_tags);

  // Contains mode finds a tag whose form differs from the entity's name by a
  // prefix, which prefix mode would miss.
  const { tags, isLoading, isRateLimited } = useCanonicalTags(query, {
    matchMode: "contains",
    limit: 20,
    excludeLinked: true,
  });

  const trimmed = query.trim();
  const showResults =
    trimmed.length >= MIN_QUERY_LENGTH && selected === null && tags.length > 0;
  const activeDescendantId =
    showResults && highlighted >= 0 ? `${listboxId}-opt-${highlighted}` : undefined;

  function choose(tag: CanonicalTagListItem) {
    setSelected(tag);
    setHighlighted(-1);
    setErrorMsg(null);
  }

  function reset() {
    setSelected(null);
    setQuery("");
    setHighlighted(-1);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      reset();
      return;
    }
    if (!showResults) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlighted((prev) => (prev + 1) % tags.length);
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlighted((prev) => (prev <= 0 ? tags.length - 1 : prev - 1));
        break;
      case "Enter": {
        e.preventDefault();
        const tag = tags[highlighted];
        if (tag) choose(tag);
        break;
      }
      default:
        break;
    }
  }

  /** Shared error wording: the server names the obstacle, we do not guess. */
  function describeFailure(err: unknown, fallback: string): string {
    const detail = (err as { detail?: string } | null)?.detail;
    return detail ?? fallback;
  }

  async function handleUnMerge(
    normalizedForm: string,
    confirmed = false,
    displayForm = normalizedForm
  ) {
    setSuccessMsg(null);
    setErrorMsg(null);
    try {
      await unMerge.mutateAsync({
        normalizedForm,
        confirmMultiSource: confirmed,
      });
      setPendingUnMerge(null);
      setSuccessMsg(`Un-merged "${displayForm}". It is searchable again.`);
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      const detail = describeFailure(err, "Could not un-merge that tag.");
      // A 409 naming other tags is a confirmation prompt, not a failure: the
      // operation folded several at once and the curator has now been told
      // which ones return.
      if (status === 409 && detail.includes("also restores")) {
        setPendingUnMerge({ normalizedForm, displayForm, detail });
      } else {
        setPendingUnMerge(null);
        setErrorMsg(detail);
      }
    }
  }

  async function handleUnlink(normalizedForm: string, displayForm = normalizedForm) {
    setSuccessMsg(null);
    setErrorMsg(null);
    try {
      await unlink.mutateAsync(normalizedForm);
      setSuccessMsg(
        `Unlinked "${displayForm}". It no longer represents ${entityName}.`
      );
    } catch (err: unknown) {
      setErrorMsg(describeFailure(err, "Could not unlink that tag."));
    }
  }

  async function handleAttach() {
    if (selected === null) return;
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      const result = await addTag.mutateAsync(selected.normalized_form);
      const n = result.entity_video_count;
      // The wording follows what the server actually did. A merge folds the
      // chosen tag into the entity's existing one, which is not what "linked"
      // would suggest.
      const verb =
        result.operation === "merge"
          ? `Merged "${selected.canonical_form}" into "${result.target_canonical_form}"`
          : `Linked "${selected.canonical_form}"`;
      setSuccessMsg(
        `${verb} — ${n} ${n === 1 ? "video" : "videos"} now count toward ${entityName}.`
      );
      reset();
      inputRef.current?.focus();
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      // Only the server knows which entity holds a tag, or how many linked tags
      // block the operation. A generic message would strand the curator.
      const detail = (err as { detail?: string } | null)?.detail;
      if (status === 409 || status === 422) {
        setErrorMsg(detail ?? "That tag cannot be attached to this entity.");
      } else if (status === 404) {
        setErrorMsg("That tag no longer exists. Search again.");
      } else {
        setErrorMsg("Could not attach the tag. Please try again.");
      }
    }
  }

  return (
    <section aria-labelledby={headingId} className="mb-6">
      <h2
        id={headingId}
        className="text-lg font-semibold text-gray-900 mb-3"
      >
        Tags
      </h2>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        {/*
          The current state comes first. Without it the section is write-only,
          and "does this entity already have a tag?" is the question that
          precedes every action below.
        */}
        {hasTagData && (
          <div className="mb-4">
            {needsAttention && (
              <p
                className="mb-3 px-3 py-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg"
                role="alert"
              >
                This entity has {linkedTags.length} tags representing
                it. Only one should. Attaching another is blocked until that is
                resolved, because there is no single tag to merge into.
              </p>
            )}

            {linkedTags.length === 0 ? (
              <p className="text-sm text-slate-500 italic">
                No tag is linked to this entity — videos tagged with its name are
                not counted toward it.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {linkedTags.map((linked: LinkedTagSummary) => (
                  <li key={linked.normalized_form} className="py-2 first:pt-0">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-sm font-medium text-slate-900">
                        {linked.canonical_form}
                      </span>
                      <span className="text-xs text-slate-500">
                        {linked.video_count} video
                        {linked.video_count === 1 ? "" : "s"} ·{" "}
                        {linked.alias_count} variation
                        {linked.alias_count === 1 ? "" : "s"}
                      </span>
                    </div>

                    <div className="mt-1 flex flex-wrap items-center gap-3">
                      {linked.merged_tags.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setShowAbsorbed((v) => !v)}
                          aria-expanded={showAbsorbed}
                          className="text-xs text-blue-700 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                        >
                          {showAbsorbed ? "Hide" : "Show"}{" "}
                          {linked.merged_tags.length} merged tag
                          {linked.merged_tags.length === 1 ? "" : "s"}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void handleUnlink(linked.normalized_form, linked.canonical_form)}
                        disabled={unlink.isPending}
                        className="text-xs text-slate-500 hover:text-red-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                      >
                        Unlink
                      </button>
                    </div>

                    {showAbsorbed && linked.merged_tags.length > 0 && (
                      <ul className="mt-2 ml-4 space-y-1">
                        {linked.merged_tags.map((m) => (
                          <li
                            key={m.normalized_form}
                            className="flex flex-wrap items-baseline gap-2 text-xs text-slate-500"
                          >
                            <span>
                              <span className="text-slate-400">↳</span>{" "}
                              {m.canonical_form}{" "}
                              {/*
                                "brought", not "has": a merged tag owns no
                                videos now, and this is what it contributed at
                                merge time. Saying "has" would read as a live
                                count and invite adding it to the parent's,
                                which double counts any overlap.
                              */}
                              <span className="text-slate-400">
                                (brought {m.contributed_video_count} video
                                {m.contributed_video_count === 1 ? "" : "s"})
                              </span>
                            </span>
                            {m.operation_id !== null && (
                              <button
                                type="button"
                                onClick={() =>
                                  void handleUnMerge(m.normalized_form, false, m.canonical_form)
                                }
                                disabled={unMerge.isPending}
                                className="text-blue-700 hover:text-blue-900 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                              >
                                Un-merge
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <p className="text-sm text-slate-600 mb-3">
          Attach a canonical tag so its videos count toward this entity. If a tag
          already represents it, the one you choose is merged into that tag.
        </p>

        <label
          id={labelId}
          htmlFor={inputId}
          className="block text-sm font-medium text-slate-900"
        >
          Search tags
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          // The component owns its listbox; the browser's form-history dropdown
          // must not stack on top of it (see TagAutocomplete).
          autoComplete="off"
          role="combobox"
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          aria-expanded={showResults}
          aria-autocomplete="list"
          aria-controls={showResults ? listboxId : undefined}
          aria-activedescendant={activeDescendantId}
          value={selected ? selected.canonical_form : query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(null);
            setHighlighted(-1);
            setErrorMsg(null);
          }}
          onKeyDown={handleKeyDown}
          disabled={addTag.isPending}
          placeholder="Type at least 2 characters..."
          className="w-full mt-1 px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-900 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100"
        />
        <p id={descriptionId} className="mt-1 text-xs text-slate-500">
          Matches the canonical form and its variations at any position. Tags
          already representing an entity are not listed.
        </p>

        {/*
          Mounted only while a search is active. An always-present live region
          is the usual advice, but this page carries several status regions and
          a permanently empty one makes `getByRole("status")` ambiguous for
          every other feature on it. Typing flips this true while the request is
          still in flight, so the region exists before the count arrives.
        */}
        {trimmed.length >= MIN_QUERY_LENGTH && selected === null && (
          <div role="status" aria-live="polite" className="sr-only">
            {isLoading
              ? ""
              : `${tags.length} tag${tags.length === 1 ? "" : "s"} found`}
          </div>
        )}

        {isRateLimited && (
          <p className="mt-2 text-sm text-amber-700">
            Too many searches. Pause a moment and try again.
          </p>
        )}

        {trimmed.length >= MIN_QUERY_LENGTH &&
          selected === null &&
          !isLoading &&
          tags.length === 0 && (
            <p className="mt-2 text-sm text-slate-500">
              No unattached tags found matching &ldquo;{trimmed}&rdquo;.
            </p>
          )}

        {showResults && (
          <ul
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            className="mt-2 max-h-56 overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-lg"
          >
            {tags.map((tag, i) => (
              <li
                key={tag.normalized_form}
                id={`${listboxId}-opt-${i}`}
                role="option"
                aria-selected={i === highlighted}
                onMouseDown={(e) => {
                  // mousedown, not click: blurring the input first would close
                  // the listbox before the selection registered.
                  e.preventDefault();
                  choose(tag);
                }}
                className={`px-3 py-2 cursor-pointer ${
                  i === highlighted ? "bg-blue-50" : "hover:bg-slate-50"
                }`}
              >
                <span className="block text-sm text-slate-900">
                  {tag.canonical_form}
                </span>
                <span className="block text-xs text-slate-500">
                  {tag.video_count} video{tag.video_count === 1 ? "" : "s"} ·{" "}
                  {tag.alias_count} variation
                  {tag.alias_count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleAttach()}
              disabled={addTag.isPending}
              className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {addTag.isPending
                ? "Attaching..."
                : `Attach "${selected.canonical_form}"`}
            </button>
            <button
              type="button"
              onClick={reset}
              disabled={addTag.isPending}
              className="text-sm text-slate-600 hover:text-slate-900 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        )}

        {pendingUnMerge && (
          <div
            className="mt-3 px-3 py-2 text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg"
            role="alert"
          >
            <p>{pendingUnMerge.detail}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() =>
                  void handleUnMerge(
                    pendingUnMerge.normalizedForm,
                    true,
                    pendingUnMerge.displayForm
                  )
                }
                disabled={unMerge.isPending}
                className="px-3 py-1 text-sm font-medium text-white bg-amber-700 rounded-lg hover:bg-amber-800 disabled:opacity-50"
              >
                Un-merge all of them
              </button>
              <button
                type="button"
                onClick={() => setPendingUnMerge(null)}
                className="text-sm text-slate-600 hover:text-slate-900"
              >
                Cancel
              </button>
            </div>
          </div>
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
