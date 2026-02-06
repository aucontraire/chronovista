/**
 * ViewModeToggle component for switching between transcript view modes.
 *
 * Provides a toggle between "Segments" (timestamped) and "Full Text" (continuous prose)
 * views for transcript display.
 *
 * Implements accessibility requirements:
 * - NFR-A06: Keyboard-accessible toggle
 * - aria-pressed states for toggle buttons
 * - aria-live announcements for view changes
 *
 * @module components/transcript/ViewModeToggle
 */

import { useCallback, useState } from "react";

/**
 * View mode options for transcript display.
 * - "segments": Timestamped segments with individual entries
 * - "fulltext": Continuous prose view without timestamps
 */
export type ViewMode = "segments" | "fulltext";

/**
 * Props for the ViewModeToggle component.
 */
export interface ViewModeToggleProps {
  /** Currently active view mode */
  mode: ViewMode;
  /** Callback when view mode changes */
  onModeChange: (mode: ViewMode) => void;
}

/**
 * ViewModeToggle provides a toggle button group for switching transcript view modes.
 *
 * Features:
 * - Two toggle options: "Segments" and "Full Text"
 * - Visual styling similar to tabs/segmented control
 * - Keyboard accessible with Enter/Space activation
 * - aria-pressed states for screen readers
 * - aria-live announcement when view changes
 *
 * @example
 * ```tsx
 * const [viewMode, setViewMode] = useState<ViewMode>('segments');
 *
 * <ViewModeToggle
 *   mode={viewMode}
 *   onModeChange={setViewMode}
 * />
 * ```
 */
export function ViewModeToggle({ mode, onModeChange }: ViewModeToggleProps) {
  // State for aria-live announcement
  const [announcement, setAnnouncement] = useState<string>("");

  /**
   * Handles view mode change with accessibility announcement.
   */
  const handleModeChange = useCallback(
    (newMode: ViewMode) => {
      if (newMode === mode) {
        return;
      }

      onModeChange(newMode);

      // Announce the view change for screen readers
      const modeLabel = newMode === "segments" ? "Segments" : "Full Text";
      setAnnouncement(`View changed to ${modeLabel}`);

      // Clear announcement after it's been read
      setTimeout(() => setAnnouncement(""), 1000);
    },
    [mode, onModeChange]
  );

  /**
   * Gets the button classes based on whether it's active.
   */
  const getButtonClasses = (isActive: boolean): string => {
    const baseClasses = `
      px-4 py-2 text-sm font-medium
      transition-colors duration-150
      focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
    `;

    if (isActive) {
      return `${baseClasses} bg-blue-600 text-white`;
    }

    return `${baseClasses} bg-gray-100 text-gray-700 hover:bg-gray-200`;
  };

  return (
    <div className="relative">
      {/* Toggle button group */}
      <div
        role="group"
        aria-label="Transcript view mode"
        className="inline-flex rounded-lg overflow-hidden border border-gray-200"
      >
        {/* Segments button */}
        <button
          type="button"
          onClick={() => handleModeChange("segments")}
          aria-pressed={mode === "segments"}
          className={getButtonClasses(mode === "segments")}
        >
          Segments
        </button>

        {/* Full Text button */}
        <button
          type="button"
          onClick={() => handleModeChange("fulltext")}
          aria-pressed={mode === "fulltext"}
          className={getButtonClasses(mode === "fulltext")}
        >
          Full Text
        </button>
      </div>

      {/* Aria-live region for view change announcements */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcement}
      </div>
    </div>
  );
}
