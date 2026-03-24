/**
 * CreateEntityModal — modal for creating a new named entity.
 *
 * Implements:
 * - T015 [US1]: Modal shell (FR-017, FR-018, FR-019)
 * - T016 [US1]: Tag autocomplete + entity-type selector (FR-004, FR-005, FR-011, FR-018, FR-020)
 * - T017 [US1]: Submit handler wired to useClassifyTag mutation (FR-016)
 *
 * Features:
 * - ARIA dialog: role="dialog", aria-modal="true", aria-labelledby
 * - Semi-transparent backdrop that closes on click
 * - X button in top-right corner
 * - Escape key listener closes modal
 * - Focus trap: Tab cycles within modal; Shift+Tab wraps in reverse
 * - Focus auto-moves to name field on open
 * - Focus returns to trigger element on close (via onClose callback)
 * - Conditional rendering: returns null when isOpen is false
 * - Portal: rendered via createPortal to document.body
 * - Form state reset on close
 *
 * Tag autocomplete (T016):
 * - ARIA combobox on the name input (role="combobox", aria-expanded,
 *   aria-autocomplete="list", aria-controls, aria-activedescendant)
 * - Triggers after 2+ characters with 300 ms debounce via useCanonicalTags
 * - ArrowUp/Down/Enter keyboard navigation
 * - On selection: populates name, shows "Creating from tag" chip (FR-004)
 * - Editing name after selection clears selectedTag (FR-004 mode transition)
 * - When no selectedTag and name non-empty: "Creating standalone entity" label (FR-011)
 *
 * Entity type selector (T016):
 * - <select> covering all 8 ENTITY_PRODUCING_TYPES
 * - Tooltip info icon per option using ENTITY_TYPE_TOOLTIPS (FR-005.1)
 * - "Other" hint text (FR-005.2)
 *
 *
 * @module components/entity/CreateEntityModal
 */

import { useState, useEffect, useRef, useCallback, useId } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useCanonicalTags } from "../../hooks/useCanonicalTags";
import { useClassifyTag, useCheckDuplicate, useCreateEntity } from "../../hooks/useEntityMentions";
import {
  ENTITY_PRODUCING_TYPES,
  ENTITY_TYPE_LABELS,
  ENTITY_TYPE_TOOLTIPS,
} from "../../constants/entityTypes";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * A canonical tag returned from the tag-resolution autocomplete.
 * Populated by T016 when the user selects a tag to link this entity to.
 */
export interface SelectedTag {
  canonical_form: string;
  normalized_form: string;
  alias_count: number;
  video_count: number;
}

export interface CreateEntityModalProps {
  /** Whether the modal is open. When false the component returns null. */
  isOpen: boolean;
  /** Called when the modal should close (X button, backdrop click, Escape key, or Cancel). */
  onClose: () => void;
  /**
   * Called after a successful entity creation so the parent can refresh its
   * entity list (e.g. invalidate TanStack Query cache).
   */
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns all keyboard-focusable elements inside a container element.
 * Used by the focus-trap logic.
 */
function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      [
        "a[href]",
        "button:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        '[tabindex]:not([tabindex="-1"])',
      ].join(", ")
    )
  ).filter((el) => !el.hidden);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * CreateEntityModal renders a centred dialog for creating a new named entity.
 *
 * The modal shell manages ARIA semantics, backdrop, Escape handling, focus
 * trap, and form-state lifecycle. T016 adds entity type selector and tag
 * autocomplete. T017 wires the submit handler to the useClassifyTag mutation.
 *
 * @example
 * ```tsx
 * const triggerRef = useRef<HTMLButtonElement>(null);
 * const [isOpen, setIsOpen] = useState(false);
 *
 * <button ref={triggerRef} onClick={() => setIsOpen(true)}>
 *   Create Entity
 * </button>
 * <CreateEntityModal
 *   isOpen={isOpen}
 *   onClose={() => { setIsOpen(false); triggerRef.current?.focus(); }}
 *   onSuccess={() => void queryClient.invalidateQueries({ queryKey: ["entities"] })}
 * />
 * ```
 */
