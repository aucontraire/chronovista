/**
 * Tests for PipelineStepCard Component (T029)
 *
 * Covers:
 * - Step name and description rendering
 * - Status badge for every status variant
 * - Action button states (Start, Running..., Retry, disabled)
 * - Auth required badge when requires_auth and not authenticated
 * - Metrics display when step is completed
 * - Inline error message
 * - ProgressBar when running with an active task
 * - Dependency explanation when blocked
 * - Callback wiring (onStart, onRetry)
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PipelineStepCard } from "../../../components/onboarding/PipelineStepCard";
import type {
  BackgroundTask,
  OperationType,
  PipelineStep,
} from "../../../types/onboarding";

// ---------------------------------------------------------------------------
// Mock data helpers
// ---------------------------------------------------------------------------

function makeStep(overrides: Partial<PipelineStep> = {}): PipelineStep {
  return {
    name: "Load Data",
    operation_type: "load_data" as OperationType,
    description: "Imports channels, videos, and playlists from your export.",
    status: "available",
    dependencies: [],
    requires_auth: false,
    metrics: {},
    error: null,
    ...overrides,
  };
}

function makeTask(overrides: Partial<BackgroundTask> = {}): BackgroundTask {
  return {
    id: "task-001",
    operation_type: "load_data" as OperationType,
    status: "running",
    progress: 45,
    error: null,
    started_at: "2026-03-19T10:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

const defaultProps = {
  activeTask: null as BackgroundTask | null,
  isAuthenticated: true,
  onStart: vi.fn(),
  onRetry: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PipelineStepCard", () => {
  describe("step name and description", () => {
    it("renders the step name as a heading", () => {
      render(
        <PipelineStepCard step={makeStep()} {...defaultProps} />
      );

      expect(screen.getByRole("heading", { name: "Load Data" })).toBeInTheDocument();
    });

    it("renders the step description", () => {
      render(
        <PipelineStepCard step={makeStep()} {...defaultProps} />
      );

      expect(
        screen.getByText(
          "Imports channels, videos, and playlists from your export."
        )
      ).toBeInTheDocument();
    });
  });

  describe("status badge", () => {
    it("shows 'Not started' badge for not_started status", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "not_started" })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByLabelText("Status: Not started")
      ).toBeInTheDocument();
    });

    it("shows 'Available' badge for available status", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available" })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByLabelText("Status: Available")
      ).toBeInTheDocument();
    });

    it("shows 'Running' badge for running status", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "running" })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByLabelText("Status: Running")
      ).toBeInTheDocument();
    });

    it("shows 'Completed' badge for completed status", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "completed" })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByLabelText("Status: Completed")
      ).toBeInTheDocument();
    });

    it("shows 'Blocked' badge for blocked status", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "blocked" })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByLabelText("Status: Blocked")
      ).toBeInTheDocument();
    });
  });

  describe("action button — Start", () => {
    it("shows an enabled Start button when step is available", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available" })}
          {...defaultProps}
        />
      );

      const button = screen.getByRole("button", { name: /start load data/i });
      expect(button).toBeInTheDocument();
      expect(button).not.toBeDisabled();
      expect(button).toHaveTextContent("Start");
    });

    it("calls onStart with the step's operation_type when Start is clicked", () => {
      const onStart = vi.fn();
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", operation_type: "load_data" })}
          {...defaultProps}
          onStart={onStart}
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start load data/i }));
      expect(onStart).toHaveBeenCalledOnce();
      expect(onStart).toHaveBeenCalledWith("load_data");
    });
  });

  describe("action button — blocked (disabled)", () => {
    it("shows a disabled button when step is blocked", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "blocked" })}
          {...defaultProps}
        />
      );

      const button = screen.getByRole("button", {
        name: /load data is blocked/i,
      });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-disabled", "true");
    });

    it("shows a disabled button when step is not_started", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "not_started" })}
          {...defaultProps}
        />
      );

      const button = screen.getByRole("button", {
        name: /load data is not yet available/i,
      });
      expect(button).toBeDisabled();
    });
  });

  describe("action button — Running", () => {
    it("shows a disabled Running button when step is running", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "running" })}
          {...defaultProps}
        />
      );

      const button = screen.getByRole("button", {
        name: /load data is currently running/i,
      });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).toHaveTextContent("Running");
    });
  });

  describe("action button — Retry", () => {
    it("shows a Retry button when step is completed with an error", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "completed",
            error: "Network timeout during enrichment.",
          })}
          {...defaultProps}
        />
      );

      const button = screen.getByRole("button", { name: /retry load data/i });
      expect(button).toBeInTheDocument();
      expect(button).not.toBeDisabled();
      expect(button).toHaveTextContent("Retry");
    });

    it("calls onRetry with the step's operation_type when Retry is clicked", () => {
      const onRetry = vi.fn();
      render(
        <PipelineStepCard
          step={makeStep({
            name: "Enrich Metadata",
            status: "completed",
            operation_type: "enrich_metadata",
            error: "Service unavailable.",
          })}
          {...defaultProps}
          onRetry={onRetry}
        />
      );

      fireEvent.click(
        screen.getByRole("button", { name: /retry enrich metadata/i })
      );
      expect(onRetry).toHaveBeenCalledOnce();
      expect(onRetry).toHaveBeenCalledWith("enrich_metadata");
    });
  });

  describe("auth required badge", () => {
    it("shows 'Requires Authentication' badge when requires_auth and not authenticated", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", requires_auth: true })}
          activeTask={null}
          isAuthenticated={false}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      expect(
        screen.getByRole("status", {
          name: "Authentication required for this step",
        })
      ).toBeInTheDocument();
      expect(screen.getByText("Requires Authentication")).toBeInTheDocument();
    });

    it("does not show auth badge when authenticated", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", requires_auth: true })}
          activeTask={null}
          isAuthenticated={true}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      expect(
        screen.queryByRole("status", {
          name: "Authentication required for this step",
        })
      ).not.toBeInTheDocument();
    });

    it("does not show auth badge when requires_auth is false", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", requires_auth: false })}
          activeTask={null}
          isAuthenticated={false}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      expect(
        screen.queryByText("Requires Authentication")
      ).not.toBeInTheDocument();
    });

    it("shows a disabled button when requires_auth and not authenticated on available step", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", requires_auth: true })}
          activeTask={null}
          isAuthenticated={false}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      const button = screen.getByRole("button", {
        name: /load data requires authentication/i,
      });
      expect(button).toBeDisabled();
    });
  });

  describe("metrics display", () => {
    it("shows metrics when step is completed and metrics are non-empty", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "completed",
            metrics: { channels_loaded: 12, videos_loaded: 500 },
          })}
          {...defaultProps}
        />
      );

      expect(screen.getByText("channels loaded:")).toBeInTheDocument();
      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText("videos loaded:")).toBeInTheDocument();
      expect(screen.getByText("500")).toBeInTheDocument();
    });

    it("does not show metrics when step is not completed", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "available",
            metrics: { channels_loaded: 12 },
          })}
          {...defaultProps}
        />
      );

      expect(
        screen.queryByText("channels loaded:")
      ).not.toBeInTheDocument();
    });

    it("does not show metrics section when metrics is empty", () => {
      const { container } = render(
        <PipelineStepCard
          step={makeStep({ status: "completed", metrics: {} })}
          {...defaultProps}
        />
      );

      // No dl element rendered for empty metrics
      const dl = container.querySelector("dl");
      expect(dl).not.toBeInTheDocument();
    });
  });

  describe("inline error message", () => {
    it("shows the error message when step.error is set", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "completed",
            error: "Connection refused at 127.0.0.1:8765",
          })}
          {...defaultProps}
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(
        screen.getByText("Connection refused at 127.0.0.1:8765")
      ).toBeInTheDocument();
    });

    it("does not show error alert when step.error is null", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "available", error: null })}
          {...defaultProps}
        />
      );

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("ProgressBar when running", () => {
    it("shows ProgressBar when running with an active task", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "running" })}
          activeTask={makeTask({ progress: 45 })}
          isAuthenticated={true}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      // ProgressBar renders a progressbar role element
      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toBeInTheDocument();
      expect(progressbar).toHaveAttribute("aria-valuenow", "45");
    });

    it("does not show ProgressBar when running but activeTask is null", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "running" })}
          activeTask={null}
          isAuthenticated={true}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });

    it("does not show ProgressBar when step is not running even if activeTask is set", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "completed" })}
          activeTask={makeTask({ progress: 100 })}
          isAuthenticated={true}
          onStart={vi.fn()}
          onRetry={vi.fn()}
        />
      );

      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });
  });

  describe("dependency explanation when blocked", () => {
    it("shows dependency explanation when step is blocked with dependencies", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "blocked",
            dependencies: ["seed_reference", "load_data"],
          })}
          {...defaultProps}
        />
      );

      expect(
        screen.getByText(/requires completion of:/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText("seed reference, load data")
      ).toBeInTheDocument();
    });

    it("does not show dependency explanation when not blocked", () => {
      render(
        <PipelineStepCard
          step={makeStep({
            status: "available",
            dependencies: ["seed_reference"],
          })}
          {...defaultProps}
        />
      );

      expect(
        screen.queryByText(/requires completion of:/i)
      ).not.toBeInTheDocument();
    });

    it("does not show dependency explanation when blocked but dependencies is empty", () => {
      render(
        <PipelineStepCard
          step={makeStep({ status: "blocked", dependencies: [] })}
          {...defaultProps}
        />
      );

      expect(
        screen.queryByText(/requires completion of:/i)
      ).not.toBeInTheDocument();
    });
  });

  describe("article landmark and accessible label", () => {
    it("renders the card as an article with an accessible label", () => {
      render(
        <PipelineStepCard
          step={makeStep({ name: "Seed Reference" })}
          {...defaultProps}
        />
      );

      const article = screen.getByRole("article", {
        name: "Pipeline step: Seed Reference",
      });
      expect(article).toBeInTheDocument();
    });
  });
});
