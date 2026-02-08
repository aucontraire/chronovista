/**
 * SearchInput Component
 *
 * Implements FR-001, FR-002, FR-025: Search query input with validation and debouncing.
 *
 * Features:
 * - Query length validation (2-500 characters)
 * - 300ms debounce after user stops typing
 * - Accessible ARIA labels and form semantics
 * - Real-time validation hints
 *
 * @see FR-001: Search query input
 * @see FR-002: Debounced search execution
 * @see FR-025: Query length limits
 */

import { useEffect, useRef } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { SEARCH_CONFIG } from "../config/search";

interface SearchInputProps {
  /** Current search query value */
  value: string;
  /** Immediate onChange handler (fires on every keystroke) */
  onChange: (value: string) => void;
  /** Debounced onChange handler (fires 300ms after user stops typing) */
  onDebouncedChange: (value: string) => void;
  /** Whether to autofocus the input on mount */
  autoFocus?: boolean;
}

/**
 * Search input component with debouncing and validation.
 *
 * This component manages the search query input field with real-time validation
 * and debounced search execution to prevent excessive API calls.
 *
 * @example
 * ```tsx
 * <SearchInput
 *   value={query}
 *   onChange={setQuery}
 *   onDebouncedChange={handleSearch}
 * />
 * ```
 */
export function SearchInput({
  value,
  onChange,
  onDebouncedChange,
  autoFocus = false,
}: SearchInputProps) {
  const debouncedValue = useDebounce(value, SEARCH_CONFIG.DEBOUNCE_DELAY);
  const isFirstRender = useRef(true);

  // Trigger debounced callback when debounced value changes
  useEffect(() => {
    // Skip the first render to avoid triggering search on initial mount
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    onDebouncedChange(debouncedValue);
  }, [debouncedValue, onDebouncedChange]);

  // Validation state
  const isTooShort = value.length > 0 && value.length < SEARCH_CONFIG.MIN_QUERY_LENGTH;
  const isTooLong = value.length > SEARCH_CONFIG.MAX_QUERY_LENGTH;
  const showHint = isTooShort || isTooLong;
  const isInvalid = isTooShort;

  // Truncate input at max length
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    if (newValue.length <= SEARCH_CONFIG.MAX_QUERY_LENGTH) {
      onChange(newValue);
    } else {
      // Truncate and show warning
      onChange(newValue.slice(0, SEARCH_CONFIG.MAX_QUERY_LENGTH));
    }
  };

  return (
    <form role="search" onSubmit={(e) => e.preventDefault()} className="w-full">
      <div className="relative">
        <input
          type="search"
          value={value}
          onChange={handleChange}
          placeholder="Search transcripts..."
          aria-label="Search transcripts"
          aria-describedby="search-hint"
          aria-controls="search-results"
          aria-invalid={isInvalid}
          autoFocus={autoFocus}
          className={`
            w-full px-4 py-3 pr-12
            text-base
            border rounded-lg
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-500 dark:placeholder-gray-400
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
            ${isTooShort ? "border-yellow-500" : ""}
            ${isTooLong ? "border-red-500" : "border-gray-300 dark:border-gray-600"}
          `}
        />

        {/* Search icon */}
        <div className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400">
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
      </div>

      {/* Validation hints - always render for aria-describedby reference */}
      <p
        id="search-hint"
        className={`
          mt-2 text-sm
          ${!showHint ? "sr-only" : ""}
          ${isTooShort ? "text-yellow-600 dark:text-yellow-500" : ""}
          ${isTooLong ? "text-red-600 dark:text-red-500" : ""}
        `}
        role={showHint ? "alert" : undefined}
      >
        {isTooShort && `Enter at least ${SEARCH_CONFIG.MIN_QUERY_LENGTH} characters`}
        {isTooLong && `Query truncated to ${SEARCH_CONFIG.MAX_QUERY_LENGTH} characters`}
        {!showHint && `Enter at least ${SEARCH_CONFIG.MIN_QUERY_LENGTH} characters to search`}
      </p>
    </form>
  );
}
