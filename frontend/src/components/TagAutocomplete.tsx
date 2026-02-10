/**
 * TagAutocomplete Component
 *
 * Implements:
 * - T029: Accessible tag autocomplete with ARIA combobox pattern
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 *
 * Features:
 * - ARIA combobox pattern with role="combobox", aria-expanded, aria-autocomplete="list"
 * - role="listbox" for suggestions with role="option" for items
 * - aria-activedescendant for keyboard navigation
 * - Debounced search using useTags hook
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
import { useTags } from '../hooks/useTags';
import { FILTER_LIMITS } from '../types/filters';
import { filterColors } from '../styles/tokens';
import { isApiError } from '../api/config';

interface TagAutocompleteProps {
  /** Currently selected tags */
  selectedTags: string[];
  /** Callback when a tag is selected */
  onTagSelect: (tag: string) => void;
  /** Callback when a tag is removed */
  onTagRemove: (tag: string) => void;
  /** Maximum number of tags allowed (default: FILTER_LIMITS.MAX_TAGS) */
  maxTags?: number;
  /** Optional className for container */
  className?: string;
}

/**
 * TagAutocomplete component for selecting video tags with autocomplete.
 *
 * Provides accessible tag selection with keyboard navigation, screen reader support,
 * and visual feedback for filter limits.
 *
 * @example
 * ```tsx
 * <TagAutocomplete
 *   selectedTags={['react', 'typescript']}
 *   onTagSelect={(tag) => setTags([...tags, tag])}
 *   onTagRemove={(tag) => setTags(tags.filter(t => t !== tag))}
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

  // Fetch tags with debounced search
  const { tags, suggestions, isLoading, isError, error, refetch } = useTags({ search: inputValue });

  // Filter out already selected tags and limit results
  const availableTags = tags
    .filter(tag => !selectedTags.includes(tag))
    .slice(0, 10);

  // Filter out already selected tags from fuzzy suggestions and limit to 3
  const availableSuggestions = suggestions
    .filter(tag => !selectedTags.includes(tag))
    .slice(0, 3);

  const isMaxReached = selectedTags.length >= maxTags;
  const showSuggestions = isOpen && inputValue.length > 0 && !isMaxReached;

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
    setIsOpen(value.length > 0 && !isMaxReached);
    setHighlightedIndex(-1);
  };

  const handleTagSelect = (tag: string) => {
    if (!selectedTags.includes(tag) && selectedTags.length < maxTags) {
      onTagSelect(tag);
      setInputValue('');
      setIsOpen(false);
      setHighlightedIndex(-1);

      // Return focus to input after selection
      inputRef.current?.focus();
    }
  };

  const handleTagRemove = (tag: string) => {
    onTagRemove(tag);
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
            handleTagSelect(selectedTag);
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

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Label */}
      <label
        id={labelId}
        htmlFor={comboboxId}
        className="block text-sm font-medium text-gray-900 dark:text-gray-100"
      >
        Tags
        <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
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
              key={tag}
              role="listitem"
              className="inline-flex items-center gap-1.5 px-3 py-2 sm:py-1.5 min-h-[44px] sm:min-h-0 rounded-full text-sm font-medium border"
              style={{
                backgroundColor: filterColors.tag.background,
                color: filterColors.tag.text,
                borderColor: filterColors.tag.border,
              }}
            >
              <span>{tag}</span>
              <button
                type="button"
                onClick={() => handleTagRemove(tag)}
                aria-label={`Remove tag ${tag}`}
                className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] sm:min-w-[24px] sm:min-h-[24px] -my-2 sm:my-0 -me-2 sm:me-0 rounded-full hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                style={{ color: filterColors.tag.text }}
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
          aria-controls={showSuggestions ? listboxId : undefined}
          aria-activedescendant={activeDescendantId}
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => !isMaxReached && inputValue.length > 0 && setIsOpen(true)}
          disabled={isMaxReached}
          placeholder={isMaxReached ? 'Maximum tags reached' : 'Type to search tags...'}
          className={`
            w-full px-4 py-2.5 text-base
            border rounded-lg
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-500 dark:placeholder-gray-400
            disabled:bg-gray-100 dark:disabled:bg-gray-900
            disabled:cursor-not-allowed
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
            ${isMaxReached ? 'border-gray-300' : 'border-gray-300 dark:border-gray-600'}
          `}
        />

        {/* Loading indicator */}
        {isLoading && inputValue.length > 0 && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" aria-hidden="true" />
          </div>
        )}

        {/* Suggestions listbox */}
        {showSuggestions && availableTags.length > 0 && (
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            className="absolute z-50 left-0 right-0 top-full mt-1 max-h-60 overflow-auto bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg"
          >
          {availableTags.map((tag, index) => {
            const isHighlighted = index === highlightedIndex;
            const optionId = `${listboxId}-option-${index}`;

            return (
              <li
                key={tag}
                id={optionId}
                role="option"
                aria-selected={isHighlighted}
                onClick={() => handleTagSelect(tag)}
                onMouseEnter={() => setHighlightedIndex(index)}
                className={`
                  px-4 py-2.5 cursor-pointer text-base
                  ${isHighlighted
                    ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100'
                    : 'text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }
                `}
              >
                {tag}
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
      </p>

      {/* Error state with retry button */}
      {isError && inputValue.length > 0 && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg" role="alert">
          <p className="text-sm text-red-800 dark:text-red-200">
            {isApiError(error) && error.type === 'timeout'
              ? 'Request timed out. Please try again.'
              : 'Error loading tags. Please try again.'}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="mt-2 px-3 py-1 text-sm font-medium text-red-700 dark:text-red-300 hover:text-red-800 dark:hover:text-red-200 border border-red-300 dark:border-red-600 rounded hover:bg-red-100 dark:hover:bg-red-900/40 focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* No results message with fuzzy suggestions */}
      {showSuggestions && availableTags.length === 0 && !isLoading && !isError && (
        <div className="text-sm text-gray-500 dark:text-gray-400">
          <p>No tags found matching "{inputValue}"</p>
          {availableSuggestions.length > 0 && (
            <div className="mt-2">
              <span className="font-medium text-gray-700 dark:text-gray-300">Did you mean: </span>
              {availableSuggestions.map((suggestion, index) => (
                <span key={suggestion}>
                  <button
                    type="button"
                    onClick={() => {
                      // Select the suggested tag directly
                      handleTagSelect(suggestion);
                    }}
                    className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded px-0.5"
                  >
                    {suggestion}
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
        {showSuggestions && availableTags.length > 0 &&
          `${availableTags.length} tag${availableTags.length === 1 ? '' : 's'} found`
        }
        {selectedTags.length > 0 &&
          `, ${selectedTags.length} tag${selectedTags.length === 1 ? '' : 's'} selected`
        }
      </div>
    </div>
  );
}
