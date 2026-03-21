/**
 * Tests for SettingsPage component.
 *
 * Coverage:
 * - Page renders with "Settings" heading
 * - Document title is set to "Settings - ChronoVista" on mount
 * - Document title is restored to "ChronoVista" on unmount
 * - All 3 section components are rendered
 * - Page has correct padding classes (p-6 lg:p-8)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock all three section components to keep tests isolated and fast
vi.mock("../../components/settings/LanguagePreferencesSection", () => ({
  LanguagePreferencesSection: () =>
    React.createElement("div", { "data-testid": "language-preferences-section" }),
}));

vi.mock("../../components/settings/CacheSection", () => ({
  CacheSection: () =>
    React.createElement("div", { "data-testid": "cache-section" }),
}));

vi.mock("../../components/settings/AboutSection", () => ({
  AboutSection: () =>
    React.createElement("div", { "data-testid": "about-section" }),
}));

import { SettingsPage } from "../SettingsPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderPage() {
  const queryClient = createQueryClient();
  return render(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(SettingsPage)
      )
    )
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SettingsPage", () => {
  const originalTitle = document.title;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Restore title after each test in case unmount was not called
    document.title = originalTitle;
  });

  // -------------------------------------------------------------------------
  // Page heading
  // -------------------------------------------------------------------------

  it("renders the 'Settings' page heading", () => {
    renderPage();
    expect(screen.getByText("Settings")).toBeDefined();
  });

  it("renders the subtitle text", () => {
    renderPage();
    expect(
      screen.getByText(
        /Manage your language preferences, cache, and application information/i
      )
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Document title lifecycle
  // -------------------------------------------------------------------------

  it("sets document.title to 'Settings - ChronoVista' on mount", () => {
    renderPage();
    expect(document.title).toBe("Settings - ChronoVista");
  });

  it("restores document.title to 'ChronoVista' on unmount", () => {
    const { unmount } = renderPage();
    expect(document.title).toBe("Settings - ChronoVista");
    unmount();
    expect(document.title).toBe("ChronoVista");
  });

  // -------------------------------------------------------------------------
  // Section components
  // -------------------------------------------------------------------------

  it("renders the LanguagePreferencesSection", () => {
    renderPage();
    expect(
      screen.getByTestId("language-preferences-section")
    ).toBeDefined();
  });

  it("renders the CacheSection", () => {
    renderPage();
    expect(screen.getByTestId("cache-section")).toBeDefined();
  });

  it("renders the AboutSection", () => {
    renderPage();
    expect(screen.getByTestId("about-section")).toBeDefined();
  });

  it("renders all 3 sections together", () => {
    renderPage();
    expect(screen.getByTestId("language-preferences-section")).toBeDefined();
    expect(screen.getByTestId("cache-section")).toBeDefined();
    expect(screen.getByTestId("about-section")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Layout
  // -------------------------------------------------------------------------

  it("outer div has p-6 padding class", () => {
    const { container } = renderPage();
    const outer = container.firstChild as HTMLElement;
    expect(outer.className).toContain("p-6");
  });

  it("outer div has lg:p-8 responsive padding class", () => {
    const { container } = renderPage();
    const outer = container.firstChild as HTMLElement;
    expect(outer.className).toContain("lg:p-8");
  });
});
