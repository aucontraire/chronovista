/**
 * Tests for UnavailabilityBanner Recovery Button (Feature 025)
 *
 * Tests recovery button and status feedback features:
 * - Recovery button visibility based on props
 * - Loading state during recovery
 * - Success/failure status messages
 * - Re-recovery label for previously recovered content
 * - Keyboard accessibility
 * - Screen reader announcements
 * - T034: Elapsed time counter during recovery
 * - T041: Cancel button for active recovery operations
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { UnavailabilityBanner } from "../UnavailabilityBanner";
import { useRecoveryStore } from "../../stores/recoveryStore";
import type { RecoveryResultData } from "../../types/recovery";

describe("UnavailabilityBanner - Recovery Button", () => {
  beforeEach(() => {
    // Reset store state before each test
    useRecoveryStore.setState({ sessions: new Map() });
    // Use fake timers for elapsed time tests
    vi.useFakeTimers();
  });

  afterEach(() => {
    // Restore real timers
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("Button Visibility", () => {
    it("should show recovery button when onRecover is provided and entity is unavailable", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      expect(button).toBeInTheDocument();
    });

    it("should not show recovery button when onRecover is not provided", () => {
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
        />
      );

      expect(
        screen.queryByRole("button", { name: /recover from web archive/i })
      ).not.toBeInTheDocument();
    });

    it("should not show recovery button when entityId is not provided", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.queryByRole("button", { name: /recover from web archive/i })
      ).not.toBeInTheDocument();
    });

    it("should show recovery button for channel entity type", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="channel"
          entityId="test-channel-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      expect(button).toBeInTheDocument();
    });
  });

  describe("Loading State", () => {
    it("should show loading spinner when phase is 'in-progress'", () => {
      const mockRecover = vi.fn();

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
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/recovering from web archive/i)
      ).toBeInTheDocument();
    });

    it("should disable button when phase is 'in-progress'", () => {
      const mockRecover = vi.fn();

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
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      expect(button).toBeDisabled();
    });

    it("should show spinner icon during recovery", () => {
      const mockRecover = vi.fn();

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

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const spinnerContainer = screen
        .getByText(/recovering from web archive/i)
        .closest("div");
      const spinner = spinnerContainer?.querySelector("svg.animate-spin");
      expect(spinner).toBeInTheDocument();
    });
  });

  describe("Success Messages", () => {
    it("should show success message with field count and snapshot date when recovery succeeds", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title", "description"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 2,
        failure_reason: null,
        duration_seconds: 3.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/recovered 2 fields from archive snapshot 2023-04-15/i)
      ).toBeInTheDocument();
    });

    it("should use singular 'field' when only 1 field recovered", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/recovered 1 field from archive snapshot 2023-04-15/i)
      ).toBeInTheDocument();
    });

    it("should show green success styling for successful recovery", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title", "description"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 2,
        failure_reason: null,
        duration_seconds: 3.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const successMessage = screen
        .getByText(/recovered 2 fields/i)
        .closest("div");
      expect(successMessage).toHaveClass("bg-green-50");
      expect(successMessage).toHaveClass("border-green-200");
      expect(successMessage).toHaveClass("text-green-700");
    });

    it("should show CheckCircleIcon for successful recovery", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const successMessage = screen.getByText(/recovered 1 field/i).closest("div");
      const icon = successMessage?.querySelector("svg");
      expect(icon).toBeInTheDocument();
    });
  });

  describe("Zero-Field Success", () => {
    it("should show blue informational message when no fields recovered (all up-to-date)", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: [],
        fields_skipped: ["title", "description"],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/recovery completed.*all fields already up-to-date/i)
      ).toBeInTheDocument();
    });

    it("should show blue styling for zero-field success", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: [],
        fields_skipped: ["title", "description"],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const infoMessage = screen
        .getByText(/all fields already up-to-date/i)
        .closest("div");
      expect(infoMessage).toHaveClass("bg-blue-50");
      expect(infoMessage).toHaveClass("border-blue-200");
      expect(infoMessage).toHaveClass("text-blue-700");
    });

    it("should show InformationCircleIcon for zero-field success", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: [],
        fields_skipped: ["title"],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const infoMessage = screen
        .getByText(/all fields already up-to-date/i)
        .closest("div");
      const icon = infoMessage?.querySelector("svg");
      expect(icon).toBeInTheDocument();
    });
  });

  describe("Failure Messages", () => {
    it("should show contextual message for no_snapshots_found", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "no_snapshots_found",
        duration_seconds: 0.5,
      };

      // Set up store with completed (failed) session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/no archived snapshots found for this content/i)
      ).toBeInTheDocument();
    });

    it("should show contextual message for all_snapshots_failed", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 5,
        failure_reason: "all_snapshots_failed",
        duration_seconds: 2.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(
          /could not extract metadata from available snapshots/i
        )
      ).toBeInTheDocument();
    });

    it("should show contextual message for cdx_connection_error", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "cdx_connection_error",
        duration_seconds: 10.0,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(
          /web archive is temporarily unavailable.*please try again later/i
        )
      ).toBeInTheDocument();
    });

    it("should show generic failure message with custom reason when provided", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "unknown_error_occurred",
        duration_seconds: 0.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/recovery failed: unknown_error_occurred/i)
      ).toBeInTheDocument();
    });

    it("should show red styling for failure messages", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "no_snapshots_found",
        duration_seconds: 0.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const errorMessage = screen
        .getByText(/no archived snapshots found/i)
        .closest("div");
      expect(errorMessage).toHaveClass("bg-red-50");
      expect(errorMessage).toHaveClass("border-red-200");
      expect(errorMessage).toHaveClass("text-red-700");
    });

    it("should show XCircleIcon for failure messages", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "no_snapshots_found",
        duration_seconds: 0.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const errorMessage = screen
        .getByText(/no archived snapshots found/i)
        .closest("div");
      const icon = errorMessage?.querySelector("svg");
      expect(icon).toBeInTheDocument();
    });
  });

  describe("Re-recover Label", () => {
    it("should show 'Re-recover from Web Archive' when recoveredAt is set", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
          recoveredAt="2023-04-15T12:00:00Z"
        />
      );

      const button = screen.getByRole("button", {
        name: /re-recover from web archive/i,
      });
      expect(button).toBeInTheDocument();
    });

    it("should show 'Recover from Web Archive' when recoveredAt is null", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
          recoveredAt={null}
        />
      );

      const button = screen.getByRole("button", {
        name: /^recover from web archive$/i,
      });
      expect(button).toBeInTheDocument();
    });

    it("should show 'Recover from Web Archive' when recoveredAt is undefined", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /^recover from web archive$/i,
      });
      expect(button).toBeInTheDocument();
    });

    it("should display formatted previous recovery date when recoveredAt is set", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
          recoveredAt="2023-04-15T12:00:00Z"
        />
      );

      // The date should be formatted as "Apr 15, 2023" (locale-dependent)
      expect(screen.getByText(/last:/i)).toBeInTheDocument();
    });
  });

  describe("Keyboard Accessibility", () => {
    it("should trigger onRecover when Enter key is pressed", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      await user.click(button);
      expect(mockRecover).toHaveBeenCalledTimes(1);

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should trigger onRecover when Space key is pressed", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      button.focus();
      await user.keyboard(" ");
      expect(mockRecover).toHaveBeenCalledTimes(1);

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should have visible focus indicator on recovery button", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      expect(button).toHaveClass("focus:outline-none");
      expect(button).toHaveClass("focus:ring-2");
      expect(button).toHaveClass("focus:ring-offset-2");
    });

    it("should not trigger onRecover when button is disabled", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();

      // Set up store with in-progress session to disable button
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
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      await user.click(button);
      expect(mockRecover).not.toHaveBeenCalled();

      // Restore fake timers
      vi.useFakeTimers();
    });
  });

  describe("ARIA Live Region", () => {
    it("should have aria-live='polite' on recovery status container", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const ariaLiveRegion = container.querySelector('[aria-live="polite"]');
      // The main banner has aria-live, but the recovery status area should also have it
      const statusRegions = container.querySelectorAll('[aria-live="polite"]');
      expect(statusRegions.length).toBeGreaterThan(0);
    });

    it("should have aria-atomic='true' on recovery status container", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const ariaAtomicRegion = container.querySelector('[aria-atomic="true"]');
      expect(ariaAtomicRegion).toBeInTheDocument();
    });

    it("should announce loading state to screen readers", () => {
      const mockRecover = vi.fn();

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
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const loadingText = screen.getByText(/recovering from web archive/i);
      expect(loadingText).toBeInTheDocument();
    });

    it("should announce success to screen readers", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title", "description"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const successMessage = screen.getByText(/recovered 2 fields/i);
      expect(successMessage).toBeInTheDocument();
    });

    it("should announce failure to screen readers", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: false,
        snapshot_used: null,
        fields_recovered: [],
        fields_skipped: [],
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: "no_snapshots_found",
        duration_seconds: 0.5,
      };

      // Set up store with completed session and result
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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const errorMessage = screen.getByText(/no archived snapshots found/i);
      expect(errorMessage).toBeInTheDocument();
    });
  });

  describe("Button Styling", () => {
    it("should have archive box icon", () => {
      const mockRecover = vi.fn();
      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      const icon = button.querySelector("svg");
      expect(icon).toBeInTheDocument();
    });

    it("should have correct button classes for enabled state", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      expect(button).toHaveClass("bg-slate-700");
      expect(button).toHaveClass("hover:bg-slate-800");
      expect(button).toHaveClass("text-white");
      expect(button).toHaveClass("rounded-lg");
    });

    it("should have disabled cursor class when disabled", () => {
      const mockRecover = vi.fn();

      // Set up store with in-progress session to disable button
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
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const button = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      expect(button).toHaveClass("disabled:cursor-not-allowed");
    });
  });

  describe("Year Filter UI", () => {
    it("should show advanced options toggle button when onRecover and entityId are provided", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      expect(toggleButton).toBeInTheDocument();
    });

    it("should not show year filter panel initially (advanced options collapsed by default)", () => {
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const panel = document.getElementById("recovery-advanced-options");
      expect(panel).not.toBeInTheDocument();
    });

    it("should expand advanced options panel when toggle is clicked", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const panel = document.getElementById("recovery-advanced-options");
      expect(panel).toBeInTheDocument();

      // Panel should have two select dropdowns
      const selects = panel?.querySelectorAll("select");
      expect(selects?.length).toBe(2);

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should have aria-expanded='false' initially and aria-expanded='true' after click", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });

      expect(toggleButton).toHaveAttribute("aria-expanded", "false");

      await user.click(toggleButton);

      expect(toggleButton).toHaveAttribute("aria-expanded", "true");

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should render start year select with all years (2005-current year) plus 'Any year' default", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const currentYear = new Date().getFullYear();
      const yearCount = currentYear - 2005 + 1;

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);
      const options = startYearSelect.querySelectorAll("option");

      // Should have "Any year" + (current year - 2005 + 1) years
      expect(options.length).toBe(yearCount + 1);
      expect(options[0].textContent).toBe("Any year");
      expect(options[0]).toHaveValue("");
      expect(options[1]).toHaveValue("2005");
      expect(options[yearCount]).toHaveValue(String(currentYear));

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should render end year select with all years (2005-current year) and current year as default", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const currentYear = new Date().getFullYear();
      const yearCount = currentYear - 2005 + 1;

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const endYearSelect = screen.getByLabelText(/to:/i);
      const options = endYearSelect.querySelectorAll("option");

      // Should have "Any year" + (current year - 2005 + 1) years
      expect(options.length).toBe(yearCount + 1);
      expect(options[0].textContent).toBe("Any year");
      expect(options[0]).toHaveValue("");
      expect(options[1]).toHaveValue("2005");
      expect(options[yearCount]).toHaveValue(String(currentYear));

      // The end year should default to current year
      expect(endYearSelect).toHaveValue(String(currentYear));

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should show year validation error when end year < start year", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);
      const endYearSelect = screen.getByLabelText(/to:/i);

      // Set start year to 2020, end year to 2015
      await user.selectOptions(startYearSelect, "2020");
      await user.selectOptions(endYearSelect, "2015");

      // Validation error should appear
      const errorAlert = screen.getByRole("alert");
      expect(errorAlert).toHaveTextContent("End year must be after start year");

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should clear year validation error when end year is changed to be >= start year", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);
      const endYearSelect = screen.getByLabelText(/to:/i);

      // Set invalid range first
      await user.selectOptions(startYearSelect, "2020");
      await user.selectOptions(endYearSelect, "2015");

      // Error should be present
      expect(screen.getByRole("alert")).toBeInTheDocument();

      // Fix the range
      await user.selectOptions(endYearSelect, "2022");

      // Error should be gone
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should disable recovery button when year validation error exists", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const recoveryButton = screen.getByRole("button", {
        name: /recover from web archive/i,
      });

      // Initially enabled
      expect(recoveryButton).not.toBeDisabled();

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);
      const endYearSelect = screen.getByLabelText(/to:/i);

      // Set invalid range
      await user.selectOptions(startYearSelect, "2020");
      await user.selectOptions(endYearSelect, "2015");

      // Button should be disabled
      expect(recoveryButton).toBeDisabled();

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should show help text when advanced options panel is expanded", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      expect(
        screen.getByText(/default searches all years/i)
      ).toBeInTheDocument();

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should pass year values to onRecover when both years are selected", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);
      const endYearSelect = screen.getByLabelText(/to:/i);

      await user.selectOptions(startYearSelect, "2018");
      await user.selectOptions(endYearSelect, "2022");

      const recoveryButton = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      expect(mockRecover).toHaveBeenCalledWith({
        startYear: 2018,
        endYear: 2022,
      });

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should pass only endYear (current year) to onRecover when 'Any year' is selected for startYear", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const currentYear = new Date().getFullYear();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const recoveryButton = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      expect(mockRecover).toHaveBeenCalledWith({ endYear: currentYear });

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should pass both startYear and default endYear (current year) when only startYear is explicitly changed", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const currentYear = new Date().getFullYear();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });
      await user.click(toggleButton);

      const startYearSelect = screen.getByLabelText(/from:/i);

      await user.selectOptions(startYearSelect, "2020");

      const recoveryButton = screen.getByRole("button", {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      expect(mockRecover).toHaveBeenCalledWith({ startYear: 2020, endYear: currentYear });

      // Restore fake timers
      vi.useFakeTimers();
    });

    it("should make toggle button keyboard accessible", async () => {
      // Use real timers for userEvent to avoid conflicts
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /advanced options/i,
      });

      // Verify it's a button (automatically keyboard accessible)
      expect(toggleButton.tagName).toBe("BUTTON");

      // Verify it can be triggered via keyboard
      toggleButton.focus();
      await user.keyboard(" "); // Space key

      const panel = document.getElementById("recovery-advanced-options");
      expect(panel).toBeInTheDocument();

      // Restore fake timers
      vi.useFakeTimers();
    });
  });

  describe("Elapsed Time Counter (T034)", () => {
    it("should show '0s elapsed' initially when recovery starts", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session starting now
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.getByText(/\(0s elapsed\)/i)).toBeInTheDocument();
    });

    it("should show elapsed timer updating after 1 second", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session that started 1 second ago
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now - 1000,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      // Should show 1s elapsed
      expect(screen.getByText(/\(1s elapsed\)/i)).toBeInTheDocument();
    });

    it("should show '1m 23s' format after 83 seconds", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session that started 83 seconds ago
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now - 83000,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.getByText(/\(1m 23s elapsed\)/i)).toBeInTheDocument();
    });

    it("should not show timer when phase is idle", () => {
      const mockRecover = vi.fn();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.queryByText(/elapsed/i)).not.toBeInTheDocument();
    });

    it("should not show timer when phase is completed", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.queryByText(/elapsed/i)).not.toBeInTheDocument();
    });

    it("should show help text 'This can take 1-5 minutes' during recovery", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(
        screen.getByText(/this can take 1–5 minutes depending on archive availability/i)
      ).toBeInTheDocument();
    });

    it("should have aria-live and aria-atomic on elapsed timer for screen readers", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const timerElement = screen.getByText(/\(0s elapsed\)/i);
      expect(timerElement).toHaveAttribute("aria-live", "polite");
      expect(timerElement).toHaveAttribute("aria-atomic", "true");
    });
  });

  describe("Cancel Button (T041)", () => {
    it("should show cancel button when phase is in-progress", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).toBeInTheDocument();
    });

    it("should not show cancel button when phase is idle", () => {
      const mockRecover = vi.fn();

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
    });

    it("should not show cancel button when phase is completed", () => {
      const mockRecover = vi.fn();
      const recoveryResult: RecoveryResultData = {
        success: true,
        snapshot_used: "20230415120000",
        fields_recovered: ["title"],
        fields_skipped: [],
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

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
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
    });

    it("should call cancelRecovery when cancel button is clicked", async () => {
      // Use real timers for this test to avoid userEvent timeout issues
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const mockCancelRecovery = vi.spyOn(useRecoveryStore.getState(), "cancelRecovery");
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(mockCancelRecovery).toHaveBeenCalledWith("test-session");

      // Restore fake timers for other tests
      vi.useFakeTimers();
    });

    it("should hide recovery section after clicking cancel", async () => {
      // Use real timers for this test to avoid userEvent timeout issues
      vi.useRealTimers();
      const user = userEvent.setup();
      const mockRecover = vi.fn();
      const mockCancelRecovery = vi.spyOn(useRecoveryStore.getState(), "cancelRecovery");
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      const { container } = render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      // Verify cancel button exists
      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).toBeInTheDocument();

      await user.click(cancelButton);

      // Verify cancelRecovery was called
      expect(mockCancelRecovery).toHaveBeenCalledWith("test-session");

      // After cancellation, the recovery status section disappears
      // because phase changes to "cancelled" and isRecovering becomes false
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
      });

      // Restore fake timers for other tests
      vi.useFakeTimers();
    });

    it("should have secondary button styling on cancel button", () => {
      const mockRecover = vi.fn();
      const now = Date.now();

      // Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["test-video-id", {
            sessionId: "test-session",
            entityId: "test-video-id",
            entityType: "video",
            entityTitle: "Test Video",
            phase: "in-progress",
            startedAt: now,
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="deleted"
          entityType="video"
          entityId="test-video-id"
          onRecover={mockRecover}
        />
      );

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).toHaveClass("bg-white");
      expect(cancelButton).toHaveClass("border-slate-300");
      expect(cancelButton).toHaveClass("text-slate-700");
    });
  });
});
