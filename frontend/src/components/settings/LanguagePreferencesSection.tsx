/**
 * LanguagePreferencesSection — displays and manages user language preferences
 * within the Settings page.
 *
 * Implements Feature 049 requirements:
 * - FR-002: Group existing preferences into 4 sections (Fluent, Learning, Curious, Exclude)
 * - FR-005: Per-preference remove button
 * - FR-006: "Reset All" button with confirmation dialog
 * - FR-007: Language display name with muted code in parentheses
 * - FR-008: Descriptive heading per preference type group
 * - FR-009: Inline duplicate validation error from DuplicateLanguageError
 * - FR-010: Empty state with explanatory text when no preferences exist
 * - FR-021: Loading skeleton while fetching
 * - FR-022: Inline error with retry button on API failure
 * - FR-023: Searchable language dropdown (filterable combobox)
 * - FR-024: Preferences displayed in priority order within each group
 * - FR-029: Full accessibility — ARIA groups, labels, keyboard nav, aria-live
 *
 * @module components/settings/LanguagePreferencesSection
 */

import { useState, useRef, useId, useEffect, useCallback } from "react";

import {
  useLanguagePreferences,
  DuplicateLanguageError,
} from "../../hooks/useLanguagePreferences";
import type { LanguagePreferenceItem } from "../../hooks/useLanguagePreferences";
import type { SupportedLanguage } from "../../api/settings";

// ---------------------------------------------------------------------------
// Constants — preference type metadata
// ---------------------------------------------------------------------------

const PREFERENCE_TYPES = [
  { value: "fluent", label: "Fluent" },
  { value: "learning", label: "Learning" },
  { value: "curious", label: "Curious" },
  { value: "exclude", label: "Exclude" },
] as const;

type PreferenceTypeValue = (typeof PREFERENCE_TYPES)[number]["value"];

interface PreferenceTypeConfig {
  label: string;
  description: string;
  pillClasses: string;
  badgeClasses: string;
}

const PREFERENCE_TYPE_CONFIG: Record<PreferenceTypeValue, PreferenceTypeConfig> =
  {
    fluent: {
      label: "Fluent",
      description: "Always download transcripts in these languages",
      pillClasses:
        "bg-emerald-50 border-emerald-200 text-emerald-800",
      badgeClasses:
        "text-emerald-700 hover:bg-emerald-100 hover:text-emerald-900 focus-visible:ring-emerald-500",
    },
    learning: {
      label: "Learning",
      description: "Download if available",
      pillClasses:
        "bg-blue-50 border-blue-200 text-blue-800",
      badgeClasses:
        "text-blue-700 hover:bg-blue-100 hover:text-blue-900 focus-visible:ring-blue-500",
    },
    curious: {
      label: "Curious",
      description:
        "Never auto-download; available on-demand only via explicit language selection",
      pillClasses:
        "bg-violet-50 border-violet-200 text-violet-800",
      badgeClasses:
        "text-violet-700 hover:bg-violet-100 hover:text-violet-900 focus-visible:ring-violet-500",
    },
    exclude: {
      label: "Exclude",
      description: "Never download",
      pillClasses:
        "bg-rose-50 border-rose-200 text-rose-800",
      badgeClasses:
        "text-rose-700 hover:bg-rose-100 hover:text-rose-900 focus-visible:ring-rose-500",
    },
  };

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

function ExclamationTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LanguagePreferencesSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading language preferences"
      aria-busy="true"
      className="animate-pulse space-y-4"
    >
      {/* Skeleton preference groups */}
      {[1, 2, 3].map((i) => (
        <div key={i}>
          <div className="h-4 bg-slate-200 rounded w-24 mb-2" />
          <div className="h-3 bg-slate-100 rounded w-48 mb-3" />
          <div className="flex gap-2">
            <div className="h-8 bg-slate-200 rounded-full w-28" />
            <div className="h-8 bg-slate-200 rounded-full w-24" />
          </div>
        </div>
      ))}
      {/* Skeleton form */}
      <div className="pt-4 border-t border-slate-100 flex gap-2">
        <div className="h-9 bg-slate-200 rounded-md flex-1" />
        <div className="h-9 bg-slate-200 rounded-md w-32" />
        <div className="h-9 bg-slate-200 rounded-md w-20" />
      </div>
      <span className="sr-only">Loading language preferences…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single preference pill (language name + remove button)
