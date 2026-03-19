/**
 * ExclusionPatternsSection — displays and manages exclusion patterns for a
 * named entity.
 *
 * Exclusion patterns are text phrases that should NOT trigger entity mention
 * detection. For example, entity "Mexico" might have exclusion pattern
 * "New Mexico" so "New Mexico" doesn't get flagged as a "Mexico" mention.
 *
 * Features:
 * - Lists current exclusion patterns as removable pills
 * - Inline remove button (X) per pattern with loading state
 * - "Add pattern" form at the bottom (text input + Add button)
 * - Empty state when no patterns exist
 * - 409 duplicate error shown as inline user-friendly message
 * - Accessible: proper labels, keyboard navigation, aria attributes
 *
 * Visual and interaction patterns mirror the Aliases section in EntityDetailPage.
 */

import { useState, useRef, useEffect } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";

import {
  addExclusionPattern,
  removeExclusionPattern,
} from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ExclusionPatternsSectionProps {
  /** UUID of the named entity. */
  entityId: string;
  /** Current exclusion patterns from the entity detail response. */
  patterns: string[];
}

// ---------------------------------------------------------------------------
// Icons (inline SVG — no icon library dependency)
// ---------------------------------------------------------------------------

function XMarkIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={2}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 18 18 6M6 6l12 12"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Pattern pill (with remove button)
// ---------------------------------------------------------------------------

interface PatternPillProps {
  pattern: string;
  entityId: string;
  onRemoved: () => void;
}

function PatternPill({ pattern, entityId, onRemoved }: PatternPillProps) {
  const [isRemoving, setIsRemoving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (errorTimerRef.current !== null) {
        clearTimeout(errorTimerRef.current);
      }
    };
  }, []);

  async function handleRemove() {
    if (isRemoving) return;
    setIsRemoving(true);
    setErrorMsg(null);
    try {
      await removeExclusionPattern(entityId, pattern);
      onRemoved();
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      let message = "Failed to remove pattern. Please try again.";
      if (status === 404) {
        message = "Pattern or entity not found. Please refresh the page.";
      }
      setErrorMsg(message);
      // Auto-dismiss error after 4 seconds.
      errorTimerRef.current = setTimeout(() => {
        setErrorMsg(null);
        errorTimerRef.current = null;
      }, 4000);
      setIsRemoving(false);
    }
  }

  return (
    <li className="flex flex-col gap-0.5">
      <div className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 bg-orange-50 text-orange-800 border border-orange-200 rounded-full text-sm font-medium max-w-full">
        <span className="truncate" title={pattern}>
          {pattern}
        </span>
        <button
          type="button"
          onClick={() => void handleRemove()}
          disabled={isRemoving}
          aria-label={`Remove exclusion pattern "${pattern}"`}
          className="flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full text-orange-600 hover:bg-orange-200 hover:text-orange-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isRemoving ? (
            <span className="sr-only">Removing…</span>
          ) : (
            <XMarkIcon className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
      {errorMsg && (
        <p className="text-xs text-red-600 pl-1" role="alert">
          {errorMsg}
        </p>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Add pattern form
// ---------------------------------------------------------------------------

interface AddPatternFormProps {
  entityId: string;
  /** Called after a successful addition so the parent can refetch. */
  onAdded: () => void;
}

/**
 * Compact form for adding a new exclusion pattern to a named entity.
 * Shows inline green confirmation on success, and inline red error on failure.
 */
function AddPatternForm({ entityId, onAdded }: AddPatternFormProps) {
  const [pattern, setPattern] = useState("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: (pat: string) => addExclusionPattern(entityId, pat),
    onSuccess: (_data, pat) => {
      setPattern("");
      setSuccessMsg(`"${pat}" added as exclusion pattern.`);
      onAdded();

      // Auto-clear success message after 3 seconds.
      successTimerRef.current = setTimeout(() => {
        setSuccessMsg(null);
      }, 3000);

      // Return focus to the input so the user can add another pattern.
      inputRef.current?.focus();
    },
    onError: (err: unknown) => {
      const status = (err as { status?: number } | null)?.status;
      if (status === 409) {
        setErrorMsg("This exclusion pattern already exists for the entity.");
      } else if (status === 404) {
        setErrorMsg("Entity not found. Please refresh the page.");
      } else {
        setErrorMsg("Failed to add exclusion pattern. Please try again.");
      }
    },
  });

  // Clean up success timer on unmount.
  useEffect(() => {
    return () => {
      if (successTimerRef.current !== null) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = pattern.trim();
    if (!trimmed) return;

    setSuccessMsg(null);
    setErrorMsg(null);
    mutation.mutate(trimmed);
  }

  const isPending = mutation.isPending;

  return (
    <div className="pt-3 mt-3 border-t border-slate-100">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2"
        aria-label="Add new exclusion pattern"
      >
        <input
          ref={inputRef}
          type="text"
          value={pattern}
          onChange={(e) => {
            setPattern(e.target.value);
            // Clear error when the user starts typing again.
            if (errorMsg) setErrorMsg(null);
          }}
          placeholder="Add exclusion pattern…"
          className="flex-1 min-w-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-gray-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          disabled={isPending}
          aria-label="Exclusion pattern text"
          maxLength={500}
        />
        <button
          type="submit"
          disabled={isPending || !pattern.trim()}
          className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "Adding…" : "Add"}
        </button>
      </form>

      {/* Inline feedback */}
      {successMsg && (
        <p className="mt-1.5 text-xs text-green-600" role="status" aria-live="polite">
          {successMsg}
        </p>
      )}
      {errorMsg && (
        <p className="mt-1.5 text-xs text-red-600" role="alert">
          {errorMsg}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * ExclusionPatternsSection renders a card listing the current exclusion
 * patterns for a named entity with per-pattern removal and an add form.
 *
 * Patterns come from the entity detail query (`exclusion_patterns` field), so
 * adding or removing a pattern calls `queryClient.invalidateQueries` on the
 * `entity-detail` key to refresh the list from the server.
 */
export function ExclusionPatternsSection({
  entityId,
  patterns,
}: ExclusionPatternsSectionProps) {
  const queryClient = useQueryClient();

  function handleChange() {
    void queryClient.invalidateQueries({
      queryKey: ["entity-detail", entityId],
    });
  }

  return (
    <section aria-labelledby="entity-exclusion-patterns-heading" className="mb-6">
      <h2
        id="entity-exclusion-patterns-heading"
        className="text-lg font-semibold text-gray-900 mb-3"
      >
        Exclusion Patterns
      </h2>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        {/* Help text */}
        <p className="text-xs text-gray-500 mb-3">
          Phrases listed here will not trigger mention detection for this
          entity. For example, "New Mexico" can be excluded so it doesn't
          count as a "Mexico" mention.
        </p>

        {/* Pattern list or empty state */}
        {patterns.length > 0 ? (
          <ul
            className="flex flex-wrap gap-2"
            aria-label="Current exclusion patterns"
          >
            {patterns.map((p) => (
              <PatternPill
                key={p}
                pattern={p}
                entityId={entityId}
                onRemoved={handleChange}
              />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400 italic">
            No exclusion patterns defined.
          </p>
        )}

        {/* Add pattern form */}
        <AddPatternForm entityId={entityId} onAdded={handleChange} />
      </div>
    </section>
  );
}
