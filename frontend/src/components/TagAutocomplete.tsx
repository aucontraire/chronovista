/**
 * TagAutocomplete Component
 *
 * Implements:
 * - T029: Accessible tag autocomplete with ARIA combobox pattern
 * - T009-T012: Canonical tag integration with two-line items, fuzzy suggestions,
 *   rate limit UI, truncation, and screen reader ARIA labels
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 * - FR-001: Two-line dropdown items (canonical_form · video_count · variations)
 * - FR-018: Interaction states (hover gray-100, focus blue-100/blue-900)
 * - FR-019/FR-020/FR-023: Fuzzy suggestion buttons
 * - FR-004: Rate limit UI without red/error colors
 * - FR-025: Screen reader text uses "variations" (never "var.")
 * - R8: 25-char truncation with title tooltip
 *
 * Features:
 * - ARIA combobox pattern with role="combobox", aria-expanded, aria-autocomplete="list"
 * - role="listbox" for suggestions with role="option" for items
 * - aria-activedescendant for keyboard navigation
 * - Debounced search using useCanonicalTags hook
 * - Two-line option items: canonical_form + video_count on line 1, variations on line 2
 * - Fuzzy suggestions in role="group" when tags empty
 * - Rate limit state with countdown message (no red colors)
 * - 25-char truncation with title tooltip
 * - Maximum tag limit validation
 * - Keyboard navigation (Arrow Up/Down, Enter, Escape, Tab)
 * - Filter pills with remove buttons
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-002: Focus Management
 * @see FR-ACC-004: Screen Reader Announcements
 * @see FR-ACC-007: Visible Focus Indicators
 */

import { useState, useRef, useEffect, useId } from 'react';
import { useCanonicalTags } from '../hooks/useCanonicalTags';
import type { SelectedCanonicalTag } from '../types/canonical-tags';
import { FILTER_LIMITS } from '../types/filters';
import { filterColors } from '../styles/tokens';
import { isApiError } from '../api/config';

/** Maximum characters before truncating canonical_form in dropdown (R8) */
const TRUNCATION_LIMIT = 25;

/**
 * Truncates a string to TRUNCATION_LIMIT chars with ellipsis.
 * Returns the original string when within the limit.
 */
function truncateLabel(value: string): string {
  return value.length > TRUNCATION_LIMIT
    ? `${value.slice(0, TRUNCATION_LIMIT)}…`
    : value;
}

interface TagAutocompleteProps {
  /** Currently selected canonical tags */
  selectedTags: SelectedCanonicalTag[];
  /** Callback when a canonical tag is selected */
  onTagSelect: (tag: SelectedCanonicalTag) => void;
  /** Callback when a canonical tag is removed — receives normalized_form */
  onTagRemove: (normalizedForm: string) => void;
  /** Maximum number of tags allowed (default: FILTER_LIMITS.MAX_TAGS) */
  maxTags?: number;
  /** Optional className for container */
  className?: string;
}

/**
 * TagAutocomplete component for selecting canonical video tags with autocomplete.
 *
 * Provides accessible tag selection with keyboard navigation, screen reader support,
 * two-line dropdown items, fuzzy suggestions, and rate limit UI.
 *
 * @example
 * ```tsx
 * <TagAutocomplete
 *   selectedTags={[{ canonical_form: 'React', normalized_form: 'react', alias_count: 3 }]}
 *   onTagSelect={(tag) => setTags([...tags, tag])}
 *   onTagRemove={(normalizedForm) => setTags(tags.filter(t => t.normalized_form !== normalizedForm))}
 * />
 * ```
 */
