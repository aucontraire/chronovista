import { useState, useEffect } from "react";

/**
 * A hook that debounces a value by the specified delay.
 *
 * This hook is useful for delaying expensive operations (like API calls)
 * until the user has stopped typing or changing a value.
 *
 * @param value - The value to debounce
 * @param delay - Delay in milliseconds (default: 300ms per SEARCH_CONFIG.DEBOUNCE_DELAY)
 * @returns The debounced value
 *
 * @example
 * ```tsx
 * const [searchTerm, setSearchTerm] = useState('');
 * const debouncedSearchTerm = useDebounce(searchTerm, 300);
 *
 * useEffect(() => {
 *   // This will only run 300ms after the user stops typing
 *   fetchSearchResults(debouncedSearchTerm);
 * }, [debouncedSearchTerm]);
 * ```
 */
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
