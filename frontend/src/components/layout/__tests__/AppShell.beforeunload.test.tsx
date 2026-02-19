/**
 * Tests for AppShell beforeunload Warning (T035)
 *
 * Tests beforeunload handler registration when recovery is active:
 * - Handler registered when active recovery exists
 * - Handler NOT registered when no active recovery
 * - Handler removed when recovery completes
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../AppShell";
import { useRecoveryStore } from "../../../stores/recoveryStore";

describe("AppShell - beforeunload Warning (T035)", () => {
  let addEventListenerSpy: ReturnType<typeof vi.spyOn>;
  let removeEventListenerSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Reset store state before each test
    useRecoveryStore.setState({ sessions: new Map() });

    // Spy on window event listeners
    addEventListenerSpy = vi.spyOn(window, "addEventListener");
    removeEventListenerSpy = vi.spyOn(window, "removeEventListener");
  });

  afterEach(() => {
    // Clean up spies
    vi.restoreAllMocks();
  });

  it("should register beforeunload listener when active recovery exists", () => {
    // Set up store with in-progress session
    useRecoveryStore.setState({
      sessions: new Map([
        ["test-video-id", {
          sessionId: "test-session",
          entityId: "test-video-id",
          entityType: "video",
          entityTitle: "Test Video",
          phase: "in-progress",
          startedAt: Date.now(),
          completedAt: null,
          filterOptions: {},
          result: null,
          error: null,
          abortController: null,
        }],
      ]),
    });

    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Check that beforeunload listener was added
    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );
  });

  it("should NOT register beforeunload listener when no active recovery", () => {
    // Store has no sessions (idle state)
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Check that beforeunload listener was NOT added
    expect(addEventListenerSpy).not.toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );
  });

  it("should remove beforeunload listener when component unmounts", () => {
    // Set up store with in-progress session
    useRecoveryStore.setState({
      sessions: new Map([
        ["test-video-id", {
          sessionId: "test-session",
          entityId: "test-video-id",
          entityType: "video",
          entityTitle: "Test Video",
          phase: "in-progress",
          startedAt: Date.now(),
          completedAt: null,
          filterOptions: {},
          result: null,
          error: null,
          abortController: null,
        }],
      ]),
    });

    const { unmount } = render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Verify listener was added
    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );

    // Clear the spy call history
    addEventListenerSpy.mockClear();
    removeEventListenerSpy.mockClear();

    // Unmount the component
    unmount();

    // Check that beforeunload listener was removed
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );
  });

  it("should register beforeunload listener for pending phase", () => {
    // Set up store with pending session
    useRecoveryStore.setState({
      sessions: new Map([
        ["test-video-id", {
          sessionId: "test-session",
          entityId: "test-video-id",
          entityType: "video",
          entityTitle: "Test Video",
          phase: "pending",
          startedAt: Date.now(),
          completedAt: null,
          filterOptions: {},
          result: null,
          error: null,
          abortController: null,
        }],
      ]),
    });

    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Check that beforeunload listener was added
    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );
  });

  it("should NOT register beforeunload listener for completed phase", () => {
    // Set up store with completed session
    useRecoveryStore.setState({
      sessions: new Map([
        ["test-video-id", {
          sessionId: "test-session",
          entityId: "test-video-id",
          entityType: "video",
          entityTitle: "Test Video",
          phase: "completed",
          startedAt: Date.now() - 5000,
          completedAt: Date.now(),
          filterOptions: {},
          result: {
            success: true,
            snapshot_used: "20230415120000",
            fields_recovered: ["title"],
            fields_skipped: [],
            snapshots_available: 5,
            snapshots_tried: 1,
            failure_reason: null,
            duration_seconds: 2.1,
          },
          error: null,
          abortController: null,
        }],
      ]),
    });

    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Check that beforeunload listener was NOT added
    expect(addEventListenerSpy).not.toHaveBeenCalledWith(
      "beforeunload",
      expect.any(Function)
    );
  });

  it("should call preventDefault on beforeunload event", () => {
    // Set up store with in-progress session
    useRecoveryStore.setState({
      sessions: new Map([
        ["test-video-id", {
          sessionId: "test-session",
          entityId: "test-video-id",
          entityType: "video",
          entityTitle: "Test Video",
          phase: "in-progress",
          startedAt: Date.now(),
          completedAt: null,
          filterOptions: {},
          result: null,
          error: null,
          abortController: null,
        }],
      ]),
    });

    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    // Get the handler function that was registered
    const calls = addEventListenerSpy.mock.calls.filter(
      (call: unknown[]) => call[0] === "beforeunload"
    );
    expect(calls.length).toBe(1);
    const handler = calls[0][1] as (e: BeforeUnloadEvent) => void;

    // Create a mock beforeunload event
    const mockEvent = {
      preventDefault: vi.fn(),
    } as unknown as BeforeUnloadEvent;

    // Call the handler
    handler(mockEvent);

    // Verify preventDefault was called
    expect(mockEvent.preventDefault).toHaveBeenCalled();
  });
});
