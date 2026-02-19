/**
 * AppShell component - main layout wrapper with sidebar and content area.
 *
 * Implements User Story 5: Responsive Sidebar Layout
 * - VD-005: Main content area background bg-slate-50
 * - CSS Grid works with responsive sidebar (64px or 240px)
 * - T035: beforeunload warning when recovery is active
 * - T039: Recovery indicator banner with session status
 * - T040: localStorage hydration UX with backend polling
 */

import { useEffect, useRef, useState } from "react";
import { Link, Outlet } from "react-router-dom";

import { ErrorBoundary } from "../ErrorBoundary";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { useRecoveryStore } from "../../stores/recoveryStore";
import type { RecoverySession } from "../../stores/recoveryStore";
import { apiFetch } from "../../api/config";

/**
 * Toast notification for recovery completion/failure.
 */
interface Toast {
  id: string;
  type: "success" | "error";
  message: string;
  entityTitle: string;
}

/**
 * Formats elapsed time in milliseconds to human-readable string.
 * @param ms - Elapsed milliseconds
 * @returns Formatted time string (e.g., "1m 23s", "45s")
 */
function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

/**
 * AppShell provides the main layout structure for the application.
 *
 * Layout:
 * - CSS Grid with sidebar (auto) and main area (1fr)
 * - Sidebar on the left (bg-slate-900) with responsive width (w-16 or lg:w-60)
 * - VD-005: Main area contains Header + content with bg-slate-50
 * - Content area uses Outlet for child routes wrapped in ErrorBoundary
 * - T035: Registers beforeunload handler when recovery is active
 * - T039: Displays active recovery indicator and completion toasts
 * - T040: Polls backend for hydrated sessions to detect completion
 */
