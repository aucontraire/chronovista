/**
 * AppShell component - main layout wrapper with sidebar and content area.
 *
 * Implements User Story 5: Responsive Sidebar Layout
 * - VD-005: Main content area background bg-slate-50
 * - CSS Grid works with responsive sidebar (64px or 240px)
 */

import { Outlet } from "react-router-dom";

import { ErrorBoundary } from "../ErrorBoundary";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * AppShell provides the main layout structure for the application.
 *
 * Layout:
 * - CSS Grid with sidebar (auto) and main area (1fr)
 * - Sidebar on the left (bg-slate-900) with responsive width (w-16 or lg:w-60)
 * - VD-005: Main area contains Header + content with bg-slate-50
 * - Content area uses Outlet for child routes wrapped in ErrorBoundary
 */
export function AppShell() {
  return (
    <div className="grid grid-cols-[auto_1fr] min-h-screen">
      {/* Sidebar with main navigation */}
      <Sidebar />

      {/* Main content area */}
      <div className="flex flex-col min-h-screen">
        <Header />
        <main className="flex-1 overflow-auto bg-slate-50">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
