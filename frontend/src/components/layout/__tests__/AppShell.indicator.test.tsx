/**
 * Tests for AppShell recovery indicator and localStorage hydration UX.
 *
 * Tests T039: AppShell Recovery Indicator
 * - Active recovery shows banner with entity title
 * - Banner includes link to entity detail page
 * - Multiple active sessions show count
 * - Success toast shown on completion with field count
 * - Error toast shown on failure with error message
 * - Toast auto-dismisses after 8 seconds
 * - Session cleaned up after toast dismiss
 * - No banner shown when no active sessions
 *
 * Tests T040: localStorage Hydration UX
 * - Hydrated in-progress session shows info text
 * - Backend polling triggers every 30 seconds
 * - Polling detects `recovered_at` change and transitions to completed
 * - Polling stops when session completes
 * - Polling failure is silently ignored
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AppShell } from "../AppShell";
import { useRecoveryStore } from "../../../stores/recoveryStore";
import * as apiConfig from "../../../api/config";

// Mock the API config module
vi.mock("../../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
  RECOVERY_TIMEOUT: 660000,
}));

// Mock the child components
vi.mock("../Header", () => ({
  Header: () => <div data-testid="mock-header">Header</div>,
}));

vi.mock("../Sidebar", () => ({
  Sidebar: () => <div data-testid="mock-sidebar">Sidebar</div>,
}));

vi.mock("../../ErrorBoundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("AppShell - T039 Recovery Indicator", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Clear the store before each test
    useRecoveryStore.setState({ sessions: new Map() });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("should show banner when active recovery exists", () => {
    // Start a recovery session
    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video Title");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    expect(
      screen.getByText(/Recovery in progress for/i, { exact: false })
    ).toBeInTheDocument();
    expect(screen.getByText("Test Video Title")).toBeInTheDocument();
  });

  it("should include link to entity detail page", () => {
    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    const link = screen.getByRole("link", { name: /Test Video/i });
    expect(link).toHaveAttribute("href", "/videos/video123");
  });

  it("should show count when multiple active sessions exist", () => {
    const sessionId1 = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Video 1");
    const sessionId2 = useRecoveryStore
      .getState()
      .startRecovery("video456", "video", "Video 2");

    useRecoveryStore.getState().updatePhase(sessionId1, "in-progress");
    useRecoveryStore.getState().updatePhase(sessionId2, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    expect(screen.getByText("2 recoveries in progress")).toBeInTheDocument();
  });

  it("should show success toast on completion with field count", async () => {
    // This test needs real timers because the toast appears via Zustand subscribe + React state update
    vi.useRealTimers();

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Allow useEffect with subscribe to run and populate prevSessionsRef with pending session
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now transition to in-progress to update prevSessionsRef
    act(() => {
      useRecoveryStore.getState().updatePhase(sessionId, "in-progress");
    });

    // Wait for subscribe to update prevSessionsRef
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now simulate completion
    act(() => {
      useRecoveryStore.getState().setResult(sessionId, {
        success: true,
        snapshot_used: "20230101120000",
        fields_recovered: ["title", "description"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.5,
      });
    });

    // Wait for the toast to appear
    await waitFor(() => {
      expect(screen.getByText("Recovery completed")).toBeInTheDocument();
    });

    expect(screen.getByText(/2 fields recovered/i)).toBeInTheDocument();
  });

  it("should show error toast on failure with error message", async () => {
    // This test needs real timers because the toast appears via Zustand subscribe + React state update
    vi.useRealTimers();

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Allow useEffect with subscribe to run and populate prevSessionsRef with pending session
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now transition to in-progress to update prevSessionsRef
    act(() => {
      useRecoveryStore.getState().updatePhase(sessionId, "in-progress");
    });

    // Wait for subscribe to update prevSessionsRef
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now simulate failure
    act(() => {
      useRecoveryStore.getState().setError(sessionId, "Network timeout");
    });

    // Wait for the toast to appear
    await waitFor(() => {
      expect(screen.getByText("Recovery failed")).toBeInTheDocument();
    });

    expect(screen.getByText(/Network timeout/i)).toBeInTheDocument();
  });

  it("should auto-dismiss toast after 8 seconds and cleanup session", { timeout: 10000 }, async () => {
    // This test uses real timers for the entire flow since mixing fake/real is problematic
    vi.useRealTimers();

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Allow useEffect with subscribe to run and populate prevSessionsRef with pending session
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now transition to in-progress to update prevSessionsRef
    act(() => {
      useRecoveryStore.getState().updatePhase(sessionId, "in-progress");
    });

    // Wait for subscribe to update prevSessionsRef
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now simulate completion
    act(() => {
      useRecoveryStore.getState().setResult(sessionId, {
        success: true,
        snapshot_used: "20230101120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 1,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.0,
      });
    });

    // Wait for toast to appear
    await waitFor(() => {
      expect(screen.getByText("Recovery completed")).toBeInTheDocument();
    });

    // Wait for toast auto-dismiss (8 seconds) + cleanup
    await waitFor(
      () => {
        expect(screen.queryByText("Recovery completed")).not.toBeInTheDocument();
      },
      { timeout: 9000 }
    );

    // Verify session was cleaned up
    const sessions = useRecoveryStore.getState().sessions;
    expect(sessions.has("video123")).toBe(false);
  });

  it("should not show banner when no active sessions exist", () => {
    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    expect(screen.queryByText(/Recovery in progress/i)).not.toBeInTheDocument();
  });

  it("should show elapsed time in banner", () => {
    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Should show initial elapsed time (0s)
    expect(screen.getByText(/\(0s\)/i)).toBeInTheDocument();

    // Advance 5 seconds - wrap in act to flush React state updates
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    // Should update to 5s
    expect(screen.getByText(/\(5s\)/i)).toBeInTheDocument();
  });
});

describe("AppShell - T040 localStorage Hydration UX", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useRecoveryStore.setState({ sessions: new Map() });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("should show info text for hydrated in-progress session", () => {
    // Simulate a session that was hydrated from localStorage (< 10 min old)
    const recentSessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(recentSessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    expect(
      screen.getByText(
        /A recovery operation started earlier may still be in progress/i
      )
    ).toBeInTheDocument();
  });

  it("should poll backend every 30 seconds", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);
    apiFetchMock.mockResolvedValue({
      video_id: "video123",
      title: "Test Video",
      recovered_at: null,
    });

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Initial poll should not happen immediately
    expect(apiFetchMock).not.toHaveBeenCalled();

    // Advance 30 seconds to trigger first poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      // Flush microtasks without running more timers
      await Promise.resolve();
    });

    // Check that first poll happened
    expect(apiFetchMock).toHaveBeenCalledWith("/videos/video123");
    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    // Advance another 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(2);
  });

  it("should detect recovered_at change and transition to completed", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);

    useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");

    // First poll: no recovery
    apiFetchMock.mockResolvedValueOnce({
      video_id: "video123",
      title: "Test Video",
      recovered_at: null,
    });

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Advance to first poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    // Session should still be pending
    expect(useRecoveryStore.getState().sessions.get("video123")?.phase).toBe(
      "pending"
    );

    // Second poll: recovery completed (recovered_at is newer than session start)
    apiFetchMock.mockResolvedValueOnce({
      video_id: "video123",
      title: "Test Video - Recovered",
      recovered_at: new Date(Date.now() + 1000).toISOString(), // More recent than session start
    });

    // Advance to second poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(2);

    // Session should transition to completed
    expect(useRecoveryStore.getState().sessions.get("video123")?.phase).toBe(
      "completed"
    );
  });

  it("should stop polling when session completes", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);
    apiFetchMock.mockResolvedValue({
      video_id: "video123",
      title: "Test Video",
      recovered_at: null,
    });

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    const { unmount } = render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // First poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });
    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    // Mark session as completed - wrap in act
    await act(async () => {
      useRecoveryStore.getState().setResult(sessionId, {
        success: true,
        snapshot_used: "20230101120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 1,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.0,
      });
    });

    // Unmount and remount to trigger cleanup
    unmount();
    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Advance another 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    // Should not poll again (session is completed, not active)
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it("should silently ignore polling failures", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    // Mock network error
    apiFetchMock.mockRejectedValue(new Error("Network error"));

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Advance to first poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    // Session should still be in-progress (error ignored)
    expect(useRecoveryStore.getState().sessions.get("video123")?.phase).toBe(
      "in-progress"
    );

    // Should not log errors (silent failure)
    expect(consoleErrorSpy).not.toHaveBeenCalled();

    consoleErrorSpy.mockRestore();
  });

  it("should handle channel entity type in polling", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);
    apiFetchMock.mockResolvedValue({
      channel_id: "channel123",
      title: "Test Channel",
      recovered_at: null,
    });

    const sessionId = useRecoveryStore
      .getState()
      .startRecovery("channel123", "channel", "Test Channel");
    useRecoveryStore.getState().updatePhase(sessionId, "in-progress");

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Advance to first poll
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(apiFetchMock).toHaveBeenCalledWith("/channels/channel123");
  });

  it("should not poll for sessions older than 10 minutes", async () => {
    const apiFetchMock = vi.mocked(apiConfig.apiFetch);

    // Create a session and manually set its startedAt to 11 minutes ago
    useRecoveryStore
      .getState()
      .startRecovery("video123", "video", "Test Video");
    const sessions = useRecoveryStore.getState().sessions;
    const session = sessions.get("video123");

    if (session) {
      session.startedAt = Date.now() - 660_000; // 11 minutes ago
      useRecoveryStore.setState({ sessions: new Map(sessions) });
    }

    render(
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    );

    // Advance 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    // Should not poll (session is too old)
    expect(apiFetchMock).not.toHaveBeenCalled();
  });
});