export function AppShell() {
  const hasActiveRecovery = useRecoveryStore((s) => s.hasActiveRecovery());
  // Don't subscribe to activeSessions in render - causes infinite loops with persist middleware
  // Instead, use getActiveSessions() directly when needed

  // Toast state (T039)
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Previous sessions ref for detecting completion (T039)
  const prevSessionsRef = useRef<Map<string, RecoverySession>>(new Map());

  // State for elapsed time counter - forces re-render every second
  const [, setElapsedTick] = useState(0);

  // T039: Detect session completion/failure and show toasts
  // Use subscribe pattern instead of useEffect to avoid infinite loops
  useEffect(() => {
    const unsubscribe = useRecoveryStore.subscribe((state) => {
      const currentSessions = state.sessions;
      const prev = prevSessionsRef.current;

      for (const [entityId, session] of currentSessions) {
        const prevSession = prev.get(entityId);
        if (prevSession && ["pending", "in-progress"].includes(prevSession.phase)) {
          if (session.phase === "completed") {
            // Show success toast
            const fieldsRecovered = session.result?.fields_recovered.length ?? 0;
            const toast: Toast = {
              id: session.sessionId,
              type: "success",
              message: `${fieldsRecovered} field${fieldsRecovered !== 1 ? "s" : ""} recovered`,
              entityTitle: session.entityTitle ?? `${session.entityType} ${session.entityId}`,
            };
            setToasts((prev) => [...prev, toast]);

            // Schedule cleanup after 8 seconds
            setTimeout(() => {
              useRecoveryStore.getState().cleanupSession(session.sessionId);
              setToasts((prev) => prev.filter((t) => t.id !== session.sessionId));
            }, 8000);
          } else if (session.phase === "failed") {
            // Show error toast
            const toast: Toast = {
              id: session.sessionId,
              type: "error",
              message: session.error ?? "Recovery failed",
              entityTitle: session.entityTitle ?? `${session.entityType} ${session.entityId}`,
            };
            setToasts((prev) => [...prev, toast]);

            // Schedule cleanup after 8 seconds
            setTimeout(() => {
              useRecoveryStore.getState().cleanupSession(session.sessionId);
              setToasts((prev) => prev.filter((t) => t.id !== session.sessionId));
            }, 8000);
          }
        }
      }
      prevSessionsRef.current = new Map(currentSessions);
    });

    return unsubscribe;
  }, []);

  // T040: Poll backend for hydrated in-progress sessions
  useEffect(() => {
    // Get hydrated sessions from store at mount time
    const hydratedSessions = useRecoveryStore
      .getState()
      .getActiveSessions()
      .filter((session) => {
        const age = Date.now() - session.startedAt;
        return age < 600_000; // < 10 minutes
      });

    if (hydratedSessions.length === 0) return;

    const pollingIntervalId = setInterval(async () => {
      // Re-check active sessions on each interval
      const currentActiveSessions = useRecoveryStore.getState().getActiveSessions();

      for (const session of hydratedSessions) {
        // Skip if session is no longer active
        if (!currentActiveSessions.some((s) => s.sessionId === session.sessionId)) {
          continue;
        }

        try {
          const endpoint =
            session.entityType === "video"
              ? `/videos/${session.entityId}`
              : `/channels/${session.entityId}`;

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const response = await apiFetch<any>(endpoint);

          // Check if recovered_at changed (indicating completion)
          if (response.recovered_at) {
            const currentRecoveredAt = response.recovered_at;
            const sessionStartedAt = new Date(session.startedAt).toISOString();

            // If recovered_at is more recent than session start, mark as completed
            if (currentRecoveredAt > sessionStartedAt) {
              useRecoveryStore.getState().updatePhase(session.sessionId, "completed");
            }
          }
        } catch {
          // Silently ignore polling errors (best-effort)
        }
      }
    }, 30_000); // Poll every 30 seconds

    return () => clearInterval(pollingIntervalId);
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Elapsed timer effect for indicator
  // Use hasActiveRecovery instead of activeSessions to avoid infinite loops
  useEffect(() => {
    if (hasActiveRecovery) {
      const intervalId = setInterval(() => {
        setElapsedTick((prev) => prev + 1);
      }, 1000);

      return () => clearInterval(intervalId);
    }
  }, [hasActiveRecovery]);

  // T035: beforeunload warning when recovery is active
  useEffect(() => {
    if (!hasActiveRecovery) return;

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Modern browsers ignore the custom message and show their own
      // but we still need to call preventDefault() to trigger the dialog
    };

    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasActiveRecovery]);

  return (
    <div className="grid grid-cols-[auto_1fr] min-h-screen">
      {/* Sidebar with main navigation */}
      <Sidebar />

      {/* Main content area */}
      <div className="flex flex-col min-h-screen">
        <Header />

        {/* T039: Active recovery indicator banner */}
        {hasActiveRecovery && (() => {
          // Get active sessions directly to avoid subscription issues
          const activeSessions = useRecoveryStore.getState().getActiveSessions();
          const firstSession = activeSessions[0];
          if (!firstSession) return null;

          return (
            <div
              className="bg-amber-50 border-b border-amber-200 px-6 py-3"
              role="status"
              aria-live="polite"
            >
              {activeSessions.length === 1 ? (
                <div className="flex items-center gap-3 text-sm">
                  <div className="w-4 h-4 border-2 border-amber-600 border-t-transparent rounded-full animate-spin" />
                  <span className="text-amber-900">
                    Recovery in progress for{" "}
                    <Link
                      to={`/${firstSession.entityType}s/${firstSession.entityId}`}
                      className="font-medium underline hover:text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 rounded"
                    >
                      {firstSession.entityTitle ?? firstSession.entityId}
                    </Link>
                    ... ({formatElapsed(Date.now() - firstSession.startedAt)})
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-3 text-sm">
                  <div className="w-4 h-4 border-2 border-amber-600 border-t-transparent rounded-full animate-spin" />
                  <span className="text-amber-900">
                    {activeSessions.length} recoveries in progress
                  </span>
                </div>
              )}

              {/* T040: Hydration info text for recent sessions */}
              {activeSessions.some((s) => Date.now() - s.startedAt < 600_000) && (
                <p className="text-xs text-amber-700 mt-2 ml-7">
                  A recovery operation started earlier may still be in progress.
                </p>
              )}
            </div>
          );
        })()}

        {/* T039: Toast notifications for completion/failure */}
        {toasts.length > 0 && (
          <div
            className="fixed top-20 right-6 z-50 space-y-2"
            aria-live="polite"
            role="status"
          >
            {toasts.map((toast) => (
              <div
                key={toast.id}
                className={`max-w-md px-4 py-3 rounded-lg shadow-lg border ${
                  toast.type === "success"
                    ? "bg-green-50 border-green-200"
                    : "bg-red-50 border-red-200"
                }`}
              >
                <div className="flex items-start gap-3">
                  {toast.type === "success" ? (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
                      />
                    </svg>
                  ) : (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
                      />
                    </svg>
                  )}
                  <div>
                    <p
                      className={`text-sm font-medium ${
                        toast.type === "success" ? "text-green-900" : "text-red-900"
                      }`}
                    >
                      {toast.type === "success" ? "Recovery completed" : "Recovery failed"}
                    </p>
                    <p
                      className={`text-sm ${
                        toast.type === "success" ? "text-green-800" : "text-red-800"
                      }`}
                    >
                      {toast.entityTitle} — {toast.message}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <main className="flex-1 overflow-auto bg-slate-50">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
