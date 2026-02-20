/**
 * URL parameter management hooks.
 *
 * Provides type-safe URL parameter synchronization with React Router.
 * Implements FR-003 (URL state persistence), FR-024 (browser back/forward),
 * FR-026 (invalid value fallback), FR-027 (snake_case param keys).
 */

import { useSearchParams } from 'react-router-dom';
import { useCallback } from 'react';

/**
 * Generic URL parameter hook with type-safe value constraints.
 *
 * @param paramKey - URL parameter name (snake_case per FR-027)
 * @param defaultValue - Default value when param is absent or invalid
 * @param allowedValues - Optional array of allowed values for validation
 * @returns Tuple of [current value, setter function]
 *
 * @example
 * ```tsx
 * const [sortBy, setSortBy] = useUrlParam('sort_by', 'upload_date', ['upload_date', 'title']);
 * ```
 */
export function useUrlParam<T extends string>(
  paramKey: string,
  defaultValue: T,
  allowedValues?: readonly T[]
): [T, (value: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();

  // Get current value from URL
  const rawValue = searchParams.get(paramKey);

  // Validate against allowed values if provided (FR-026)
  let currentValue: T = defaultValue;
  if (rawValue !== null) {
    if (allowedValues) {
      // Type assertion is safe because we validate against allowedValues
      const isValid = allowedValues.includes(rawValue as T);
      if (isValid) {
        currentValue = rawValue as T;
      }
      // Invalid value falls back to default (FR-026)
    } else {
      currentValue = rawValue as T;
    }
  }

  // Setter function that updates URL params
  const setValue = useCallback(
    (value: T) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === defaultValue) {
          // Remove param if setting to default value
          next.delete(paramKey);
        } else {
          next.set(paramKey, value);
        }
        return next;
      });
    },
    [paramKey, defaultValue, setSearchParams]
  );

  return [currentValue, setValue];
}

/**
 * Boolean URL parameter hook.
 *
 * Treats "true" string as true, any other value (including absence) as false.
 * Unchecking removes the parameter from URL (not setting to "false").
 *
 * @param paramKey - URL parameter name (snake_case per FR-027)
 * @returns Tuple of [current boolean value, setter function]
 *
 * @example
 * ```tsx
 * const [includeUnavailable, setIncludeUnavailable] = useUrlParamBoolean('include_unavailable');
 * // URL: ?include_unavailable=true → returns [true, setter]
 * // URL: (no param) → returns [false, setter]
 * ```
 */
export function useUrlParamBoolean(paramKey: string): [boolean, (value: boolean) => void] {
  const [searchParams, setSearchParams] = useSearchParams();

  // Only "true" string is treated as true
  const currentValue = searchParams.get(paramKey) === 'true';

  const setValue = useCallback(
    (value: boolean) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set(paramKey, 'true');
        } else {
          // Remove param instead of setting to "false" (FR-002)
          next.delete(paramKey);
        }
        return next;
      });
    },
    [paramKey, setSearchParams]
  );

  return [currentValue, setValue];
}