export function TagAutocomplete({
  selectedTags,
  onTagSelect,
  onTagRemove,
  maxTags = FILTER_LIMITS.MAX_TAGS,
  className = '',
}: TagAutocompleteProps) {
  const [inputValue, setInputValue] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  // Unique IDs for ARIA relationships
  const comboboxId = useId();
  const listboxId = useId();
  const labelId = useId();
  const descriptionId = useId();
  const announcementId = useId();

  // Fetch canonical tags with debounced search
  const {
    tags,
    suggestions,
    isLoading,
    isError,
    error,
    isRateLimited,
    rateLimitRetryAfter,
  } = useCanonicalTags(inputValue);

  // Filter out already selected tags (by normalized_form) and limit results
  const selectedNormalizedForms = new Set(selectedTags.map(t => t.normalized_form));
  const availableTags = tags
    .filter(tag => !selectedNormalizedForms.has(tag.normalized_form))
    .slice(0, 10);

  // Filter out already selected suggestions and limit to 3
  const availableSuggestions = (suggestions ?? [])
    .filter(s => !selectedNormalizedForms.has(s.normalized_form))
    .slice(0, 3);

  const isMaxReached = selectedTags.length >= maxTags;
  const showSuggestions = isOpen && inputValue.length > 0 && !isMaxReached && !isRateLimited;

  // Reset highlighted index when tags change
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [availableTags]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      const inputEl = inputRef.current;
      const listboxEl = listboxRef.current;

      if (
        inputEl &&
        !inputEl.contains(target) &&
        listboxEl &&
        !listboxEl.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    setIsOpen(value.length > 0 && !isMaxReached && !isRateLimited);
    setHighlightedIndex(-1);
  };

  const handleTagSelect = (tag: SelectedCanonicalTag) => {
    if (
      !selectedNormalizedForms.has(tag.normalized_form) &&
      selectedTags.length < maxTags
    ) {
      onTagSelect(tag);
      setInputValue('');
      setIsOpen(false);
      setHighlightedIndex(-1);

      // Return focus to input after selection
      inputRef.current?.focus();
    }
  };

  const handleTagRemove = (normalizedForm: string) => {
    onTagRemove(normalizedForm);
    // Return focus to input after removal
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || availableTags.length === 0) {
      // Allow Escape to close even if no suggestions
      if (e.key === 'Escape') {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev < availableTags.length - 1 ? prev + 1 : 0
        );
        break;

      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev > 0 ? prev - 1 : availableTags.length - 1
        );
        break;

      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < availableTags.length) {
          const selectedTag = availableTags[highlightedIndex];
          if (selectedTag) {
            handleTagSelect({
              canonical_form: selectedTag.canonical_form,
              normalized_form: selectedTag.normalized_form,
              alias_count: selectedTag.alias_count,
            });
          }
        }
        break;

      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;

      case 'Home':
        if (showSuggestions) {
          e.preventDefault();
          setHighlightedIndex(0);
        }
        break;

      case 'End':
        if (showSuggestions) {
          e.preventDefault();
          setHighlightedIndex(availableTags.length - 1);
        }
        break;

      case 'Tab':
        // Close dropdown on tab (default behavior will move focus)
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  };

  // Generate ID for highlighted option (aria-activedescendant)
  const activeDescendantId = highlightedIndex >= 0
    ? `${listboxId}-option-${highlightedIndex}`
    : undefined;

  /**
   * Build an accessible aria-label for a dropdown option.
   * Uses "variations" (never "var.") per FR-025.
   * alias_count - 1 gives the variation count (canonical itself is not a variation).
   */
  function buildOptionAriaLabel(canonicalForm: string, videoCount: number, aliasCount: number): string {
    const variationCount = aliasCount - 1;
    if (variationCount > 0) {
      return `${canonicalForm}, ${videoCount} videos, ${variationCount} variations`;
    }
    return `${canonicalForm}, ${videoCount} videos`;
  }

  // Announcement text for the live region
  let announcementText = '';
  if (isRateLimited) {
    announcementText = 'Too many requests. Search will be available again shortly.';
  } else if (showSuggestions && availableTags.length > 0) {
    announcementText = `${availableTags.length} tag${availableTags.length === 1 ? '' : 's'} found`;
    if (selectedTags.length > 0) {
      announcementText += `, ${selectedTags.length} tag${selectedTags.length === 1 ? '' : 's'} selected`;
    }
  } else if (showSuggestions && availableTags.length === 0 && availableSuggestions.length > 0) {
    const suggestionNames = availableSuggestions.map(s => s.canonical_form).join(', ');
    announcementText = `No tags found. Did you mean: ${suggestionNames}?`;
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Label */}
      <label
        id={labelId}
        htmlFor={comboboxId}
        className="block text-sm font-medium text-gray-900"
      >
        Tags
        <span className="ml-2 text-xs text-gray-500">
          ({selectedTags.length}/{maxTags})
        </span>
      </label>

      {/* Selected tags display */}
      {selectedTags.length > 0 && (
        <div
          className="flex flex-wrap gap-2"
          role="list"
          aria-label="Selected tags"
        >
          {selectedTags.map((tag) => (
            <div
              key={tag.normalized_form}
              role="listitem"
              className="inline-flex items-center gap-1.5 px-3 py-2 sm:py-1.5 min-h-[44px] sm:min-h-0 rounded-full text-sm font-medium border"
              style={{
                backgroundColor: filterColors.canonical_tag.background,
                color: filterColors.canonical_tag.text,
                borderColor: filterColors.canonical_tag.border,
              }}
            >
              <span>{tag.canonical_form}</span>
              <button
                type="button"
                onClick={() => handleTagRemove(tag.normalized_form)}
                aria-label={`Remove tag ${tag.canonical_form}`}
                className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] sm:min-w-[24px] sm:min-h-[24px] -my-2 sm:my-0 -me-2 sm:me-0 rounded-full hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                style={{ color: filterColors.canonical_tag.text }}
              >
                <svg
                  className="w-4 h-4 sm:w-3 sm:h-3"
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

      {/* Combobox input */}
      <div className="relative">
        <input
          ref={inputRef}
          id={comboboxId}
          type="text"
          role="combobox"
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          aria-expanded={showSuggestions && availableTags.length > 0}
          aria-autocomplete="list"
          aria-controls={showSuggestions && availableTags.length > 0 ? listboxId : undefined}
          aria-activedescendant={activeDescendantId}
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (!isMaxReached && !isRateLimited && inputValue.length > 0) {
              setIsOpen(true);
            }
          }}
          disabled={isMaxReached || isRateLimited}
          placeholder={
            isRateLimited
              ? 'Too many requests. Please wait.'
              : isMaxReached
              ? 'Maximum tags reached'
              : 'Type to search tags...'
          }
          className={`
            w-full px-4 py-2.5 text-base
            border rounded-lg
            text-gray-900
            placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
            ${isRateLimited
              ? 'bg-gray-100 cursor-not-allowed border-gray-300'
              : isMaxReached
              ? 'bg-gray-100 cursor-not-allowed border-gray-300'
              : 'bg-white border-gray-300'
            }
          `}
        />

        {/* Loading indicator */}
        {isLoading && inputValue.length > 0 && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div
              className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
              aria-hidden="true"
            />
          </div>
        )}

        {/* Suggestions listbox */}
        {showSuggestions && availableTags.length > 0 && (
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            className="absolute z-50 left-0 right-0 top-full mt-1 max-h-60 overflow-auto bg-white border border-gray-300 rounded-lg shadow-lg"
          >
            {availableTags.map((tag, index) => {
              const isHighlighted = index === highlightedIndex;
              const optionId = `${listboxId}-option-${index}`;
              const displayLabel = truncateLabel(tag.canonical_form);
              const needsTooltip = tag.canonical_form.length > TRUNCATION_LIMIT;
              const variationCount = tag.alias_count - 1;
              const ariaLabel = buildOptionAriaLabel(
                tag.canonical_form,
                tag.video_count,
                tag.alias_count,
              );

              return (
                <li
                  key={tag.normalized_form}
                  id={optionId}
                  role="option"
                  aria-selected={isHighlighted}
                  aria-label={ariaLabel}
                  title={needsTooltip ? tag.canonical_form : undefined}
                  onClick={() =>
                    handleTagSelect({
                      canonical_form: tag.canonical_form,
                      normalized_form: tag.normalized_form,
                      alias_count: tag.alias_count,
                    })
                  }
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={`
                    px-4 py-2.5 cursor-pointer
                    ${isHighlighted
                      ? 'bg-blue-100 text-blue-900'
                      : 'text-gray-900 hover:bg-gray-100'
                    }
                  `}
                >
                  {/* Line 1: canonical_form · video_count */}
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium leading-tight">
                      {displayLabel}
                    </span>
                    <span className="text-xs text-gray-500 leading-tight">
                      {tag.video_count} videos
                    </span>
                  </div>
                  {/* Line 2: variation count (only when alias_count > 1) */}
                  {variationCount > 0 && (
                    <div className="text-xs text-gray-400 leading-tight mt-0.5">
                      {variationCount} variations
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Description for screen readers */}
      <p id={descriptionId} className="sr-only">
        Type to search for tags. Use arrow keys to navigate suggestions, Enter to select, Escape to close.
        {isMaxReached && ` Maximum of ${maxTags} tags reached.`}
        {isRateLimited && ` Search is temporarily rate limited. Please wait ${rateLimitRetryAfter} seconds.`}
      </p>

      {/* Rate limit message — no red/error colors per FR-004 */}
      {isRateLimited && (
        <div
          className="p-3 bg-gray-50 border border-gray-200 rounded-lg"
          role="status"
          aria-live="polite"
        >
          <p className="text-sm text-gray-700">
            Too many requests. Please wait{rateLimitRetryAfter > 0 ? ` ${rateLimitRetryAfter} seconds` : ''}.
          </p>
        </div>
      )}

      {/* Error state with retry button */}
      {isError && !isRateLimited && inputValue.length > 0 && (
        <div
          className="p-3 bg-red-50 border border-red-200 rounded-lg"
          role="alert"
        >
          <p className="text-sm text-red-800">
            {isApiError(error) && error.type === 'timeout'
              ? 'Request timed out. Please try again.'
              : 'Error loading tags. Please try again.'}
          </p>
        </div>
      )}

      {/* No results message with fuzzy suggestions (FR-019/FR-020/FR-023) */}
      {showSuggestions && availableTags.length === 0 && !isLoading && !isError && (
        <div className="text-sm text-gray-500">
          <p>No tags found matching "{inputValue}"</p>
          {availableSuggestions.length > 0 && (
            <div
              role="group"
              aria-label="Fuzzy suggestions"
              className="mt-2"
            >
              <span className="font-medium text-gray-700">Did you mean: </span>
              {availableSuggestions.map((suggestion, index) => (
                <span key={suggestion.normalized_form}>
                  <button
                    type="button"
                    aria-label={`Did you mean ${suggestion.canonical_form}?`}
                    onClick={() => {
                      handleTagSelect({
                        canonical_form: suggestion.canonical_form,
                        normalized_form: suggestion.normalized_form,
                        // Suggestions don't include alias_count — treat as 1
                        alias_count: 1,
                      });
                    }}
                    className="text-blue-600 hover:text-blue-800 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded px-0.5"
                  >
                    {suggestion.canonical_form}
                  </button>
                  {index < availableSuggestions.length - 1 && <span>, </span>}
                </span>
              ))}
              <span>?</span>
            </div>
          )}
        </div>
      )}

      {/* Screen reader announcement region */}
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcementText}
      </div>
    </div>
  );
}
