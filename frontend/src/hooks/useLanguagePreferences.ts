/**
 * useLanguagePreferences hook for managing language preferences in settings.
 *
 * Implements:
 * - GET /api/v1/preferences/languages — current user preferences
 * - GET /api/v1/settings/supported-languages — all available languages (static)
 * - PUT /api/v1/preferences/languages — replace-all semantics for updates
 * - FR-009: Duplicate validation before adding a language
 *
 * Priority numbering is maintained locally:
 * - On add: new item receives next sequential priority within its type group
 * - On remove: remaining items are re-numbered 1..N within each type group
 * - On resetAll: empty list replaces all preferences
 *
 * @module hooks/useLanguagePreferences
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../api/config";
import {
  fetchSupportedLanguages,
  type SupportedLanguage,
} from "../api/settings";

// ---------------------------------------------------------------------------
// Query key constants
// ---------------------------------------------------------------------------

export const LANGUAGE_PREFERENCES_KEY = ["language-preferences"] as const;
export const SUPPORTED_LANGUAGES_KEY = ["supported-languages"] as const;

// ---------------------------------------------------------------------------
// Types matching backend schemas (preferences.py)
// ---------------------------------------------------------------------------

export interface LanguagePreferenceItem {
  /** BCP-47 language code (e.g. "en", "es", "ja") */
  language_code: string;
  /** One of: "fluent", "learning", "curious", "exclude" */
  preference_type: string;
  /** 1 = highest priority within the preference type group */
  priority: number;
  /** Goal text for the "learning" type; null otherwise */
  learning_goal: string | null;
}

export interface LanguagePreferencesResponse {
  data: LanguagePreferenceItem[];
  pagination: null;
}

export interface LanguagePreferenceUpdate {
  language_code: string;
  preference_type: string;
  /** Omit to let the backend auto-assign within its group */
  priority?: number;
  learning_goal?: string | null;
}

export interface LanguagePreferencesUpdateRequest {
  preferences: LanguagePreferenceUpdate[];
}

// ---------------------------------------------------------------------------
// Error type for duplicate validation (FR-009)
// ---------------------------------------------------------------------------

export class DuplicateLanguageError extends Error {
  readonly languageCode: string;
  readonly existingType: string;

  constructor(languageCode: string, existingType: string) {
    super(
      `Language "${languageCode}" is already configured as "${existingType}". ` +
        `Remove it from that group before adding it here.`
    );
    this.name = "DuplicateLanguageError";
    this.languageCode = languageCode;
    this.existingType = existingType;
  }
}

// ---------------------------------------------------------------------------
// Public hook return type
// ---------------------------------------------------------------------------

