/**
 * Zustand store for managing recovery sessions.
 *
 * Features:
 * - Session-based recovery tracking keyed by entityId
 * - Phase-based state machine (idle, pending, in-progress, completed, failed, cancelled)
 * - AbortController integration for cancellation
 * - Persistent storage with 10-minute stale session cleanup
 * - Year filter support for recovery operations
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { RecoveryResultData } from "../types/recovery";

/**
 * Recovery operation phase.
 */
export type RecoveryPhase =
  | "idle"
  | "pending"
  | "in-progress"
  | "completed"
  | "failed"
  | "cancelled";

/**
 * Recovery session state.
 */
export interface RecoverySession {
  /** Unique session identifier (crypto.randomUUID()) */
  sessionId: string;
  /** Video ID or Channel ID being recovered */
  entityId: string;
  /** Entity type (video or channel) */
  entityType: "video" | "channel";
  /** Entity title for display in AppShell indicator (nullable) */
  entityTitle: string | null;
  /** Current recovery phase */
  phase: RecoveryPhase;
  /** Start timestamp (Date.now()) */
  startedAt: number;
  /** Completion timestamp (null until terminal phase) */
  completedAt: number | null;
  /** Year filter options */
  filterOptions: {
    startYear?: number;
    endYear?: number;
  };
  /** Recovery result data (null until completed) */
  result: RecoveryResultData | null;
  /** Human-readable error message (null unless failed) */
  error: string | null;
  /** AbortController for cancellation (non-serializable, excluded from persistence) */
  abortController: AbortController | null;
}

/**
 * Recovery store state.
 */
interface RecoveryStore {
  /** Map of entityId -> RecoverySession */
  sessions: Map<string, RecoverySession>;

  /**
   * Start a new recovery session.
   *
   * @param entityId - Video ID or Channel ID
   * @param entityType - Entity type (video or channel)
   * @param entityTitle - Entity title for display (optional)
   * @param filterOptions - Year filter options (optional)
   * @returns Session ID
   */
  startRecovery: (
    entityId: string,
    entityType: "video" | "channel",
    entityTitle?: string | null,
    filterOptions?: { startYear?: number; endYear?: number }
  ) => string;

  /**
   * Update the phase of a recovery session.
   *
   * @param sessionId - Session ID
   * @param phase - New phase
   */
  updatePhase: (sessionId: string, phase: RecoveryPhase) => void;

  /**
   * Set the recovery result and mark as completed.
   *
   * @param sessionId - Session ID
   * @param result - Recovery result data
   */
  setResult: (sessionId: string, result: RecoveryResultData) => void;

  /**
   * Set the error message and mark as failed.
   *
   * @param sessionId - Session ID
   * @param error - Human-readable error message
   */
  setError: (sessionId: string, error: string) => void;

  /**
   * Store the AbortController reference for a session.
   *
   * @param sessionId - Session ID
   * @param controller - AbortController instance
   */
  setAbortController: (sessionId: string, controller: AbortController) => void;

  /**
   * Cancel a recovery session.
   *
   * @param sessionId - Session ID
   */
  cancelRecovery: (sessionId: string) => void;

  /**
   * Remove a session from the store.
   *
   * @param sessionId - Session ID
   */
  cleanupSession: (sessionId: string) => void;

  /**
   * Get the active session for an entity (if exists).
   *
   * @param entityId - Video ID or Channel ID
   * @returns Recovery session or undefined
   */
  getActiveSession: (entityId: string) => RecoverySession | undefined;

  /**
   * Get all active sessions (pending or in-progress).
   *
   * @returns Array of active recovery sessions
   */
  getActiveSessions: () => RecoverySession[];

  /**
   * Check if any recovery is currently active.
   *
   * @returns True if any session is pending or in-progress
   */
  hasActiveRecovery: () => boolean;
}

/**
 * Terminal phases that set completedAt timestamp.
 */
const TERMINAL_PHASES: RecoveryPhase[] = ["completed", "failed", "cancelled"];

/**
 * Active phases for filtering.
 */
const ACTIVE_PHASES: RecoveryPhase[] = ["pending", "in-progress"];

/**
 * Session staleness threshold (10 minutes in milliseconds).
 */
const SESSION_STALE_THRESHOLD = 600_000;

/**
 * Custom storage configuration for Map serialization.
 */
const mapStorage = createJSONStorage(() => ({
  getItem: (name: string) => {
    const value = localStorage.getItem(name);
    if (!value) return null;

    try {
      const parsed = JSON.parse(value);
      // Convert sessions array back to Map, filtering stale sessions
      const now = Date.now();
      const sessionEntries = (parsed.state?.sessions ?? [])
        .filter(([_key, session]: [string, RecoverySession]) => {
          // Keep only active sessions that aren't stale
          if (!ACTIVE_PHASES.includes(session.phase)) {
            return false;
          }
          return now - session.startedAt <= SESSION_STALE_THRESHOLD;
        })
        .map(([key, session]: [string, RecoverySession]) => [
          key,
          { ...session, abortController: null }, // AbortController can't be serialized
        ]);

      return JSON.stringify({
        ...parsed,
        state: {
          ...parsed.state,
          sessions: sessionEntries,
        },
      });
    } catch {
      return null;
    }
  },
  setItem: (name: string, value: string) => {
    try {
      const parsed = JSON.parse(value);
      // Convert Map to array entries, excluding abortController
      const sessions = Array.from(
        (parsed.state?.sessions ?? new Map()) as Map<string, RecoverySession>
      )
        .filter(([_key, session]) => ACTIVE_PHASES.includes(session.phase))
        .map(([key, session]) => [
          key,
          {
            sessionId: session.sessionId,
            entityId: session.entityId,
            entityType: session.entityType,
            entityTitle: session.entityTitle,
            phase: session.phase,
            startedAt: session.startedAt,
            completedAt: session.completedAt,
            filterOptions: session.filterOptions,
            result: session.result,
            error: session.error,
            // Exclude abortController (non-serializable)
          },
        ]);

      localStorage.setItem(
        name,
        JSON.stringify({
          ...parsed,
          state: {
            ...parsed.state,
            sessions,
          },
        })
      );
    } catch {
      // Ignore serialization errors
    }
  },
  removeItem: (name: string) => {
    localStorage.removeItem(name);
  },
}));