// ---------------------------------------------------------------------------

interface PreferencePillProps {
  item: LanguagePreferenceItem;
  displayName: string;
  onRemove: (languageCode: string) => void;
  isRemoving: boolean;
  config: PreferenceTypeConfig;
}

function PreferencePill({
  item,
  displayName,
  onRemove,
  isRemoving,
  config,
}: PreferencePillProps) {
  return (
    <li>
      <div
        className={`inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 border rounded-full text-sm font-medium ${config.pillClasses}`}
      >
        {/* Language name + muted code */}
        <span>
          {displayName}{" "}
          <span className="opacity-60 font-normal">({item.language_code})</span>
        </span>

        {/* Remove button */}
        <button
          type="button"
          onClick={() => onRemove(item.language_code)}
          disabled={isRemoving}
          aria-label={`Remove ${displayName} (${item.language_code}) from ${config.label}`}
          className={`flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${config.badgeClasses}`}
        >
          {isRemoving ? (
            <SpinnerIcon className="w-3 h-3 animate-spin" />
          ) : (
            <XMarkIcon className="w-3.5 h-3.5" />
          )}
          <span className="sr-only">
            {isRemoving ? "Removing…" : `Remove ${displayName}`}
          </span>
        </button>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Preference type group (heading + pills)
// ---------------------------------------------------------------------------

interface PreferenceGroupProps {
  typeValue: PreferenceTypeValue;
  items: LanguagePreferenceItem[];
  supportedLanguages: SupportedLanguage[];
  onRemove: (languageCode: string) => void;
  isRemoving: boolean;
  headingId: string;
}

function PreferenceGroup({
  typeValue,
  items,
  supportedLanguages,
  onRemove,
  isRemoving,
  headingId,
}: PreferenceGroupProps) {
  const config = PREFERENCE_TYPE_CONFIG[typeValue];

  // Build a lookup map for fast display name resolution
  const langMap = new Map(supportedLanguages.map((l) => [l.code, l.display_name]));

  return (
    <div role="group" aria-labelledby={headingId} className="space-y-2">
      {/* Group heading + description */}
      <div>
        <h4
          id={headingId}
          className="text-sm font-semibold text-slate-800"
        >
          {config.label}
        </h4>
        <p className="text-xs text-slate-500 mt-0.5">{config.description}</p>
      </div>

      {/* Pills — ordered by priority (items already arrive sorted) */}
      {items.length > 0 ? (
        <ul className="flex flex-wrap gap-2" aria-label={`${config.label} languages`}>
          {items.map((item) => (
            <PreferencePill
              key={item.language_code}
              item={item}
              displayName={
                langMap.get(item.language_code) ?? item.language_code
              }
              onRemove={onRemove}
              isRemoving={isRemoving}
              config={config}
            />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-400 italic">
          No {config.label.toLowerCase()} languages configured.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state (when ALL preference groups are empty)
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="py-6 text-center">
      <p className="text-slate-500 text-sm mb-4">
        No language preferences configured yet. Use the form below to add
        languages and choose how transcripts should be downloaded for each.
      </p>
      <dl className="text-left max-w-md mx-auto space-y-2 text-sm">
        <div className="flex gap-2">
          <dt className="font-semibold text-emerald-700 shrink-0">Fluent:</dt>
          <dd className="text-slate-600">
            Always download transcripts in these languages
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-semibold text-blue-700 shrink-0">Learning:</dt>
          <dd className="text-slate-600">Download if available</dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-semibold text-violet-700 shrink-0">Curious:</dt>
          <dd className="text-slate-600">
            Never auto-download; available on-demand only via explicit language
            selection
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="font-semibold text-rose-700 shrink-0">Exclude:</dt>
          <dd className="text-slate-600">Never download</dd>
        </div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reset all confirmation dialog (inline, not a modal)
// ---------------------------------------------------------------------------

interface ResetConfirmationProps {
  isPending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function ResetConfirmation({
  isPending,
  onConfirm,
  onCancel,
}: ResetConfirmationProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  // WCAG 2.4.3: Focus the Confirm button on mount
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      role="alertdialog"
      aria-modal="false"
      aria-labelledby="reset-confirm-label"
      aria-describedby="reset-confirm-desc"
      className="flex flex-wrap items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 mt-4"
      onKeyDown={handleKeyDown}
    >
      <ExclamationTriangleIcon className="w-5 h-5 text-amber-600 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p id="reset-confirm-label" className="text-sm font-semibold text-amber-900">
          Remove all language preferences?
        </p>
        <p id="reset-confirm-desc" className="text-xs text-amber-700 mt-0.5">
          This will permanently remove all configured language preferences. This
          action cannot be undone.
        </p>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          ref={confirmRef}
          type="button"
          onClick={onConfirm}
          disabled={isPending}
          aria-busy={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 transition-colors"
        >
          {isPending && (
            <SpinnerIcon className="w-3.5 h-3.5 animate-spin" />
          )}
          {isPending ? "Resetting…" : "Yes, remove all"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:opacity-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add preference form (searchable language dropdown + type selector)
// ---------------------------------------------------------------------------

interface AddPreferenceFormProps {
  supportedLanguages: SupportedLanguage[];
  usedLanguageCodes: Set<string>;
  onAdd: (
    languageCode: string,
    preferenceType: string,
    learningGoal?: string | null
  ) => void;
  isMutating: boolean;
}

function AddPreferenceForm({
  supportedLanguages,
  usedLanguageCodes,
  onAdd,
  isMutating,
}: AddPreferenceFormProps) {
  const formId = useId();

  const [search, setSearch] = useState("");
  const [selectedCode, setSelectedCode] = useState("");
  const [preferenceType, setPreferenceType] =
    useState<PreferenceTypeValue>("fluent");
  const [learningGoal, setLearningGoal] = useState("");
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const [isListOpen, setIsListOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  // Alphabetically sorted languages filtered by search term
  const filteredLanguages: SupportedLanguage[] = [...supportedLanguages]
    .sort((a, b) => a.display_name.localeCompare(b.display_name))
    .filter((lang) => {
      const q = search.toLowerCase();
      return (
        lang.display_name.toLowerCase().includes(q) ||
        lang.code.toLowerCase().includes(q)
      );
    });

  // The display name for the currently selected code
  const selectedDisplayName =
    supportedLanguages.find((l) => l.code === selectedCode)?.display_name ?? "";

  function selectLanguage(lang: SupportedLanguage) {
    setSelectedCode(lang.code);
    setSearch(lang.display_name);
    setIsListOpen(false);
    setDuplicateError(null);
  }

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setSearch(value);
    setDuplicateError(null);

    // If user edits the text, clear the previously selected code unless
    // the text still exactly matches that language's display name.
    if (value !== selectedDisplayName) {
      setSelectedCode("");
    }

    setIsListOpen(true);
  }

  const handleSearchFocus = useCallback(() => {
    if (search) setIsListOpen(true);
  }, [search]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!isListOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (
        !inputRef.current?.parentElement?.contains(e.target as Node) &&
        !listboxRef.current?.contains(e.target as Node)
      ) {
        setIsListOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isListOpen]);

  function handleKeyDownOnInput(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setIsListOpen(false);
    } else if (e.key === "ArrowDown" && isListOpen) {
      e.preventDefault();
      const firstItem = listboxRef.current?.querySelector<HTMLElement>(
        "[role='option']"
      );
      firstItem?.focus();
    }
  }

  function handleKeyDownOnOption(
    e: React.KeyboardEvent<HTMLLIElement>,
    lang: SupportedLanguage,
    index: number
  ) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selectLanguage(lang);
      inputRef.current?.focus();
    } else if (e.key === "Escape") {
      setIsListOpen(false);
      inputRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const items = listboxRef.current?.querySelectorAll<HTMLElement>(
        "[role='option']"
      );
      if (items && index < items.length - 1) {
        items[index + 1]?.focus();
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (index === 0) {
        inputRef.current?.focus();
      } else {
        const items = listboxRef.current?.querySelectorAll<HTMLElement>(
          "[role='option']"
        );
        items?.[index - 1]?.focus();
      }
    }
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setDuplicateError(null);

    if (!selectedCode) return;

    try {
      onAdd(
        selectedCode,
        preferenceType,
        preferenceType === "learning" && learningGoal.trim()
          ? learningGoal.trim()
          : null
      );
      // Reset form on success
      setSearch("");
      setSelectedCode("");
      setLearningGoal("");
      inputRef.current?.focus();
    } catch (err) {
      if (err instanceof DuplicateLanguageError) {
        setDuplicateError(err.message);
      } else {
        throw err;
      }
    }
  }

  const isAlreadyUsed = selectedCode !== "" && usedLanguageCodes.has(selectedCode);
  const canSubmit =
    selectedCode !== "" && !isAlreadyUsed && !isMutating;

  const listboxId = `${formId}-listbox`;
  const languageInputId = `${formId}-language`;
  const typeSelectId = `${formId}-type`;
  const goalInputId = `${formId}-goal`;

  return (
    <div className="pt-4 mt-4 border-t border-slate-100">
      <h4 className="text-sm font-semibold text-slate-800 mb-3">
        Add Language Preference
      </h4>

      <form onSubmit={handleSubmit} noValidate aria-label="Add language preference">
        <div className="flex flex-wrap gap-3 items-start">

          {/* --- Language search combobox --- */}
          <div className="flex-1 min-w-[200px] relative">
            <label
              htmlFor={languageInputId}
              className="block text-xs font-medium text-slate-600 mb-1"
            >
              Language
            </label>
            <input
              ref={inputRef}
              id={languageInputId}
              type="text"
              role="combobox"
              autoComplete="off"
              aria-autocomplete="list"
              aria-controls={listboxId}
              aria-expanded={isListOpen && filteredLanguages.length > 0}
              aria-haspopup="listbox"
              aria-label="Search and select a language"
              value={search}
              onChange={handleSearchChange}
              onFocus={handleSearchFocus}
              onKeyDown={handleKeyDownOnInput}
              placeholder="Search language…"
              disabled={isMutating}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
            />

            {/* Dropdown listbox */}
            {isListOpen && filteredLanguages.length > 0 && (
              <ul
                id={listboxId}
                ref={listboxRef}
                role="listbox"
                aria-label="Available languages"
                className="absolute z-20 mt-1 w-full max-h-52 overflow-y-auto bg-white border border-slate-200 rounded-md shadow-lg py-1 text-sm"
              >
                {filteredLanguages.map((lang, index) => {
                  const isUsed = usedLanguageCodes.has(lang.code);
                  const isSelected = lang.code === selectedCode;
                  return (
                    <li
                      key={lang.code}
                      role="option"
                      aria-selected={isSelected}
                      aria-disabled={isUsed}
                      tabIndex={isUsed ? -1 : 0}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        if (!isUsed) selectLanguage(lang);
                      }}
                      onKeyDown={(e) => {
                        if (!isUsed) handleKeyDownOnOption(e, lang, index);
                      }}
                      className={`flex items-center justify-between px-3 py-1.5 cursor-pointer ${
                        isUsed
                          ? "text-slate-400 cursor-default"
                          : isSelected
                          ? "bg-indigo-50 text-indigo-900"
                          : "text-slate-800 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                      }`}
                    >
                      <span>
                        {lang.display_name}{" "}
                        <span className="text-slate-400">({lang.code})</span>
                      </span>
                      {isUsed && (
                        <span className="text-xs text-slate-400 ml-2">
                          already added
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* --- Preference type selector --- */}
          <div className="flex-1 min-w-[140px]">
            <label
              htmlFor={typeSelectId}
              className="block text-xs font-medium text-slate-600 mb-1"
            >
              Type
            </label>
            <select
              id={typeSelectId}
              value={preferenceType}
              onChange={(e) =>
                setPreferenceType(e.target.value as PreferenceTypeValue)
              }
              disabled={isMutating}
              aria-label="Preference type"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
            >
              {PREFERENCE_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          {/* --- Add button --- */}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!canSubmit}
              aria-label={
                selectedCode
                  ? `Add ${selectedDisplayName || selectedCode} as ${preferenceType}`
                  : "Add language preference (select a language first)"
              }
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 transition-colors"
            >
              {isMutating && (
                <SpinnerIcon className="w-3.5 h-3.5 animate-spin" />
              )}
              {isMutating ? "Adding…" : "Add"}
            </button>
          </div>
        </div>

        {/* --- Learning goal input (only when type = learning) --- */}
        {preferenceType === "learning" && (
          <div className="mt-3">
            <label
              htmlFor={goalInputId}
              className="block text-xs font-medium text-slate-600 mb-1"
            >
              Learning goal{" "}
              <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id={goalInputId}
              type="text"
              value={learningGoal}
              onChange={(e) => setLearningGoal(e.target.value)}
              placeholder="e.g. JLPT N3 goal, travel Spanish, …"
              maxLength={300}
              disabled={isMutating}
              className="w-full max-w-md rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
        )}

        {/* --- Inline duplicate error (FR-009) --- */}
        {duplicateError !== null && (
          <p role="alert" className="mt-2 text-sm text-rose-600">
            {duplicateError}
          </p>
        )}

        {/* --- Inline "already added" hint --- */}
        {isAlreadyUsed && !duplicateError && (
          <p role="status" className="mt-2 text-sm text-amber-700">
            This language is already in your preferences. Remove it from its
            current group first.
          </p>
        )}
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * LanguagePreferencesSection renders the language preferences card within
 * the Settings page. It is fully self-contained — all data and mutations come
 * from the `useLanguagePreferences` hook.
 *
 * @example
 * ```tsx
 * <LanguagePreferencesSection />
 * ```
 */
export function LanguagePreferencesSection() {
  const {
    preferences,
    supportedLanguages,
    isLoading,
    error,
    addPreference,
    removePreference,
    resetAll,
    isMutating,
  } = useLanguagePreferences();

  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // Ref to the "Reset All" button so focus can be restored after the
  // confirmation dialog is dismissed (WCAG 2.4.3).
  const resetButtonRef = useRef<HTMLButtonElement>(null);

  // aria-live announcement for preference changes (FR-029)
  const [announcement, setAnnouncement] = useState("");

  // Announce after isMutating transitions from true → false
  const wasMutatingRef = useRef(false);
  useEffect(() => {
    if (wasMutatingRef.current && !isMutating) {
      setAnnouncement("Language preferences updated.");
      const t = setTimeout(() => setAnnouncement(""), 3000);
      return () => clearTimeout(t);
    }
    wasMutatingRef.current = isMutating;
  }, [isMutating]);

  // Group preferences by type, preserving priority order
  const grouped = {
    fluent: preferences
      .filter((p) => p.preference_type === "fluent")
      .sort((a, b) => a.priority - b.priority),
    learning: preferences
      .filter((p) => p.preference_type === "learning")
      .sort((a, b) => a.priority - b.priority),
    curious: preferences
      .filter((p) => p.preference_type === "curious")
      .sort((a, b) => a.priority - b.priority),
    exclude: preferences
      .filter((p) => p.preference_type === "exclude")
      .sort((a, b) => a.priority - b.priority),
  };

  const hasAnyPreferences = preferences.length > 0;
  const usedLanguageCodes = new Set(preferences.map((p) => p.language_code));

  // Stable heading IDs for aria-labelledby on each group
  const headingIdPrefix = useId();
  const headingIds: Record<PreferenceTypeValue, string> = {
    fluent: `${headingIdPrefix}-fluent`,
    learning: `${headingIdPrefix}-learning`,
    curious: `${headingIdPrefix}-curious`,
    exclude: `${headingIdPrefix}-exclude`,
  };

  function handleRemove(languageCode: string) {
    removePreference(languageCode);
  }

  function handleResetConfirm() {
    resetAll();
    setShowResetConfirm(false);
    // Focus is lost when the dialog unmounts; return it to the page heading
    // since the "Reset All" button is no longer rendered after a successful reset.
  }

  function handleResetCancel() {
    setShowResetConfirm(false);
    // WCAG 2.4.3: Return focus to the button that opened the confirmation.
    resetButtonRef.current?.focus();
  }

  return (
    <section aria-labelledby="language-preferences-heading">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        {/* ---------------------------------------------------------------- */}
        {/* Section header                                                   */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h3
              id="language-preferences-heading"
              className="text-lg font-semibold text-slate-900"
            >
              Language Preferences
            </h3>
            <p className="text-sm text-slate-500 mt-1">
              Control which languages ChronoVista downloads transcripts for and
              how they are prioritised.
            </p>
          </div>

          {/* Reset All — only visible when preferences exist (FR-006) */}
          {hasAnyPreferences && !showResetConfirm && (
            <button
              ref={resetButtonRef}
              type="button"
              onClick={() => setShowResetConfirm(true)}
              aria-label="Reset all language preferences"
              disabled={isMutating}
              className="flex-shrink-0 text-sm font-medium text-rose-600 hover:text-rose-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Reset All
            </button>
          )}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* aria-live region for preference change announcements (FR-029)   */}
        {/* ---------------------------------------------------------------- */}
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {announcement}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Loading state (FR-021)                                           */}
        {/* ---------------------------------------------------------------- */}
        {isLoading && <LanguagePreferencesSkeleton />}

        {/* ---------------------------------------------------------------- */}
        {/* Error state (FR-022)                                             */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error !== null && (
          <div
            role="alert"
            className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3"
          >
            <ExclamationTriangleIcon className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-rose-800">
                Failed to load language preferences
              </p>
              <p className="text-xs text-rose-700 mt-1">{error.message}</p>
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="flex-shrink-0 text-sm font-medium text-rose-700 hover:text-rose-900 underline focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Main content (once loaded and no error)                         */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error === null && (
          <>
            {/* Empty state (FR-010) */}
            {!hasAnyPreferences && <EmptyState />}

            {/* Grouped preferences (FR-002, FR-007, FR-008, FR-024) */}
            {hasAnyPreferences && (
              <div className="space-y-6">
                {PREFERENCE_TYPES.map((type) => (
                  <PreferenceGroup
                    key={type.value}
                    typeValue={type.value}
                    items={grouped[type.value]}
                    supportedLanguages={supportedLanguages}
                    onRemove={handleRemove}
                    isRemoving={isMutating}
                    headingId={headingIds[type.value]}
                  />
                ))}
              </div>
            )}

            {/* Reset All confirmation (FR-006) */}
            {showResetConfirm && (
              <ResetConfirmation
                isPending={isMutating}
                onConfirm={handleResetConfirm}
                onCancel={handleResetCancel}
              />
            )}

            {/* Add preference form (FR-023, FR-009) */}
            <AddPreferenceForm
              supportedLanguages={supportedLanguages}
              usedLanguageCodes={usedLanguageCodes}
              onAdd={addPreference}
              isMutating={isMutating}
            />
          </>
        )}
      </div>
    </section>
  );
}
