/**
 * Tests for useLanguagePreferences hook.
 *
 * Coverage:
 * - Initial loading state while both queries are fetching
 * - Successful fetch of preferences and supported languages
 * - addPreference() — calls PUT with full list including new item and correct priority
 * - addPreference() with DuplicateLanguageError (FR-009)
 * - removePreference() — filters out language and renumbers priorities within groups
 * - resetAll() — calls PUT with empty preferences list
 * - isMutating state transitions during mutation lifecycle
 * - Error propagation from preferences query
 * - Error propagation from supported-languages query
 * - Mutation success invalidates the LANGUAGE_PREFERENCES_KEY query
 * - Priority renumbering: removing middle item compacts remaining priorities
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock apiFetch and fetchSupportedLanguages before the hook import
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

vi.mock("../../api/settings", () => ({
  fetchSupportedLanguages: vi.fn(),
}));

import { apiFetch } from "../../api/config";
import { fetchSupportedLanguages } from "../../api/settings";
import {
  useLanguagePreferences,
  DuplicateLanguageError,
  LANGUAGE_PREFERENCES_KEY,
} from "../useLanguagePreferences";
import type { LanguagePreferencesResponse } from "../useLanguagePreferences";
import type { SupportedLanguage } from "../../api/settings";

const mockedApiFetch = vi.mocked(apiFetch);
const mockedFetchSupportedLanguages = vi.mocked(fetchSupportedLanguages);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePreferencesResponse(
  items: LanguagePreferencesResponse["data"] = []
): LanguagePreferencesResponse {
  return { data: items, pagination: null };
}

function makeSupportedLanguagesResponse(
  languages: SupportedLanguage[] = []
): { data: SupportedLanguage[]; pagination: null } {
  return { data: languages, pagination: null };
}

const DEFAULT_SUPPORTED_LANGUAGES: SupportedLanguage[] = [
  { code: "en", display_name: "English" },
  { code: "es", display_name: "Spanish" },
  { code: "fr", display_name: "French" },
  { code: "ja", display_name: "Japanese" },
];

// ---------------------------------------------------------------------------
// Wrapper & QueryClient helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useLanguagePreferences", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();

    // Default: both queries resolve successfully with empty data
    mockedApiFetch.mockResolvedValue(makePreferencesResponse());
    mockedFetchSupportedLanguages.mockResolvedValue(
      makeSupportedLanguagesResponse(DEFAULT_SUPPORTED_LANGUAGES)
    );
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("returns isLoading=true while queries are pending", () => {
    // Keep queries pending indefinitely
    mockedApiFetch.mockReturnValue(new Promise(() => {}));
    mockedFetchSupportedLanguages.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.preferences).toEqual([]);
    expect(result.current.supportedLanguages).toEqual([]);
  });

  it("returns isLoading=false once both queries have resolved", async () => {
    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  // -------------------------------------------------------------------------
  // Successful data fetch
  // -------------------------------------------------------------------------

  it("exposes preferences from the GET /preferences/languages response", async () => {
    const prefs = [
      {
        language_code: "en",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
      {
        language_code: "ja",
        preference_type: "learning",
        priority: 1,
        learning_goal: "JLPT N3",
      },
    ];
    mockedApiFetch.mockResolvedValue(makePreferencesResponse(prefs));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toEqual(prefs);
  });

  it("exposes supportedLanguages from fetchSupportedLanguages", async () => {
    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.supportedLanguages).toEqual(DEFAULT_SUPPORTED_LANGUAGES);
  });

  // -------------------------------------------------------------------------
  // addPreference
  // -------------------------------------------------------------------------

  it("addPreference() fires PUT with existing items plus new item at next priority", async () => {
    const existingPrefs = [
      {
        language_code: "en",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
    ];
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs))
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs)); // after mutation invalidate

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.addPreference("es", "fluent");
    });

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/preferences/languages",
        expect.objectContaining({ method: "PUT" })
      )
    );

    const putCall = mockedApiFetch.mock.calls.find(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    expect(putCall).toBeDefined();
    const body = JSON.parse((putCall![1] as { body: string }).body);
    expect(body.preferences).toContainEqual(
      expect.objectContaining({
        language_code: "es",
        preference_type: "fluent",
        priority: 2, // next after existing fluent priority=1
      })
    );
    // Original item is preserved
    expect(body.preferences).toContainEqual(
      expect.objectContaining({ language_code: "en", preference_type: "fluent" })
    );
  });

  it("addPreference() assigns priority=1 when the type group is empty", async () => {
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse([]))
      .mockResolvedValueOnce(makePreferencesResponse([]));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.addPreference("ja", "learning", "JLPT N3");
    });

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/preferences/languages",
        expect.objectContaining({ method: "PUT" })
      )
    );

    const putCall = mockedApiFetch.mock.calls.find(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    const body = JSON.parse((putCall![1] as { body: string }).body);
    expect(body.preferences).toContainEqual(
      expect.objectContaining({
        language_code: "ja",
        preference_type: "learning",
        priority: 1,
        learning_goal: "JLPT N3",
      })
    );
  });

  it("addPreference() throws DuplicateLanguageError (FR-009) when language already exists", async () => {
    const existingPrefs = [
      {
        language_code: "fr",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
    ];
    mockedApiFetch.mockResolvedValueOnce(makePreferencesResponse(existingPrefs));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let thrown: unknown = null;
    act(() => {
      try {
        result.current.addPreference("fr", "learning");
      } catch (e) {
        thrown = e;
      }
    });

    expect(thrown).toBeInstanceOf(DuplicateLanguageError);
    expect((thrown as DuplicateLanguageError).languageCode).toBe("fr");
    expect((thrown as DuplicateLanguageError).existingType).toBe("fluent");
    // No PUT should have been fired
    const putCalls = mockedApiFetch.mock.calls.filter(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    expect(putCalls).toHaveLength(0);
  });

  it("DuplicateLanguageError contains a human-readable message", async () => {
    const existingPrefs = [
      {
        language_code: "es",
        preference_type: "curious",
        priority: 1,
        learning_goal: null,
      },
    ];
    mockedApiFetch.mockResolvedValueOnce(makePreferencesResponse(existingPrefs));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let err: DuplicateLanguageError | undefined;
    act(() => {
      try {
        result.current.addPreference("es", "fluent");
      } catch (e) {
        if (e instanceof DuplicateLanguageError) err = e;
      }
    });

    expect(err?.message).toContain("es");
    expect(err?.message).toContain("curious");
  });

  // -------------------------------------------------------------------------
  // removePreference
  // -------------------------------------------------------------------------

  it("removePreference() fires PUT without the removed language", async () => {
    const existingPrefs = [
      {
        language_code: "en",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
      {
        language_code: "es",
        preference_type: "fluent",
        priority: 2,
        learning_goal: null,
      },
    ];
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs))
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.removePreference("en");
    });

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/preferences/languages",
        expect.objectContaining({ method: "PUT" })
      )
    );

    const putCall = mockedApiFetch.mock.calls.find(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    const body = JSON.parse((putCall![1] as { body: string }).body);
    const codes = body.preferences.map(
      (p: { language_code: string }) => p.language_code
    );
    expect(codes).not.toContain("en");
    expect(codes).toContain("es");
  });

  it("removePreference() renumbers priorities after removal", async () => {
    const existingPrefs = [
      {
        language_code: "es",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
      {
        language_code: "fr",
        preference_type: "fluent",
        priority: 2,
        learning_goal: null,
      },
      {
        language_code: "ja",
        preference_type: "fluent",
        priority: 3,
        learning_goal: null,
      },
    ];
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs))
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.removePreference("fr"); // remove middle item
    });

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/preferences/languages",
        expect.objectContaining({ method: "PUT" })
      )
    );

    const putCall = mockedApiFetch.mock.calls.find(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    const body = JSON.parse((putCall![1] as { body: string }).body);

    // After removing fr(2), es should be 1 and ja should be 2
    const esItem = body.preferences.find(
      (p: { language_code: string }) => p.language_code === "es"
    );
    const jaItem = body.preferences.find(
      (p: { language_code: string }) => p.language_code === "ja"
    );
    expect(esItem?.priority).toBe(1);
    expect(jaItem?.priority).toBe(2);
  });

  // -------------------------------------------------------------------------
  // resetAll
  // -------------------------------------------------------------------------

  it("resetAll() fires PUT with an empty preferences list", async () => {
    const existingPrefs = [
      {
        language_code: "en",
        preference_type: "fluent",
        priority: 1,
        learning_goal: null,
      },
    ];
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse(existingPrefs))
      .mockResolvedValueOnce(makePreferencesResponse([]));

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.resetAll();
    });

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/preferences/languages",
        expect.objectContaining({ method: "PUT" })
      )
    );

    const putCall = mockedApiFetch.mock.calls.find(
      (c) => c[1] && (c[1] as { method?: string }).method === "PUT"
    );
    const body = JSON.parse((putCall![1] as { body: string }).body);
    expect(body.preferences).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // isMutating
  // -------------------------------------------------------------------------

  it("isMutating is true while the PUT is in flight and false when settled", async () => {
    let resolveMutation!: (value: unknown) => void;
    const pendingMutation = new Promise((resolve) => {
      resolveMutation = resolve;
    });

    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse([]))
      .mockReturnValueOnce(pendingMutation as Promise<LanguagePreferencesResponse>);

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isMutating).toBe(false);

    act(() => {
      result.current.resetAll();
    });

    await waitFor(() => expect(result.current.isMutating).toBe(true));

    // Resolve and verify isMutating returns to false
    resolveMutation(makePreferencesResponse([]));
    await waitFor(() => expect(result.current.isMutating).toBe(false));
  });

  // -------------------------------------------------------------------------
  // Error propagation
  // -------------------------------------------------------------------------

  it("returns error from the preferences query", async () => {
    const apiError = new Error("Network failure");
    mockedApiFetch.mockRejectedValue(apiError);
    mockedFetchSupportedLanguages.mockResolvedValue(
      makeSupportedLanguagesResponse([])
    );

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("Network failure");
  });

  it("returns error from the supported-languages query", async () => {
    mockedApiFetch.mockResolvedValue(makePreferencesResponse([]));
    mockedFetchSupportedLanguages.mockRejectedValue(
      new Error("Languages endpoint down")
    );

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("Languages endpoint down");
  });

  // -------------------------------------------------------------------------
  // Cache invalidation on success
  // -------------------------------------------------------------------------

  it("mutation success calls invalidateQueries on LANGUAGE_PREFERENCES_KEY", async () => {
    mockedApiFetch
      .mockResolvedValueOnce(makePreferencesResponse([]))
      .mockResolvedValueOnce(makePreferencesResponse([]));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useLanguagePreferences(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.resetAll();
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: LANGUAGE_PREFERENCES_KEY })
      )
    );

    invalidateSpy.mockRestore();
  });
});
