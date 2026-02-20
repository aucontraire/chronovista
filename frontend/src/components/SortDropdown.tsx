/**
 * SortDropdown component for unified sort UI (Feature 027).
 *
 * Generic typed component that renders a native HTML <select> element
 * with sort options, syncing sort_by and sort_order URL parameters.
 *
 * Features:
 * - Native <select> for keyboard accessibility (FR-001)
 * - Supports minimum 2 sort options (FR-001a)
 * - 44×44px minimum hit area per WCAG 2.5.8 (FR-005)
 * - URL parameter synchronization via useUrlParam (FR-024)
 * - Visible focus indicator (FR-032)
 * - Field-specific default sort orders
 * - Toggle same field to reverse order (asc↔desc)
 *
 * @module components/SortDropdown
 */

import { useId } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { SortOption, SortOrder } from '../types/filters';

/**
 * Props for SortDropdown component.
 *
 * @template TField - The sort field type (union of allowed field names)
 */
export interface SortDropdownProps<TField extends string> {
  /** Array of sort options with field/label/defaultOrder */
  options: SortOption<TField>[];
  /** Default sort field when no URL param present */
  defaultField: TField;
  /** Default sort order when no URL param present */
  defaultOrder: SortOrder;
  /** Accessible label for the dropdown (default: "Sort by") */
  label?: string;
}

/**
 * Get the combined value string for the select element.
 * Format: "field:order" (e.g., "upload_date:desc")
 */
function getSortValue<TField extends string>(
  field: TField,
  order: SortOrder
): string {
  return `${field}:${order}`;
}

/**
 * Parse the combined value string back to field and order.
 */
function parseSortValue<TField extends string>(value: string): {
  field: TField;
  order: SortOrder;
} {
  const [field, order] = value.split(':') as [TField, SortOrder];
  return { field, order };
}

/**
 * SortDropdown displays a native <select> dropdown for sorting content.
 *
 * Syncs with URL parameters sort_by and sort_order. When a different field
 * is selected, uses that field's defaultOrder. When the same field is selected
 * with a different order, toggles between asc/desc.
 *
 * @template TField - The sort field type
 * @param props - Component props
 * @returns JSX element with sort dropdown
 *
 * @example
 * ```tsx
 * <SortDropdown
 *   options={[
 *     { field: 'upload_date', label: 'Date Added', defaultOrder: 'desc' },
 *     { field: 'title', label: 'Title', defaultOrder: 'asc' },
 *   ]}
 *   defaultField="upload_date"
 *   defaultOrder="desc"
 *   label="Sort videos by"
 * />
 * ```
 */
export function SortDropdown<TField extends string>({
  options,
  defaultField,
  defaultOrder,
  label = 'Sort by',
}: SortDropdownProps<TField>) {
  const selectId = useId();
  const [searchParams, setSearchParams] = useSearchParams();

  // Get all possible field values for validation
  const allowedFields = options.map((opt) => opt.field);
  const allowedOrders: SortOrder[] = ['asc', 'desc'];

  // Get raw URL params
  const rawSortBy = searchParams.get('sort_by');
  const rawSortOrder = searchParams.get('sort_order');

  // Determine actual sort field and order with coordination logic
  let actualSortBy: TField = defaultField;
  let actualSortOrder: SortOrder = defaultOrder;

  // Case 1: Both params present and valid
  if (
    rawSortBy &&
    allowedFields.includes(rawSortBy as TField) &&
    rawSortOrder &&
    allowedOrders.includes(rawSortOrder as SortOrder)
  ) {
    actualSortBy = rawSortBy as TField;
    actualSortOrder = rawSortOrder as SortOrder;
  }
  // Case 2: Only sort_by present and valid -> use field's defaultOrder
  else if (rawSortBy && allowedFields.includes(rawSortBy as TField)) {
    actualSortBy = rawSortBy as TField;
    const fieldConfig = options.find((opt) => opt.field === actualSortBy);
    actualSortOrder = fieldConfig?.defaultOrder ?? defaultOrder;
  }
  // Case 3: Only sort_order present (no valid sort_by) -> ignore orphaned sort_order, use component defaults
  // Case 4: Neither present -> use component defaults
  // Both handled by initial values above

  // Determine current combined value
  const currentValue = getSortValue(actualSortBy, actualSortOrder);

  // Handle selection change
  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const { field: newField, order: newOrder } = parseSortValue<TField>(
      event.target.value
    );

    // Update URL params (coordinated update)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);

      // Always update both params together or remove both if defaults
      if (newField === defaultField && newOrder === defaultOrder) {
        // Remove both params when returning to defaults
        next.delete('sort_by');
        next.delete('sort_order');
      } else {
        // Set both params
        next.set('sort_by', newField);
        next.set('sort_order', newOrder);
      }

      return next;
    });
  };

  // Generate all option combinations (each field × both orders)
  const allOptions: Array<{ field: TField; order: SortOrder; label: string }> =
    [];

  options.forEach((option) => {
    // Add option with field's default order first
    allOptions.push({
      field: option.field,
      order: option.defaultOrder,
      label: option.label,
    });

    // Add option with opposite order
    const oppositeOrder: SortOrder =
      option.defaultOrder === 'asc' ? 'desc' : 'asc';
    allOptions.push({
      field: option.field,
      order: oppositeOrder,
      label: option.label,
    });
  });

  return (
    <div className="flex items-center gap-2">
      <label
        htmlFor={selectId}
        className="text-sm font-medium text-gray-600 whitespace-nowrap"
      >
        {label}
      </label>
      <select
        id={selectId}
        value={currentValue}
        onChange={handleChange}
        className="block min-h-[44px] min-w-[44px] rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        aria-label={label}
      >
        {allOptions.map((option) => {
          const value = getSortValue(option.field, option.order);
          // Display with arrow indicator: ↑ for asc, ↓ for desc
          const arrow = option.order === 'asc' ? '↑' : '↓';
          const displayLabel = `${option.label} ${arrow}`;

          return (
            <option key={value} value={value}>
              {displayLabel}
            </option>
          );
        })}
      </select>
    </div>
  );
}
