/**
 * SegmentEditForm component for inline transcript segment correction editing (Feature 035).
 *
 * Implements:
 * - US-4: Inline editing with validation before submission
 * - NFR-009: Vertical layout stack for form elements
 * - WCAG 2.5.8: Touch targets at minimum 44x44px for all interactive elements
 * - WCAG 4.1.3: Status messages via aria-live regions
 * - Keyboard navigation: Escape cancels, Tab order preserved
 *
 * @module components/transcript/corrections/SegmentEditForm
 */

import { useEffect, useRef, useState } from "react";
import {
  CORRECTION_TYPE_LABELS,
  DEFAULT_CORRECTION_TYPE,
} from "../../../types/corrections";
import type { CorrectionType } from "../../../types/corrections";

/**
 * Props for the SegmentEditForm component.
 */
export interface SegmentEditFormProps {
  /** Current segment text (pre-fills textarea) */
  initialText: string;
  /** Segment ID for aria attributes */
  segmentId: number;
  /** Whether the mutation is pending */
  isPending: boolean;
  /** Called with form data when Save is clicked (after local validation passes) */
  onSave: (data: {
    corrected_text: string;
    correction_type: CorrectionType;
    correction_note: string | null;
  }) => void;
  /** Called when Cancel is clicked or Escape is pressed */
  onCancel: () => void;
  /** Server-side error message to display (from mutation onError) */
  serverError?: string | null;
}

/**
 * SegmentEditForm renders an inline form for editing a transcript segment correction.
 *
 * Validation runs on Save click only (not on keystroke). Validation errors are
 * announced via role="alert" for screen reader accessibility. The textarea is
 * auto-focused on mount. Escape key cancels the edit.
 *
 * @example
 * ```tsx
 * <SegmentEditForm
 *   initialText={segment.text}
 *   segmentId={segment.id}
 *   isPending={mutation.isPending}
 *   onSave={(data) => mutation.mutate({ segmentId: segment.id, ...data })}
 *   onCancel={() => setEditState({ mode: "read" })}
 *   serverError={serverError}
 * />
 * ```
 */
export function SegmentEditForm({
  initialText,
  segmentId,
  isPending,
  onSave,
  onCancel,
  serverError,
}: SegmentEditFormProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [text, setText] = useState(initialText);
  const [correctionType, setCorrectionType] = useState<CorrectionType>(
    DEFAULT_CORRECTION_TYPE
  );
  const [note, setNote] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  // Auto-focus the textarea on mount (US-4, accessibility best practice)
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  /**
   * Clears validation error when user types in the textarea.
   * Errors only show after a Save attempt, and clear on next keystroke.
   */
  const handleTextChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(event.target.value);
    if (validationError) {
      setValidationError(null);
    }
  };

  /**
   * Runs local validation and calls onSave if valid.
   * Validation rules (US-4):
   * - Text cannot be empty
   * - Text must differ from initialText
   */
  const handleSave = () => {
    const trimmedText = text.trim();

    if (trimmedText.length === 0) {
      setValidationError("Correction text cannot be empty.");
      return;
    }

    if (trimmedText === initialText.trim()) {
      setValidationError("Correction is identical to the current text.");
      return;
    }

    setValidationError(null);
    onSave({
      corrected_text: trimmedText,
      correction_type: correctionType,
      correction_note: note.trim() || null,
    });
  };

  /**
   * Handles keydown on the form container.
   * - Stops propagation to prevent parent scroll handler from intercepting keys.
   * - Escape cancels the edit.
   */
  const handleFormKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      onCancel();
    }
  };

  const textareaId = `segment-edit-${segmentId}`;
  const errorId = `segment-edit-error-${segmentId}`;
  const correctionTypeId = `correction-type-${segmentId}`;
  const noteId = `correction-note-${segmentId}`;

  const hasError = validationError !== null;

  return (
    <div
      className="flex flex-col gap-2 p-2 bg-white border border-slate-200 rounded-md"
      onKeyDown={handleFormKeyDown}
    >
      {/* Textarea: pre-filled with segment text, auto-focused */}
      <textarea
        ref={textareaRef}
        id={textareaId}
        rows={4}
        value={text}
        onChange={handleTextChange}
        aria-label="Edit segment text"
        aria-invalid={hasError ? "true" : "false"}
        aria-describedby={hasError ? errorId : undefined}
        className={`
          max-h-[200px] overflow-y-auto resize-none w-full
          px-3 py-2
          text-sm text-gray-900
          border rounded-md
          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
          ${hasError ? "border-red-400 bg-red-50" : "border-slate-300 bg-white"}
        `}
      />

      {/* Validation error — announced immediately via role="alert" */}
      {validationError && (
        <p
          id={errorId}
          role="alert"
          className="text-xs text-red-700"
        >
          {validationError}
        </p>
      )}

      {/* Server-side error — shown below validation error */}
      {serverError && (
        <p
          role="alert"
          className="text-xs text-red-700"
        >
          {serverError}
        </p>
      )}

      {/* Correction type select */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={correctionTypeId}
          className="text-xs font-medium text-slate-700"
        >
          Correction type
        </label>
        <select
          id={correctionTypeId}
          value={correctionType}
          onChange={(e) => setCorrectionType(e.target.value as CorrectionType)}
          className="
            w-full px-3 py-2
            text-sm text-gray-900
            border border-slate-300 rounded-md bg-white
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
          "
        >
          {(
            Object.entries(CORRECTION_TYPE_LABELS) as [
              CorrectionType,
              string,
            ][]
          ).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* Correction note input with character counter */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={noteId}
          className="text-xs font-medium text-slate-700"
        >
          Correction note (optional)
        </label>
        <input
          type="text"
          id={noteId}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          placeholder="Explain why this correction is needed…"
          className="
            w-full px-3 py-2
            text-sm text-gray-900
            border border-slate-300 rounded-md bg-white
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
          "
        />
        {/* Visible character counter */}
        <span className="text-xs text-slate-500 text-right" aria-hidden="true">
          {note.length}/500
        </span>
      </div>

      {/* Button row */}
      <div className="flex gap-2">
        {/* Save button: disabled and shows loading state when isPending */}
        <button
          type="button"
          onClick={handleSave}
          disabled={isPending}
          aria-busy={isPending ? "true" : undefined}
          aria-label={isPending ? "Saving correction…" : undefined}
          className="
            min-h-[44px] min-w-[44px]
            px-4 py-2
            text-sm font-medium text-white
            bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          {isPending ? "Saving…" : "Save"}
        </button>

        {/* Cancel button: always enabled even during pending mutation */}
        <button
          type="button"
          onClick={onCancel}
          className="
            min-h-[44px] min-w-[44px]
            px-4 py-2
            text-sm font-medium text-slate-700
            bg-white hover:bg-slate-50
            border border-slate-300
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
