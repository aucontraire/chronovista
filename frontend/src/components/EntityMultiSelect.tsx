/**
 * EntityMultiSelect — multi-select entity picker for the videos list filter panel.
 *
 * Feature 062. Models itself on `TagAutocomplete` rather than on
 * `batch/EntityAutocomplete`, deliberately:
 *
 * `EntityAutocomplete` is driven by a `searchText` prop supplied by the parent
 * correction field — it does not own its query — and it links exactly one
 * entity. A filter picker owns its input and holds a set. Bending one component
 * to serve both would thread a mode flag through every branch and create the
 * second code path that later diverges. Leaving it untouched is also the
 * strongest possible form of "do not regress the batch surface" (FR-039).
 *
 * What IS shared is the data layer: `useEntitySearch` (300 ms debounce,
 * 2-character minimum) backs both.
 *
 * Accessibility follows the ARIA combobox pattern already used by
 * `TagAutocomplete`: role="combobox" with aria-expanded and
 * aria-autocomplete="list", a role="listbox" of role="option" items, and
 * aria-activedescendant for keyboard navigation.
 */

import { useEffect, useId, useRef, useState } from "react";

import { EntityName } from "./EntityName";
import { useEntitySearch } from "../hooks/useEntitySearch";

export interface SelectedEntity {
  /** Named entity UUID. */
  entity_id: string;
  /** Canonical display name. */
  canonical_name: string;
  /** Entity type, for the badge. */
  entity_type: string;
}

interface EntityMultiSelectProps {
  /** Currently selected entities. */
  selected: SelectedEntity[];
  /** Called when an entity is added. */
  onSelect: (entity: SelectedEntity) => void;
  /** Called when an entity is removed, by entity_id. */
  onRemove: (entityId: string) => void;
  /** Maximum selectable; the input disables at the ceiling. */
  max: number;
  /** Visible label for the input. */
  label: string;
  /** Placeholder text. */
  placeholder?: string;
  /** Ids already chosen in the sibling set, which cannot be chosen here. */
  unavailableIds?: string[];
  /** Optional container className. */
  className?: string;
}

export function EntityMultiSelect({
  selected,
  onSelect,
  onRemove,
  max,
  label,
  placeholder = "Search entities…",
  unavailableIds = [],
  className = "",
}: EntityMultiSelectProps) {
  const [inputValue, setInputValue] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputId = useId();
  const listboxId = useId();
  const descriptionId = useId();

  const { entities, isLoading, isBelowMinChars } = useEntitySearch(inputValue);

  const atCeiling = selected.length >= max;
  const selectedIds = new Set(selected.map((e) => e.entity_id));
  const blockedIds = new Set([...selectedIds, ...unavailableIds]);
  const options = entities.filter((e) => !blockedIds.has(e.entity_id));

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function commit(index: number) {
    const option = options[index];
    if (!option || atCeiling) return;
    onSelect({
      entity_id: option.entity_id,
      canonical_name: option.canonical_name,
      entity_type: option.entity_type,
    });
    setInputValue("");
    setIsOpen(false);
    setHighlightedIndex(-1);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || options.length === 0) {
      if (event.key === "Escape") setIsOpen(false);
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setHighlightedIndex((i) => (i + 1) % options.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setHighlightedIndex((i) => (i <= 0 ? options.length - 1 : i - 1));
        break;
      case "Enter":
        event.preventDefault();
        if (highlightedIndex >= 0) commit(highlightedIndex);
        break;
      case "Escape":
        event.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
      default:
        break;
    }
  }

  const showSuggestions = isOpen && !isBelowMinChars && !atCeiling;

  return (
    <div ref={containerRef} className={`relative ${className}`.trim()}>
      <label
        htmlFor={inputId}
        className="block text-sm font-medium text-slate-700 mb-1"
      >
        {label}
      </label>

      {selected.length > 0 && (
        <ul
          role="list"
          aria-label={`Selected: ${label}`}
          className="flex flex-wrap gap-1.5 mb-2"
        >
          {selected.map((entity) => (
            <li key={entity.entity_id} role="listitem">
              <EntityName
                name={entity.canonical_name}
                entityType={entity.entity_type}
                onRemove={() => onRemove(entity.entity_id)}
              />
            </li>
          ))}
        </ul>
      )}

      <input
        id={inputId}
        type="text"
        // The component owns its suggestion listbox. Without this the browser
        // stacks its own form-history dropdown on top of it — two competing
        // lists, and the native one leaks whatever was typed here before.
        autoComplete="off"
        role="combobox"
        aria-expanded={showSuggestions && options.length > 0}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-describedby={descriptionId}
        {...(highlightedIndex >= 0 && options[highlightedIndex]
          ? {
              "aria-activedescendant": `${listboxId}-${options[highlightedIndex].entity_id}`,
            }
          : {})}
        value={inputValue}
        disabled={atCeiling}
        placeholder={atCeiling ? `Maximum ${max} reached` : placeholder}
        onChange={(e) => {
          setInputValue(e.target.value);
          setIsOpen(true);
          setHighlightedIndex(-1);
        }}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
        className={`w-full rounded-lg border px-4 py-2.5 text-base text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
          atCeiling
            ? 'cursor-not-allowed border-gray-300 bg-gray-100'
            : 'border-gray-300 bg-white'
        }`}
      />

      <p id={descriptionId} className="mt-1 text-xs text-slate-500">
        {atCeiling
          ? `Maximum ${max} reached. Remove one to add another.`
          : `Type at least 2 characters. ${selected.length} of ${max} selected.`}
      </p>

      {showSuggestions && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-300 bg-white shadow-lg"
        >
          {isLoading && (
            <li className="px-2 py-1.5 text-sm text-slate-500">Searching…</li>
          )}
          {!isLoading && options.length === 0 && (
            <li className="px-2 py-1.5 text-sm text-slate-500">
              No matching entities
            </li>
          )}
          {!isLoading &&
            options.map((option, index) => (
              <li
                key={option.entity_id}
                id={`${listboxId}-${option.entity_id}`}
                role="option"
                aria-selected={index === highlightedIndex}
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(index);
                }}
                onMouseEnter={() => setHighlightedIndex(index)}
                className={`flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm ${
                  index === highlightedIndex ? "bg-indigo-50" : ""
                }`}
              >
                <EntityName
                  name={option.canonical_name}
                  entityType={option.entity_type}
                  className="truncate"
                />
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