export default function CreateEntityModal({
  isOpen,
  onClose,
  onSuccess,
}: CreateEntityModalProps) {
  // ---------------------------------------------------------------------------
  // Form state
  // ---------------------------------------------------------------------------

  const [name, setName] = useState("");
  const [entityType, setEntityType] = useState("");
  const [description, setDescription] = useState("");
  const [aliases, setAliases] = useState<string[]>([]);
  const [selectedTag, setSelectedTag] = useState<SelectedTag | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Mutation
  // ---------------------------------------------------------------------------

  const classifyTagMutation = useClassifyTag();
  const createEntityMutation = useCreateEntity();

  // ---------------------------------------------------------------------------
  // Duplicate detection (T024 [US3])
  // ---------------------------------------------------------------------------

  const duplicateCheck = useCheckDuplicate(name, entityType);

  // ---------------------------------------------------------------------------
  // Tag autocomplete state
  // ---------------------------------------------------------------------------

  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  // Refs for focus management
  const dialogRef = useRef<HTMLDivElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);

  // Stable IDs for ARIA relationships
  const listboxId = useId();

  // ---------------------------------------------------------------------------
  // Tag search via useCanonicalTags (300 ms debounce built into hook)
  // ---------------------------------------------------------------------------

  const { tags: tagResults, isLoading: isSearching } = useCanonicalTags(
    // Only feed the hook when we have 2+ chars and no tag is selected.
    // When a tag is already selected we don't want to re-query.
    name.length >= 2 && selectedTag === null ? name : ""
  );

  // Open the dropdown whenever results arrive for a qualifying query.
  useEffect(() => {
    if (name.length >= 2 && selectedTag === null && tagResults.length > 0) {
      setShowDropdown(true);
    } else if (name.length < 2 || selectedTag !== null) {
      setShowDropdown(false);
      setHighlightedIndex(-1);
    }
  }, [tagResults, name, selectedTag]);

  // Reset highlighted index whenever the result list changes.
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [tagResults]);

  // ---------------------------------------------------------------------------
  // Close dropdown on outside click
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!showDropdown) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        nameInputRef.current &&
        !nameInputRef.current.contains(target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(target)
      ) {
        setShowDropdown(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showDropdown]);

  // ---------------------------------------------------------------------------
  // Reset form when modal closes
  // ---------------------------------------------------------------------------

  const resetForm = useCallback(() => {
    setName("");
    setEntityType("");
    setDescription("");
    setAliases([]);
    setSelectedTag(null);
    setIsSubmitting(false);
    setError(null);
    setShowDropdown(false);
    setHighlightedIndex(-1);
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen, resetForm]);

  // ---------------------------------------------------------------------------
  // Clear error on form modification (FR-016: error persists until retry/edit)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (error !== null) {
      setError(null);
    }
    // Intentionally depends on the form values only — not `error` itself,
    // so we don't create a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, entityType, description]);

  // ---------------------------------------------------------------------------
  // Auto-focus name field on open
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (isOpen) {
      const id = requestAnimationFrame(() => {
        nameInputRef.current?.focus();
      });
      return () => cancelAnimationFrame(id);
    }
  }, [isOpen]);

  // ---------------------------------------------------------------------------
  // Escape to close (also closes dropdown first if open)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showDropdown) {
          // First Escape press closes the dropdown only.
          e.stopPropagation();
          setShowDropdown(false);
          setHighlightedIndex(-1);
        } else {
          e.stopPropagation();
          onClose();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, showDropdown]);

  // ---------------------------------------------------------------------------
  // Focus trap
  // ---------------------------------------------------------------------------

  const handleDialogKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key !== "Tab") return;

      const dialog = dialogRef.current;
      if (!dialog) return;

      const focusable = getFocusableElements(dialog);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Backdrop click
  // ---------------------------------------------------------------------------

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  // ---------------------------------------------------------------------------
  // Tag selection handler
  // ---------------------------------------------------------------------------

  const handleTagSelect = useCallback(
    (tag: SelectedTag) => {
      setName(tag.canonical_form);
      setSelectedTag(tag);
      setAliases([]);
      setShowDropdown(false);
      setHighlightedIndex(-1);
      // Return focus to name input after selection so keyboard users can continue.
      nameInputRef.current?.focus();
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Name input change — clears selectedTag if user edits after selection
  // ---------------------------------------------------------------------------

  const handleNameChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setName(value);
      // FR-004 mode transition: any manual edit clears the selected tag.
      if (selectedTag !== null) {
        setSelectedTag(null);
      }
    },
    [selectedTag]
  );

  // ---------------------------------------------------------------------------
  // Keyboard navigation in tag dropdown
  // ---------------------------------------------------------------------------

  const handleNameKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!showDropdown || tagResults.length === 0) {
        // Allow Escape to be handled by the document listener above.
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setHighlightedIndex((prev) =>
            prev < tagResults.length - 1 ? prev + 1 : 0
          );
          break;

        case "ArrowUp":
          e.preventDefault();
          setHighlightedIndex((prev) =>
            prev > 0 ? prev - 1 : tagResults.length - 1
          );
          break;

        case "Enter":
          e.preventDefault();
          if (highlightedIndex >= 0 && highlightedIndex < tagResults.length) {
            const tag = tagResults[highlightedIndex];
            if (tag) {
              handleTagSelect({
                canonical_form: tag.canonical_form,
                normalized_form: tag.normalized_form,
                alias_count: tag.alias_count,
                video_count: tag.video_count,
              });
            }
          }
          break;

        case "Escape":
          e.preventDefault();
          setShowDropdown(false);
          setHighlightedIndex(-1);
          break;

        case "Tab":
          // Close dropdown; focus moves naturally to next element.
          setShowDropdown(false);
          setHighlightedIndex(-1);
          break;
      }
    },
    [showDropdown, tagResults, highlightedIndex, handleTagSelect]
  );

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  // FR-012: Only block submit on confirmed duplicate — endpoint failure
  // falls through as false so submission is still allowed as fallback.
  const isDuplicate = duplicateCheck.data?.is_duplicate === true;

  // Disable submit while the check is in-flight to prevent a race condition
  // where the user submits before the duplicate warning appears.
  const isDuplicateCheckPending =
    duplicateCheck.isLoading && name.trim().length >= 2 && entityType !== "";

  const isSubmitDisabled =
    isSubmitting ||
    name.trim() === "" ||
    entityType === "" ||
    isDuplicate ||
    isDuplicateCheckPending;

  // aria-activedescendant value for keyboard navigation
  const activeDescendantId =
    highlightedIndex >= 0
      ? `${listboxId}-option-${highlightedIndex}`
      : undefined;

  // Show "Creating standalone entity" label only when name has text and no tag
  // is selected (FR-011).
  const showStandaloneLabel = name.trim().length > 0 && selectedTag === null;

  // ---------------------------------------------------------------------------
  // Conditional render
  // ---------------------------------------------------------------------------

  if (!isOpen) return null;

  // ---------------------------------------------------------------------------
  // Portal render
  // ---------------------------------------------------------------------------

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={handleBackdropClick}
      style={{ backgroundColor: "rgba(0, 0, 0, 0.45)" }}
      aria-hidden="false"
    >
      {/* Dialog panel */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-entity-title"
        onKeyDown={handleDialogKeyDown}
        className="
          relative
          w-full max-w-lg
          bg-white
          rounded-xl
          shadow-2xl
          flex flex-col
          max-h-[90vh]
          overflow-hidden
        "
      >
        {/* ------------------------------------------------------------------ */}
        {/* Header                                                              */}
        {/* ------------------------------------------------------------------ */}
        <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-gray-100 flex-shrink-0">
          <h2
            id="create-entity-title"
            className="text-lg font-semibold text-gray-900"
          >
            Create Entity
          </h2>

          {/* Close (X) button */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="
              inline-flex items-center justify-center
              w-8 h-8
              rounded-full
              text-gray-400 hover:text-gray-600 hover:bg-gray-100
              focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
              transition-colors
            "
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* ------------------------------------------------------------------ */}
        {/* Scrollable form body                                                */}
        {/* ------------------------------------------------------------------ */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Inline error banner */}
          {error !== null && (
            <div
              role="alert"
              aria-live="polite"
              className="flex items-start gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800"
            >
              <svg
                className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* ---------------------------------------------------------------- */}
          {/* Name field with tag autocomplete combobox (T016)                 */}
          {/* ---------------------------------------------------------------- */}
          <div>
            <label
              htmlFor="create-entity-name"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Name <span className="text-red-500" aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>

            {/* Combobox wrapper — position: relative for dropdown positioning */}
            <div className="relative">
              <input
                ref={nameInputRef}
                id="create-entity-name"
                type="text"
                role="combobox"
                aria-expanded={showDropdown && tagResults.length > 0}
                aria-autocomplete="list"
                aria-controls={
                  showDropdown && tagResults.length > 0
                    ? listboxId
                    : undefined
                }
                aria-activedescendant={activeDescendantId}
                aria-busy={isSearching}
                value={name}
                onChange={handleNameChange}
                onKeyDown={handleNameKeyDown}
                onFocus={() => {
                  // Re-open dropdown on focus if there are already results.
                  if (
                    name.length >= 2 &&
                    selectedTag === null &&
                    tagResults.length > 0
                  ) {
                    setShowDropdown(true);
                  }
                }}
                disabled={isSubmitting}
                placeholder="e.g. Alexandria Ocasio-Cortez"
                autoComplete="off"
                className="
                  w-full
                  px-3 py-2.5
                  text-sm text-gray-900 placeholder-gray-400
                  border border-gray-300 rounded-lg
                  bg-white
                  focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                  disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
                  transition-colors
                "
              />

              {/* Inline spinner while searching */}
              {isSearching && name.length >= 2 && selectedTag === null && (
                <div
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  aria-hidden="true"
                >
                  <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                </div>
              )}

              {/* Tag suggestions listbox */}
              {showDropdown && tagResults.length > 0 && (
                <ul
                  ref={dropdownRef}
                  id={listboxId}
                  role="listbox"
                  aria-label="Matching canonical tags"
                  className="
                    absolute z-50 left-0 right-0 top-full mt-1
                    max-h-60 overflow-auto
                    bg-white border border-gray-200 rounded-lg shadow-lg
                  "
                >
                  {tagResults.map((tag, index) => {
                    const isHighlighted = index === highlightedIndex;
                    const optionId = `${listboxId}-option-${index}`;
                    const aliasLabel =
                      tag.alias_count > 1
                        ? `${tag.alias_count - 1} ${tag.alias_count - 1 === 1 ? "alias" : "aliases"}`
                        : null;

                    return (
                      <li
                        key={tag.normalized_form}
                        id={optionId}
                        role="option"
                        aria-selected={isHighlighted}
                        aria-label={`${tag.canonical_form}, ${tag.video_count} videos${aliasLabel ? `, ${aliasLabel}` : ""}`}
                        onClick={() =>
                          handleTagSelect({
                            canonical_form: tag.canonical_form,
                            normalized_form: tag.normalized_form,
                            alias_count: tag.alias_count,
                            video_count: tag.video_count,
                          })
                        }
                        onMouseEnter={() => setHighlightedIndex(index)}
                        className={`
                          px-4 py-2.5 cursor-pointer select-none
                          ${
                            isHighlighted
                              ? "bg-indigo-50 text-indigo-900"
                              : "text-gray-900 hover:bg-gray-50"
                          }
                        `}
                      >
                        {/* Line 1: canonical form (bold) + video count */}
                        <div className="flex items-baseline gap-2">
                          <span className="text-sm font-semibold leading-tight">
                            {tag.canonical_form}
                          </span>
                          <span className="text-xs text-gray-500 leading-tight">
                            {tag.video_count} {tag.video_count === 1 ? "video" : "videos"}
                          </span>
                          {aliasLabel && (
                            <span className="text-xs text-gray-400 leading-tight">
                              {aliasLabel}
                            </span>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}

              {/* No results state — shown when search returned empty */}
              {showDropdown &&
                tagResults.length === 0 &&
                !isSearching &&
                name.length >= 2 &&
                selectedTag === null && (
                  <div
                    role="status"
                    aria-live="polite"
                    className="
                      absolute z-50 left-0 right-0 top-full mt-1
                      px-4 py-3
                      bg-white border border-gray-200 rounded-lg shadow-lg
                      text-sm text-gray-500
                    "
                  >
                    No matching tags — entity will be created standalone.
                  </div>
                )}
            </div>

            {/* ---- Tag chip or standalone label (FR-004 / FR-011) ---- */}
            {selectedTag !== null ? (
              /* FR-004: "Creating from tag" chip when a tag is selected */
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-gray-500">Creating from tag</span>
                <span className="
                  inline-flex items-center gap-1.5
                  px-2.5 py-0.5
                  text-xs font-medium
                  bg-indigo-50 text-indigo-700 border border-indigo-200
                  rounded-full
                ">
                  {selectedTag.canonical_form}
                  {/* X to clear the tag selection */}
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedTag(null);
                      nameInputRef.current?.focus();
                    }}
                    disabled={isSubmitting}
                    aria-label={`Remove tag link to ${selectedTag.canonical_form}`}
                    className="
                      inline-flex items-center justify-center
                      w-3.5 h-3.5 -mr-0.5
                      rounded-full
                      text-indigo-400 hover:text-indigo-700 hover:bg-indigo-100
                      focus:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500
                      disabled:opacity-50 disabled:cursor-not-allowed
                      transition-colors
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
            ) : showStandaloneLabel ? (
              /* FR-011: "Creating standalone entity" when name has text but no tag */
              <p className="mt-1.5 text-xs text-gray-400">
                Creating standalone entity
              </p>
            ) : null}

            {/* Screen reader description for the combobox */}
            <p className="sr-only" id="create-entity-name-desc">
              Type to search canonical tags. Use arrow keys to navigate results,
              Enter to select, Escape to close the suggestions.
            </p>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Entity type selector (T016)                                      */}
          {/* ---------------------------------------------------------------- */}
          <div>
            <label
              htmlFor="create-entity-type"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Entity type{" "}
              <span className="text-red-500" aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>

            <select
              id="create-entity-type"
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              disabled={isSubmitting}
              aria-required="true"
              className="
                w-full
                px-3 py-2.5
                text-sm text-gray-900
                border border-gray-300 rounded-lg
                bg-white
                focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
                transition-colors
                appearance-none
              "
            >
              <option value="" disabled>
                Select a type…
              </option>
              {ENTITY_PRODUCING_TYPES.map((type) => (
                <option key={type} value={type}>
                  {ENTITY_TYPE_LABELS[type] ?? type}
                </option>
              ))}
            </select>

            {/* Per-type tooltip info icons (FR-005.1) */}
            {entityType !== "" && (
              <div className="mt-2 flex items-start gap-1.5">
                {/* Info icon */}
                <svg
                  className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-xs text-gray-500 leading-relaxed">
                  {ENTITY_TYPE_TOOLTIPS[entityType]}
                </p>
              </div>
            )}

            {/* FR-005.2: Non-blocking "Other" hint */}
            {entityType === "other" && (
              <p
                role="note"
                className="
                  mt-2 px-3 py-2
                  text-xs text-amber-700
                  bg-amber-50 border border-amber-200
                  rounded-md
                "
              >
                Consider whether this entity fits one of the specific types
                above.
              </p>
            )}
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Duplicate warning (T024 [US3])                                   */}
          {/* ---------------------------------------------------------------- */}
          {isDuplicate && duplicateCheck.data?.existing_entity !== null && duplicateCheck.data?.existing_entity !== undefined && (
            <div
              role="alert"
              aria-live="assertive"
              className="bg-amber-50 border border-amber-300 rounded-lg px-4 py-3 text-amber-800 text-sm space-y-1"
            >
              <p className="font-medium">
                An entity with this name and type already exists:
              </p>
              <p>
                <strong>{duplicateCheck.data.existing_entity.canonical_name}</strong>{" "}
                ({ENTITY_TYPE_LABELS[duplicateCheck.data.existing_entity.entity_type] ?? duplicateCheck.data.existing_entity.entity_type})
              </p>
              {duplicateCheck.data.existing_entity.description !== null && (
                <p className="text-sm text-amber-700">
                  {duplicateCheck.data.existing_entity.description}
                </p>
              )}
              <Link
                to={`/entities/${duplicateCheck.data.existing_entity.entity_id}`}
                className="
                  inline-block mt-1
                  text-sm font-medium text-amber-900 underline underline-offset-2
                  hover:text-amber-700
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1 rounded
                "
              >
                View existing entity
              </Link>
            </div>
          )}

          {/* ---- Description field (optional) ---- */}
          <div>
            <label
              htmlFor="create-entity-description"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Description{" "}
              <span className="text-xs font-normal text-gray-400">
                — optional
              </span>
            </label>
            <textarea
              id="create-entity-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              placeholder="Short description of this entity…"
              rows={3}
              className="
                w-full
                px-3 py-2.5
                text-sm text-gray-900 placeholder-gray-400
                border border-gray-300 rounded-lg
                bg-white
                resize-none
                focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
                transition-colors
              "
            />
          </div>

          {/* ---- Alias fields — standalone mode only (FR-004 / FR-011) ---- */}
          {selectedTag === null && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-gray-700">
                  Aliases{" "}
                  <span className="text-xs font-normal text-gray-400">
                    — optional
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => setAliases([...aliases, ""])}
                  disabled={isSubmitting || aliases.length >= 20}
                  className="
                    text-xs text-indigo-600 hover:text-indigo-700
                    font-medium
                    disabled:opacity-50 disabled:cursor-not-allowed
                    focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 rounded
                  "
                >
                  + Add Alias
                </button>
              </div>

              {aliases.map((alias, index) => (
                <div key={index} className="flex items-center gap-2 mb-2">
                  <input
                    type="text"
                    value={alias}
                    onChange={(e) => {
                      const updated = [...aliases];
                      updated[index] = e.target.value;
                      setAliases(updated);
                    }}
                    placeholder={`Alias ${index + 1}`}
                    disabled={isSubmitting}
                    aria-label={`Alias ${index + 1}`}
                    className="
                      flex-1
                      px-3 py-2
                      text-sm text-gray-900 placeholder-gray-400
                      border border-gray-300 rounded-lg
                      bg-white
                      focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
                      disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
                      transition-colors
                    "
                  />
                  <button
                    type="button"
                    onClick={() => setAliases(aliases.filter((_, i) => i !== index))}
                    disabled={isSubmitting}
                    aria-label={`Remove alias ${index + 1}`}
                    className="
                      inline-flex items-center justify-center
                      w-8 h-8
                      rounded-full
                      text-gray-400 hover:text-red-500 hover:bg-red-50
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 focus-visible:ring-offset-1
                      disabled:opacity-50 disabled:cursor-not-allowed
                      transition-colors flex-shrink-0
                    "
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* aria-live region for mode-transition announcements (FR-004 / FR-011) */}
          <div
            aria-live="polite"
            aria-atomic="true"
            className="sr-only"
          >
            {selectedTag !== null
              ? `Creating from tag: ${selectedTag.canonical_form}`
              : showStandaloneLabel
              ? "Creating standalone entity"
              : ""}
          </div>

        </div>

        {/* ------------------------------------------------------------------ */}
        {/* Footer                                                              */}
        {/* ------------------------------------------------------------------ */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50 flex-shrink-0">
          {/* Cancel button */}
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="
              min-h-[44px]
              px-4 py-2
              text-sm font-medium text-gray-700
              bg-white border border-gray-300 rounded-lg
              hover:bg-gray-50 hover:text-gray-900
              focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            Cancel
          </button>

          {/* Submit button */}
          <button
            type="button"
            disabled={isSubmitDisabled}
            aria-busy={isSubmitting}
            aria-disabled={isSubmitDisabled}
            onClick={() => {
              if (selectedTag === null) {
                // Standalone creation path.
                setIsSubmitting(true);
                const trimmedDesc = description.trim();
                const trimmedAliases = aliases
                  .map((a) => a.trim())
                  .filter((a) => a.length > 0);
                createEntityMutation.mutate(
                  {
                    name: name.trim(),
                    entity_type: entityType,
                    ...(trimmedDesc ? { description: trimmedDesc } : {}),
                    ...(trimmedAliases.length > 0
                      ? { aliases: trimmedAliases }
                      : {}),
                  },
                  {
                    onSuccess: () => {
                      onSuccess?.();
                      onClose();
                    },
                    onError: (err) => {
                      setError(
                        err.message || "Failed to create entity. Please try again."
                      );
                    },
                    onSettled: () => {
                      setIsSubmitting(false);
                    },
                  }
                );
                return;
              }

              setIsSubmitting(true);
              const trimmedDesc = description.trim();
              classifyTagMutation.mutate(
                {
                  normalized_form: selectedTag.normalized_form,
                  entity_type: entityType,
                  ...(trimmedDesc ? { description: trimmedDesc } : {}),
                },
                {
                  onSuccess: () => {
                    onSuccess?.();
                    onClose();
                  },
                  onError: (err) => {
                    setError(
                      err.message.length > 0
                        ? err.message
                        : "Failed to create entity. Please try again."
                    );
                  },
                  onSettled: () => {
                    setIsSubmitting(false);
                  },
                }
              );
            }}
            className="
              min-h-[44px]
              px-5 py-2
              text-sm font-medium text-white
              bg-indigo-600 rounded-lg
              hover:bg-indigo-700
              focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            {isSubmitting ? (
              <span className="inline-flex items-center gap-2">
                <svg
                  className="w-4 h-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Creating…
              </span>
            ) : (
              "Create Entity"
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Named re-export for consumers that prefer named imports
// ---------------------------------------------------------------------------
export { CreateEntityModal };
