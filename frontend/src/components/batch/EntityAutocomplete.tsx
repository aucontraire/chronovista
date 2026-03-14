/**
 * EntityAutocomplete Component
 *
 * Implements:
 * - T023 [US5]: ARIA combobox for entity autocomplete (FR-010, FR-025)
 * - T024 [US5]: Selected entity pill/badge with dismiss button
 *
 * Features:
 * - ARIA combobox pattern: role="combobox", aria-expanded, aria-autocomplete="list",
 *   aria-controls, aria-activedescendant
 * - 300 ms debounce, minimum 2 chars before search fires (via useEntitySearch)
 * - "Searching..." loading indicator with aria-busy on the input
 * - "No entities found" empty state
 * - Keyboard navigation:
 *     ArrowDown → opens dropdown / moves to next option
 *     ArrowUp   → moves to previous option (wraps)
 *     Enter     → selects highlighted option
 *     Escape    → closes without selecting
 *     Tab       → closes without selecting (focus moves naturally)
 * - Each option: role="option", aria-selected when focused by keyboard
 * - Selected pill: role="status", dismiss button with accessible label
 *
 * API:
 *   GET /api/v1/entities?search={text}&search_aliases=true
 *                        &exclude_alias_types=asr_error&limit=10&status=active
 *
 * @see FR-010: Entity link in batch corrections
 * @see FR-025: Entity autocomplete
 */

import { useState, useRef, useEffect, useId } from "react";
import { useEntitySearch } from "../../hooks/useEntitySearch";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** Lightweight entity shape for the autocomplete selection state. */
export interface EntityOption {
  /** Named entity UUID (string). */
  id: string;
  /** Canonical display name. */
  name: string;
  /** Entity type label (person, organization, place, …). */
  type: string;
}

export interface EntityAutocompleteProps {
  /**
   * The replacement text value from the parent PatternInput field.
   * This is used as the search query — the autocomplete suggests entities
   * whose name matches what the user intends to replace the pattern with.
   */
  searchText: string;
  /** Called when an entity is selected (non-null) or cleared (null). */
  onEntitySelect: (entity: EntityOption | null) => void;
  /** Currently selected entity, or null when nothing is linked. */
  selectedEntity: EntityOption | null;
  /** When true, all interactive elements are disabled. */
  disabled?: boolean;
  /**
   * When true, the replacement text does not match the selected entity's
   * canonical name. Triggers an amber mismatch warning below the pill.
   */
  hasMismatch?: boolean;
}

// ---------------------------------------------------------------------------
// Entity type badge label map
// ---------------------------------------------------------------------------

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Person",
  organization: "Organization",
  place: "Place",
  event: "Event",
  work: "Work",
  technical_term: "Technical term",
};

