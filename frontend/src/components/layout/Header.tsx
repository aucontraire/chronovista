/**
 * Header component - displays the application header with branding.
 */

/**
 * Header displays the Chronovista app name and branding.
 *
 * Features:
 * - 64px height (h-16)
 * - White background with bottom border
 * - Semantic header element for accessibility
 */
export function Header() {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center px-6 shrink-0">
      <h1 className="text-xl font-bold text-slate-900 tracking-tight">
        Chronovista
      </h1>
    </header>
  );
}
