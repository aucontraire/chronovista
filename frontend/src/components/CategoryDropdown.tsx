/**
 * CategoryDropdown Component
 *
 * Implements:
 * - T030: Accessible category dropdown with ARIA listbox pattern
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 *
 * Features:
 * - ARIA listbox pattern with role="listbox" and aria-labelledby
 * - role="option" with aria-selected for items
 * - Single selection (category filter)
 * - Keyboard navigation (Arrow Up/Down, Enter, Escape, Home/End)
 * - Visual indication of selected category
 * - "All Categories" option to clear filter
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-002: Focus Management
 * @see FR-ACC-004: Screen Reader Announcements
 * @see FR-ACC-007: Visible Focus Indicators
 */

import { useState, useRef, useEffect, useId } from 'react';
import { useCategories } from '../hooks/useCategories';
import { filterColors } from '../styles/tokens';
import { isApiError } from '../api/config';

interface CategoryDropdownProps {
  /** Currently selected category ID (null for "All Categories") */
  selectedCategory: string | null;
  /** Callback when category selection changes */
  onCategoryChange: (categoryId: string | null) => void;
  /** Optional className for container */
  className?: string;
}

/**
 * CategoryDropdown component for selecting a video category.
 *
 * Provides accessible category selection with keyboard navigation and screen reader support.
 * Only one category can be selected at a time (single selection).
 *
 * @example
 * ```tsx
 * <CategoryDropdown
 *   selectedCategory="10"
 *   onCategoryChange={(categoryId) => setCategory(categoryId)}
 * />
 * ```
 */
export function CategoryDropdown({
  selectedCategory,
  onCategoryChange,
  className = '',
}: CategoryDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const buttonRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  // Unique IDs for ARIA relationships
  const buttonId = useId();
  const listboxId = useId();
  const labelId = useId();
  const descriptionId = useId();
  const announcementId = useId();

  // Fetch categories
  const { categories, isLoading, isError, error, refetch } = useCategories();

  // Add "All Categories" option at the beginning
  const allOption = { category_id: null, name: 'All Categories', assignable: true };
  const options = [allOption, ...categories];

  // Find selected category name
  const selectedCategoryName = selectedCategory
    ? categories.find(cat => cat.category_id === selectedCategory)?.name || 'Unknown'
    : 'All Categories';

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        buttonRef.current &&
        !buttonRef.current.contains(target) &&
        listboxRef.current &&
        !listboxRef.current.contains(target)
      ) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Set initial highlighted index to selected option when opening
  useEffect(() => {
    if (isOpen) {
      const selectedIndex = options.findIndex(
        opt => opt.category_id === selectedCategory
      );
      setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
    }
  }, [isOpen, selectedCategory]);

  const handleToggle = () => {
    setIsOpen(prev => !prev);
  };

  const handleSelect = (categoryId: string | null) => {
    onCategoryChange(categoryId);
    setIsOpen(false);
    setHighlightedIndex(-1);

    // Return focus to button after selection
    buttonRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!isOpen) {
      // Open dropdown with Arrow Down, Arrow Up, Enter, or Space
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev < options.length - 1 ? prev + 1 : 0
        );
        break;

      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev > 0 ? prev - 1 : options.length - 1
        );
        break;

      case 'Enter':
      case ' ':
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < options.length) {
          const selectedOption = options[highlightedIndex];
          if (selectedOption) {
            handleSelect(selectedOption.category_id);
          }
        }
        break;

      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        buttonRef.current?.focus();
        break;

      case 'Home':
        e.preventDefault();
        setHighlightedIndex(0);
        break;

      case 'End':
        e.preventDefault();
        setHighlightedIndex(options.length - 1);
        break;

      case 'Tab':
        // Close dropdown on tab (default behavior will move focus)
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  };

  // Scroll highlighted option into view
  useEffect(() => {
    if (isOpen && highlightedIndex >= 0 && listboxRef.current) {
      const highlightedOption = listboxRef.current.querySelector(
        `[data-index="${highlightedIndex}"]`
      ) as HTMLElement;
      if (highlightedOption) {
        highlightedOption.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [isOpen, highlightedIndex]);

  return (
    <div className={`space-y-2 ${className}`}>
      {/* Label */}
      <label
        id={labelId}
        htmlFor={buttonId}
        className="block text-sm font-medium text-gray-900 dark:text-gray-100"
      >
        Category
      </label>

      {/* Dropdown button */}
      <div className="relative">
        <button
          ref={buttonRef}
          id={buttonId}
          type="button"
          onClick={handleToggle}
          onKeyDown={handleKeyDown}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          disabled={isLoading || isError}
          className={`
            w-full px-4 py-2.5 text-left text-base
            border rounded-lg
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            border-gray-300 dark:border-gray-600
            disabled:bg-gray-100 dark:disabled:bg-gray-900
            disabled:cursor-not-allowed
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
            flex items-center justify-between
          `}
        >
          <span className="flex items-center gap-2">
            {selectedCategory && (
              <span
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  backgroundColor: filterColors.category.background,
                  color: filterColors.category.text,
                }}
                aria-hidden="true"
              >
                Category
              </span>
            )}
            <span>{isLoading ? 'Loading...' : selectedCategoryName}</span>
          </span>

          {/* Dropdown arrow icon */}
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>

        {/* Listbox */}
        {isOpen && !isLoading && !isError && (
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            aria-activedescendant={
              highlightedIndex >= 0
                ? `${listboxId}-option-${highlightedIndex}`
                : undefined
            }
            className="absolute z-10 mt-1 w-full max-h-60 overflow-auto bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg"
          >
            {options.map((option, index) => {
              const isSelected = option.category_id === selectedCategory;
              const isHighlighted = index === highlightedIndex;
              const optionId = `${listboxId}-option-${index}`;

              return (
                <li
                  key={option.category_id ?? 'all'}
                  id={optionId}
                  role="option"
                  aria-selected={isSelected}
                  data-index={index}
                  onClick={() => handleSelect(option.category_id)}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={`
                    px-4 py-2.5 cursor-pointer text-base
                    flex items-center justify-between
                    ${isHighlighted
                      ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100'
                      : 'text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }
                  `}
                >
                  <span className="flex items-center gap-2">
                    {isSelected && (
                      <svg
                        className="w-5 h-5 text-green-600 dark:text-green-400"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                        aria-hidden="true"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                    <span className={isSelected ? 'font-semibold' : ''}>
                      {option.name}
                    </span>
                  </span>

                  {isSelected && (
                    <span className="sr-only">Selected</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Description for screen readers */}
      <p id={descriptionId} className="sr-only">
        Select a category to filter videos. Use arrow keys to navigate options, Enter or Space to select, Escape to close.
      </p>

      {/* Error state with retry button */}
      {isError && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg" role="alert">
          <p className="text-sm text-red-800 dark:text-red-200">
            {isApiError(error) && error.type === 'timeout'
              ? 'Request timed out. Please try again.'
              : 'Error loading categories. Please try again.'}
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

      {/* Screen reader announcement region */}
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {isOpen && `Category dropdown opened, ${options.length} options available`}
        {!isOpen && selectedCategory && `Category filter applied: ${selectedCategoryName}`}
      </div>
    </div>
  );
}
