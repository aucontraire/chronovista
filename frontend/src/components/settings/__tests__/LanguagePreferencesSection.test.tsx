/**
 * Tests for LanguagePreferencesSection component.
 *
 * Coverage:
 * - Loading skeleton shown when isLoading=true
 * - Error state shows alert with error message and Retry button
 * - Empty state shows preference type explanations (Fluent, Learning, Curious, Exclude)
 * - Preferences grouped by type with correct headings
 * - Language pills show display name with code in parentheses
 * - Remove button on each pill has a correct aria-label
 * - "Reset All" button only appears when preferences exist
 * - Clicking "Reset All" shows confirmation alertdialog
 * - Confirmation warns about permanently removing all preferences
 * - Confirming calls resetAll()
 * - Canceling hides the confirmation dialog
 * - Escape closes the confirmation dialog
 * - Add form has searchable language combobox
 * - Preference type selector has 4 options (Fluent, Learning, Curious, Exclude)
 * - Learning goal input only visible when type is "learning"
 * - aria-live region for preference change announcements
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../../hooks/useLanguagePreferences", () => ({
  useLanguagePreferences: vi.fn(),
  DuplicateLanguageError: class DuplicateLanguageError extends Error {
    languageCode: string;
    existingType: string;
    constructor(code: string, type: string) {
      super(`Language "${code}" already in "${type}"`);
      this.name = "DuplicateLanguageError";
      this.languageCode = code;
      this.existingType = type;
    }
  },
}));

import { useLanguagePreferences } from "../../../hooks/useLanguagePreferences";
import { LanguagePreferencesSection } from "../LanguagePreferencesSection";
import type { UseLanguagePreferencesReturn } from "../../../hooks/useLanguagePreferences";
import type { SupportedLanguage } from "../../../api/settings";

const mockedUseLanguagePreferences = vi.mocked(useLanguagePreferences);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUPPORTED_LANGUAGES: SupportedLanguage[] = [
  { code: "en", display_name: "English" },
  { code: "es", display_name: "Spanish" },
  { code: "fr", display_name: "French" },
  { code: "ja", display_name: "Japanese" },
];

function buildHookReturn(
  overrides: Partial<UseLanguagePreferencesReturn> = {}
): UseLanguagePreferencesReturn {
  return {
    preferences: [],
    supportedLanguages: SUPPORTED_LANGUAGES,
    isLoading: false,
    error: null,
    addPreference: vi.fn(),
    removePreference: vi.fn(),
    resetAll: vi.fn(),
    isMutating: false,
    ...overrides,
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderComponent(
  hookReturn: Partial<UseLanguagePreferencesReturn> = {}
) {
  mockedUseLanguagePreferences.mockReturnValue(buildHookReturn(hookReturn));
  const queryClient = createQueryClient();
  render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(LanguagePreferencesSection)
    )
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LanguagePreferencesSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("shows loading skeleton with role=status when isLoading=true", () => {
    renderComponent({ isLoading: true });
    const skeleton = screen.getByRole("status", {
      name: "Loading language preferences",
    });
    expect(skeleton).toBeDefined();
  });

  it("does not show the add form while loading", () => {
    renderComponent({ isLoading: true });
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error alert with the error message", () => {
    renderComponent({ error: new Error("Preferences endpoint failed") });
    const alert = screen.getByRole("alert");
    expect(
      within(alert).getByText("Preferences endpoint failed")
    ).toBeDefined();
  });

  it("shows a Retry button in the error state", () => {
    renderComponent({ error: new Error("Timeout") });
    expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  it("shows empty state description when preferences is empty", () => {
    renderComponent({ preferences: [] });
    expect(
      screen.getByText(/No language preferences configured yet/i)
    ).toBeDefined();
  });

  it("shows Fluent description in the empty state", () => {
    renderComponent({ preferences: [] });
    expect(
      screen.getByText(/Always download transcripts in these languages/i)
    ).toBeDefined();
  });

  it("shows Learning description in the empty state", () => {
    renderComponent({ preferences: [] });
    expect(screen.getByText(/Download if available/i)).toBeDefined();
  });

  it("shows Curious description in the empty state", () => {
    renderComponent({ preferences: [] });
    expect(screen.getByText(/Never auto-download/i)).toBeDefined();
  });

  it("shows Exclude description in the empty state", () => {
    renderComponent({ preferences: [] });
    expect(screen.getByText(/Never download/i)).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Grouped preferences
  // -------------------------------------------------------------------------

  it("shows language pill with display name and code in parentheses", () => {
    renderComponent({
      preferences: [
        {
          language_code: "es",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    // "Spanish" appears in both the visible pill span and an sr-only span;
    // use getAllByText to confirm at least one visible match
    expect(screen.getAllByText(/Spanish/i).length).toBeGreaterThanOrEqual(1);
    // The language code is rendered in parentheses within the pill
    expect(screen.getAllByText("(es)").length).toBeGreaterThanOrEqual(1);
  });

  it("shows remove button with correct aria-label on a pill", () => {
    renderComponent({
      preferences: [
        {
          language_code: "es",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    expect(
      screen.getByRole("button", {
        name: /Remove Spanish \(es\) from Fluent/i,
      })
    ).toBeDefined();
  });

  it("clicking remove button calls removePreference with the language code", () => {
    const removePreference = vi.fn();
    renderComponent({
      preferences: [
        {
          language_code: "es",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
      removePreference,
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: /Remove Spanish \(es\) from Fluent/i,
      })
    );
    expect(removePreference).toHaveBeenCalledWith("es");
  });

  it("shows the Fluent group heading", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    // The group heading for Fluent is an h4
    const fluent = screen.getAllByText("Fluent")[0];
    expect(fluent).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Reset All
  // -------------------------------------------------------------------------

  it("does not show Reset All button when preferences is empty", () => {
    renderComponent({ preferences: [] });
    expect(
      screen.queryByRole("button", { name: /reset all/i })
    ).toBeNull();
  });

  it("shows Reset All button when preferences exist", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    expect(
      screen.getByRole("button", { name: /reset all language preferences/i })
    ).toBeDefined();
  });

  it("clicking Reset All shows confirmation alertdialog", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    fireEvent.click(
      screen.getByRole("button", { name: /reset all language preferences/i })
    );
    expect(screen.getByRole("alertdialog")).toBeDefined();
  });

  it("confirmation dialog warns about permanently removing all preferences", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    fireEvent.click(
      screen.getByRole("button", { name: /reset all language preferences/i })
    );
    expect(
      screen.getByText(
        /This will permanently remove all configured language preferences/i
      )
    ).toBeDefined();
  });

  it("confirming reset calls resetAll()", () => {
    const resetAll = vi.fn();
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
      resetAll,
    });
    fireEvent.click(
      screen.getByRole("button", { name: /reset all language preferences/i })
    );
    fireEvent.click(screen.getByText(/Yes, remove all/i));
    expect(resetAll).toHaveBeenCalledTimes(1);
  });

  it("canceling the reset confirmation hides the dialog", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    fireEvent.click(
      screen.getByRole("button", { name: /reset all language preferences/i })
    );
    expect(screen.getByRole("alertdialog")).toBeDefined();
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("pressing Escape closes the reset confirmation dialog", () => {
    renderComponent({
      preferences: [
        {
          language_code: "en",
          preference_type: "fluent",
          priority: 1,
          learning_goal: null,
        },
      ],
    });
    fireEvent.click(
      screen.getByRole("button", { name: /reset all language preferences/i })
    );
    const dialog = screen.getByRole("alertdialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Add preference form
  // -------------------------------------------------------------------------

  it("renders a combobox input for language search", () => {
    renderComponent({ preferences: [] });
    const combobox = screen.getByRole("combobox", {
      name: /Search and select a language/i,
    });
    expect(combobox).toBeDefined();
  });

  it("renders a preference type select with 4 options", () => {
    renderComponent({ preferences: [] });
    // Select also uses combobox role in some implementations; find by label
    const typeSelect = screen.getByLabelText(/Preference type/i);
    expect(typeSelect).toBeDefined();
    const options = within(typeSelect as HTMLElement).getAllByRole("option");
    expect(options.length).toBe(4);
  });

  it("preference type options are Fluent, Learning, Curious, Exclude", () => {
    renderComponent({ preferences: [] });
    const typeSelect = screen.getByLabelText(/Preference type/i);
    const options = within(typeSelect as HTMLElement).getAllByRole("option");
    const optionTexts = options.map((o) => o.textContent);
    expect(optionTexts).toContain("Fluent");
    expect(optionTexts).toContain("Learning");
    expect(optionTexts).toContain("Curious");
    expect(optionTexts).toContain("Exclude");
  });

  it("does not render learning goal input when type is 'fluent' (default)", () => {
    renderComponent({ preferences: [] });
    expect(screen.queryByLabelText(/Learning goal/i)).toBeNull();
  });

  it("renders learning goal input when preference type is changed to 'learning'", () => {
    renderComponent({ preferences: [] });
    const typeSelect = screen.getByLabelText(/Preference type/i);
    fireEvent.change(typeSelect, { target: { value: "learning" } });
    expect(screen.getByLabelText(/Learning goal/i)).toBeDefined();
  });

  it("learning goal input disappears when type is changed from 'learning' to another", () => {
    renderComponent({ preferences: [] });
    const typeSelect = screen.getByLabelText(/Preference type/i);
    fireEvent.change(typeSelect, { target: { value: "learning" } });
    expect(screen.getByLabelText(/Learning goal/i)).toBeDefined();
    fireEvent.change(typeSelect, { target: { value: "curious" } });
    expect(screen.queryByLabelText(/Learning goal/i)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // aria-live region
  // -------------------------------------------------------------------------

  it("renders an aria-live polite region for preference change announcements", () => {
    renderComponent({ preferences: [] });
    const liveRegions = document.querySelectorAll('[aria-live="polite"]');
    expect(liveRegions.length).toBeGreaterThan(0);
  });

  // -------------------------------------------------------------------------
  // Section accessibility
  // -------------------------------------------------------------------------

  it("section has aria-labelledby='language-preferences-heading'", () => {
    renderComponent({ preferences: [] });
    const section = document.querySelector(
      "section[aria-labelledby='language-preferences-heading']"
    );
    expect(section).not.toBeNull();
  });

  it("renders the Language Preferences heading", () => {
    renderComponent({ preferences: [] });
    expect(screen.getByText("Language Preferences")).toBeDefined();
  });
});