/**
 * Recovery store instance.
 */
export const useRecoveryStore = create<RecoveryStore>()(
  persist(
    (set, get) => ({
      sessions: new Map(),

      startRecovery: (entityId, entityType, entityTitle = null, filterOptions = {}) => {
        const sessionId = crypto.randomUUID();
        const session: RecoverySession = {
          sessionId,
          entityId,
          entityType,
          entityTitle,
          phase: "pending",
          startedAt: Date.now(),
          completedAt: null,
          filterOptions,
          result: null,
          error: null,
          abortController: null,
        };

        set((state) => {
          const newSessions = new Map(state.sessions);
          newSessions.set(entityId, session);
          return { sessions: newSessions };
        });

        return sessionId;
      },

      updatePhase: (sessionId, phase) => {
        set((state) => {
          const newSessions = new Map(state.sessions);
          for (const [entityId, session] of newSessions.entries()) {
            if (session.sessionId === sessionId) {
              newSessions.set(entityId, {
                ...session,
                phase,
                completedAt: TERMINAL_PHASES.includes(phase) ? Date.now() : session.completedAt,
              });
              break;
            }
          }
          return { sessions: newSessions };
        });
      },

      setResult: (sessionId, result) => {
        set((state) => {
          const newSessions = new Map(state.sessions);
          for (const [entityId, session] of newSessions.entries()) {
            if (session.sessionId === sessionId) {
              newSessions.set(entityId, {
                ...session,
                result,
                phase: "completed",
                completedAt: Date.now(),
              });
              break;
            }
          }
          return { sessions: newSessions };
        });
      },

      setError: (sessionId, error) => {
        set((state) => {
          const newSessions = new Map(state.sessions);
          for (const [entityId, session] of newSessions.entries()) {
            if (session.sessionId === sessionId) {
              newSessions.set(entityId, {
                ...session,
                error,
                phase: "failed",
                completedAt: Date.now(),
              });
              break;
            }
          }
          return { sessions: newSessions };
        });
      },

      setAbortController: (sessionId, controller) => {
        set((state) => {
          const newSessions = new Map(state.sessions);
          for (const [entityId, session] of newSessions.entries()) {
            if (session.sessionId === sessionId) {
              newSessions.set(entityId, {
                ...session,
                abortController: controller,
              });
              break;
            }
          }
          return { sessions: newSessions };
        });
      },

      cancelRecovery: (sessionId) => {
        const { sessions } = get();
        for (const session of sessions.values()) {
          if (session.sessionId === sessionId) {
            // Call abort on the controller if it exists
            session.abortController?.abort();

            // Update the session state
            set((state) => {
              const newSessions = new Map(state.sessions);
              newSessions.set(session.entityId, {
                ...session,
                phase: "cancelled",
                completedAt: Date.now(),
              });
              return { sessions: newSessions };
            });
            break;
          }
        }
      },

      cleanupSession: (sessionId) => {
        set((state) => {
          const newSessions = new Map(state.sessions);
          for (const [entityId, session] of newSessions.entries()) {
            if (session.sessionId === sessionId) {
              newSessions.delete(entityId);
              break;
            }
          }
          return { sessions: newSessions };
        });
      },

      getActiveSession: (entityId) => {
        const { sessions } = get();
        return sessions.get(entityId);
      },

      getActiveSessions: () => {
        const { sessions } = get();
        return Array.from(sessions.values()).filter((session) =>
          ACTIVE_PHASES.includes(session.phase)
        );
      },

      hasActiveRecovery: () => {
        const { sessions } = get();
        for (const session of sessions.values()) {
          if (ACTIVE_PHASES.includes(session.phase)) {
            return true;
          }
        }
        return false;
      },
    }),
    {
      name: "chronovista:recovery:sessions",
      storage: mapStorage,
      partialize: (state) => ({
        // Only persist active sessions, exclude abortController
        sessions: new Map(
          Array.from(state.sessions.entries()).filter(([_key, session]) =>
            ACTIVE_PHASES.includes(session.phase)
          )
        ),
      }),
      // Convert hydrated sessions array back to a Map
      // (JSON.parse produces an array of entries, not a Map)
      merge: (persistedState, currentState) => {
        const persisted = persistedState as Partial<RecoveryStore> | undefined;
        const hydratedSessions = persisted?.sessions;
        return {
          ...currentState,
          sessions:
            hydratedSessions instanceof Map
              ? hydratedSessions
              : new Map(Array.isArray(hydratedSessions) ? hydratedSessions : []),
        };
      },
    }
  )
);