function entityTypeLabel(type: string): string {
  return ENTITY_TYPE_LABELS[type] ?? type;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * EntityAutocomplete renders a combobox input (driven by the replacement text)
 * and, once an entity is selected, a dismissible pill below the dropdown.
 *
 * The component is intentionally stateless with respect to the selected entity
 * — that state lives in the parent (PatternInput or BatchCorrectionsPage).
 *
 * @example
 * ```tsx
 * const [selectedEntity, setSelectedEntity] = useState<EntityOption | null>(null);
 *
 * <EntityAutocomplete
 *   searchText={replacementValue}
 *   selectedEntity={selectedEntity}
 *   onEntitySelect={setSelectedEntity}
 * />
 * ```
 */
export function EntityAutocomplete({
  searchText,
  onEntitySelect,
  selectedEntity,
  disabled = false,
  hasMismatch = false,
}: EntityAutocompleteProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Unique IDs for ARIA relationships
  const inputId = useId();
  const listboxId = useId();
  const labelId = useId();
  const descriptionId = useId();

  const { entities, isLoading, isBelowMinChars } = useEntitySearch(searchText);

  // Reset highlighted index when the entity list changes
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [entities]);

  // Open the dropdown when search produces results, close when text is too short
  useEffect(() => {
    if (!isBelowMinChars && searchText.trim().length >= 2) {
      setIsOpen(true);
    } else {
      setIsOpen(false);
    }
  }, [searchText, isBelowMinChars]);

  // Close on click-outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (containerRef.current && !containerRef.current.contains(target)) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  const handleSelect = (entity: EntityOption) => {
    onEntitySelect(entity);
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  const handleDismiss = () => {
    onEntitySelect(null);
    // Return focus to the (read-only) input so keyboard users don't lose their place
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return;

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          setHighlightedIndex(0);
          break;
        }
        if (entities.length === 0) break;
        setHighlightedIndex((prev) =>
          prev < entities.length - 1 ? prev + 1 : 0
        );
        break;
      }

      case "ArrowUp": {
        e.preventDefault();
        if (!isOpen || entities.length === 0) break;
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : entities.length - 1
        );
        break;
      }

      case "Enter": {
        if (!isOpen) break;
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < entities.length) {
          const entity = entities[highlightedIndex];
          if (entity) {
            handleSelect({
              id: entity.entity_id,
              name: entity.canonical_name,
              type: entity.entity_type,
            });
          }
        }
        break;
      }

      case "Escape": {
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
      }

      case "Tab": {
        // Close without selecting; focus moves naturally to the next element
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
      }
    }
  };

  // aria-activedescendant value for keyboard navigation
  const activeDescendantId =
    highlightedIndex >= 0
      ? `${listboxId}-option-${highlightedIndex}`
      : undefined;

  const showDropdown = isOpen && !disabled;
  const showLoading = isLoading && searchText.trim().length >= 2;
  const showEmpty =
    showDropdown && !isLoading && entities.length === 0 && !isBelowMinChars;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-2">
      {/* Label */}
      <label
        id={labelId}
        htmlFor={inputId}
        className="block text-sm font-medium text-slate-700"
      >
        Link entity{" "}
        <span className="font-normal text-slate-400">
          — optional. Associates this correction with a named entity.
        </span>
      </label>

      {/* Combobox container */}
      <div ref={containerRef} className="relative">
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          role="combobox"
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          aria-expanded={showDropdown && entities.length > 0}
          aria-autocomplete="list"
          aria-controls={
            showDropdown && entities.length > 0 ? listboxId : undefined
          }
          aria-activedescendant={activeDescendantId}
          aria-busy={showLoading}
          value={searchText}
          // The input is read-only here — its value is driven by the
          // replacement text field in PatternInput (searchText prop).
          // We use readOnly + pointer-events-none so the user does not
          // directly type here; keyboard events still fire for navigation.
          readOnly
          disabled={disabled}
          placeholder={
            searchText.trim().length < 2
              ? "Enter at least 2 characters in the replacement field to search…"
              : showLoading
              ? "Searching…"
              : "Entity autocomplete — type in the replacement field above"
          }
          onKeyDown={handleKeyDown}
          className={[
            "w-full px-3 py-2 rounded-md border text-sm text-slate-900",
            "placeholder-slate-400",
            "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
            "transition-colors",
            disabled
              ? "bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed"
              : "bg-slate-50 border-slate-300 cursor-default",
          ].join(" ")}
        />

        {/* Inline spinner */}
        {showLoading && (
          <div
            className="absolute right-3 top-1/2 -translate-y-1/2"
            aria-hidden="true"
          >
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Suggestions listbox */}
        {showDropdown && entities.length > 0 && (
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            className="absolute z-50 left-0 right-0 top-full mt-1 max-h-60 overflow-auto bg-white border border-slate-300 rounded-lg shadow-lg"
          >
            {entities.map((entity, index) => {
              const isHighlighted = index === highlightedIndex;
              const optionId = `${listboxId}-option-${index}`;
              return (
                <li
                  key={entity.entity_id}
                  id={optionId}
                  role="option"
                  aria-selected={isHighlighted}
                  onClick={() =>
                    handleSelect({
                      id: entity.entity_id,
                      name: entity.canonical_name,
                      type: entity.entity_type,
                    })
                  }
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={[
                    "px-4 py-2.5 cursor-pointer select-none",
                    isHighlighted
                      ? "bg-blue-100 text-blue-900"
                      : "text-slate-900 hover:bg-slate-100",
                  ].join(" ")}
                >
                  {/* Line 1: canonical name */}
                  <div className="text-sm font-medium leading-tight">
                    {entity.canonical_name}
                  </div>
                  {/* Line 2: entity type */}
                  <div className="text-xs text-slate-500 leading-tight mt-0.5">
                    {entityTypeLabel(entity.entity_type)}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {/* Empty state */}
        {showEmpty && (
          <div
            role="status"
            className="absolute z-50 left-0 right-0 top-full mt-1 px-4 py-3 bg-white border border-slate-300 rounded-lg shadow-lg text-sm text-slate-500"
          >
            No entities found for &ldquo;{searchText}&rdquo;
          </div>
        )}
      </div>

      {/* Screen reader description */}
      <p id={descriptionId} className="sr-only">
        Entity autocomplete. The replacement text above is used as the search
        query. Use arrow keys to navigate suggestions, Enter to select, Escape
        to close.
      </p>

      {/* T024: Selected entity pill — shown below the dropdown */}
      {selectedEntity !== null && (
        <div className="space-y-2">
          <div
            role="status"
            className={[
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-50 text-sm",
              hasMismatch ? "border border-amber-300" : "border border-indigo-200",
            ].join(" ")}
          >
            {/* Amber mismatch dot */}
            {hasMismatch && (
              <span
                aria-hidden="true"
                className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0"
              />
            )}
            {/* Entity name */}
            <span className="font-medium text-indigo-800">
              {selectedEntity.name}
            </span>
            {/* Entity type badge */}
            <span className="text-xs text-indigo-500 font-normal">
              {entityTypeLabel(selectedEntity.type)}
            </span>
            {/* Link to entity detail page */}
            <a
              href={`/entities/${selectedEntity.id}`}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View entity details (opens in new tab)"
              className={[
                "inline-flex items-center justify-center",
                "min-w-[24px] min-h-[24px]",
                "rounded-full",
                "text-indigo-400 hover:text-indigo-700 hover:bg-indigo-100",
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1",
                "transition-colors",
              ].join(" ")}
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </a>
            {/* Dismiss button */}
            <button
              type="button"
              onClick={handleDismiss}
              disabled={disabled}
              aria-label="Remove entity link"
              className={[
                "inline-flex items-center justify-center",
                "min-w-[24px] min-h-[24px]",
                "-me-1",
                "rounded-full",
                "text-indigo-400 hover:text-indigo-700 hover:bg-indigo-100",
                "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1",
                "transition-colors",
                disabled ? "opacity-50 cursor-not-allowed" : "",
              ].join(" ")}
            >
              <svg
                className="w-3.5 h-3.5"
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

          {/* Mismatch warning note */}
          {hasMismatch && (
            <p
              role="note"
              aria-live="polite"
              className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2"
            >
              <span className="sr-only">Warning: </span>
              &#9888;{" "}
              <span className="font-mono bg-amber-100 px-1.5 py-0.5 rounded text-amber-800">
                &ldquo;{searchText.trim()}&rdquo;
              </span>{" "}
              is not the canonical name or a registered alias for this entity.
              The entity link will still be recorded, but future scans may not
              match this form. To add it as an alias, click the{" "}
              <svg
                className="inline w-3 h-3 text-amber-800"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>{" "}
              icon above to open the entity detail page. Or proceed as-is.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
