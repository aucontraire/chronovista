/**
 * SettingsPage — main settings and preferences page.
 *
 * Route: /settings
 *
 * Feature 049 (Settings & Preferences Page):
 * - T005: Page skeleton with three section placeholders
 *
 * Section placeholders (to be replaced in later tasks):
 * - Language Preferences (T010: LanguagePreferencesSection)
 * - Cache (T017: CacheSection)
 * - About (T021: AboutSection)
 */

import { useEffect } from "react";

import { AboutSection } from "../components/settings/AboutSection";
import { CacheSection } from "../components/settings/CacheSection";
import { LanguagePreferencesSection } from "../components/settings/LanguagePreferencesSection";

/**
 * SettingsPage displays user-configurable preferences and application info.
 * Rendered within the AppShell layout which provides the header and sidebar.
 */
export function SettingsPage() {
  // Set page title on mount; restore the default on unmount.
  useEffect(() => {
    document.title = "Settings - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  return (
    <div className="p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-900">Settings</h2>
        <p className="text-slate-600 mt-1">
          Manage your language preferences, cache, and application information.
        </p>
      </div>

      <div className="space-y-6">
        {/* ------------------------------------------------------------------ */}
        {/* Language Preferences section (T009)                                */}
        {/* ------------------------------------------------------------------ */}
        <LanguagePreferencesSection />

        {/* ------------------------------------------------------------------ */}
        {/* Cache section (T016)                                               */}
        {/* ------------------------------------------------------------------ */}
        <CacheSection />

        {/* ------------------------------------------------------------------ */}
        {/* About section (T020)                                               */}
        {/* ------------------------------------------------------------------ */}
        <AboutSection />
      </div>
    </div>
  );
}