export interface UseLanguagePreferencesReturn {
  /** Current language preferences, ordered by priority. */
  preferences: LanguagePreferenceItem[];
  /** Full list of all language codes supported by the backend. */
  supportedLanguages: SupportedLanguage[];
  /** True while either query is fetching for the first time. */
  isLoading: boolean;
  /** First error from either query, or null. */
  error: Error | null;
  /**
   * Add a language preference.
   *
   * Throws DuplicateLanguageError (FR-009) if the language code already
   * exists in any preference type group.
   *
   * @param languageCode - BCP-47 code
   * @param preferenceType - "fluent" | "learning" | "curious" | "exclude"
   * @param learningGoal - Optional goal text (only relevant for "learning")
   */
  addPreference: (
    languageCode: string,
    preferenceType: string,
    learningGoal?: string | null
  ) => void;
  /**
   * Remove a language preference by its language code.
   * Re-numbers priorities within each type group after removal.
   */
  removePreference: (languageCode: string) => void;
  /** Replace all preferences with an empty list. */
  resetAll: () => void;
  /** True while a PUT mutation is in flight. */
  isMutating: boolean;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchLanguagePreferences(
  signal?: AbortSignal
): Promise<LanguagePreferencesResponse> {
  return apiFetch<LanguagePreferencesResponse>("/preferences/languages", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

async function putLanguagePreferences(
  body: LanguagePreferencesUpdateRequest
): Promise<LanguagePreferencesResponse> {
  return apiFetch<LanguagePreferencesResponse>("/preferences/languages", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Priority renumbering helper
// ---------------------------------------------------------------------------

/**
 * Re-numbers priorities 1..N within each preference_type group.
 * The relative order of items is preserved; only their priority numbers
 * are normalised to be contiguous starting from 1.
 */
function renumberPriorities(
  items: LanguagePreferenceItem[]
): LanguagePreferenceItem[] {
  // Group items by preference_type while preserving insertion order
  const byType = new Map<string, LanguagePreferenceItem[]>();
  for (const item of items) {
    const group = byType.get(item.preference_type);
    if (group !== undefined) {
      group.push(item);
    } else {
      byType.set(item.preference_type, [item]);
    }
  }

  const result: LanguagePreferenceItem[] = [];
  for (const group of byType.values()) {
    // Sort within type by existing priority so relative order is stable
    const sorted = [...group].sort((a, b) => a.priority - b.priority);
    sorted.forEach((item, index) => {
      result.push({ ...item, priority: index + 1 });
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Manages language preferences with TanStack Query for caching and mutation.
 *
 * @example
 * ```tsx
 * const {
 *   preferences,
 *   supportedLanguages,
 *   isLoading,
 *   error,
 *   addPreference,
 *   removePreference,
 *   resetAll,
 *   isMutating,
 * } = useLanguagePreferences();
 *
 * // Add a new preference
 * try {
 *   addPreference("ja", "learning", "JLPT N3 goal");
 * } catch (e) {
 *   if (e instanceof DuplicateLanguageError) {
 *     showError(e.message);
 *   }
 * }
 *
 * // Remove by language code
 * removePreference("en");
 *
 * // Reset everything
 * resetAll();
 * ```
 */
export function useLanguagePreferences(): UseLanguagePreferencesReturn {
  const queryClient = useQueryClient();

  // ------------------------------------------------------------------
  // Query: current preferences
  // ------------------------------------------------------------------
  const preferencesQuery = useQuery<LanguagePreferencesResponse, Error>({
    queryKey: LANGUAGE_PREFERENCES_KEY,
    queryFn: ({ signal }) => fetchLanguagePreferences(signal),
    staleTime: 60 * 1000, // 1 minute — preferences change infrequently
  });

  // ------------------------------------------------------------------
  // Query: supported languages (static, cache forever during the session)
  // ------------------------------------------------------------------
  const supportedLanguagesQuery = useQuery({
    queryKey: SUPPORTED_LANGUAGES_KEY,
    queryFn: ({ signal }) => fetchSupportedLanguages(signal),
    staleTime: Infinity,
    gcTime: Infinity,
  });

  // ------------------------------------------------------------------
  // Mutation: replace-all PUT
  // ------------------------------------------------------------------
  const mutation = useMutation<
    LanguagePreferencesResponse,
    Error,
    LanguagePreferencesUpdateRequest
  >({
    mutationFn: (body) => putLanguagePreferences(body),
    onSuccess: () => {
      // Invalidate so the GET query re-fetches with the server's canonical data
      queryClient.invalidateQueries({ queryKey: LANGUAGE_PREFERENCES_KEY });
    },
  });

  // ------------------------------------------------------------------
  // Derived state
  // ------------------------------------------------------------------
  const preferences = preferencesQuery.data?.data ?? [];
  const supportedLanguages = supportedLanguagesQuery.data?.data ?? [];

  const isLoading =
    preferencesQuery.isLoading || supportedLanguagesQuery.isLoading;

  const error: Error | null =
    (preferencesQuery.error as Error | null) ??
    (supportedLanguagesQuery.error as Error | null);

  // ------------------------------------------------------------------
  // Helper: addPreference
  // ------------------------------------------------------------------
  function addPreference(
    languageCode: string,
    preferenceType: string,
    learningGoal?: string | null
  ): void {
    // FR-009: Reject if the language already exists in any preference type
    const existing = preferences.find(
      (p) => p.language_code === languageCode
    );
    if (existing !== undefined) {
      throw new DuplicateLanguageError(languageCode, existing.preference_type);
    }

    // Compute the next priority within the target type group
    const existingInType = preferences.filter(
      (p) => p.preference_type === preferenceType
    );
    const nextPriority = existingInType.length + 1;

    const newItem: LanguagePreferenceUpdate = {
      language_code: languageCode,
      preference_type: preferenceType,
      priority: nextPriority,
      learning_goal: learningGoal ?? null,
    };

    // Build the updated full list (keep existing items + new one)
    const updated: LanguagePreferenceUpdate[] = [
      ...preferences.map((p) => ({
        language_code: p.language_code,
        preference_type: p.preference_type,
        priority: p.priority,
        learning_goal: p.learning_goal ?? null,
      })),
      newItem,
    ];

    mutation.mutate({ preferences: updated });
  }

  // ------------------------------------------------------------------
  // Helper: removePreference
  // ------------------------------------------------------------------
  function removePreference(languageCode: string): void {
    const filtered = preferences.filter(
      (p) => p.language_code !== languageCode
    );

    // Re-number priorities so they remain contiguous within each type group
    const renumbered = renumberPriorities(filtered);

    const updated: LanguagePreferenceUpdate[] = renumbered.map((p) => ({
      language_code: p.language_code,
      preference_type: p.preference_type,
      priority: p.priority,
      learning_goal: p.learning_goal ?? null,
    }));

    mutation.mutate({ preferences: updated });
  }

  // ------------------------------------------------------------------
  // Helper: resetAll
  // ------------------------------------------------------------------
  function resetAll(): void {
    mutation.mutate({ preferences: [] });
  }

  return {
    preferences,
    supportedLanguages,
    isLoading,
    error,
    addPreference,
    removePreference,
    resetAll,
    isMutating: mutation.isPending,
  };
}
