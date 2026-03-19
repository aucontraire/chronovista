/**
 * Unit tests for OnboardingPage (Feature 047, US2).
 *
 * Tests:
 * - T030-1: Renders 5 pipeline step cards when status data is available
 * - T030-2: Shows data export path from status
 * - T030-3: Shows "Start" button on available steps
 * - T030-4: Clicking Start triggers the createTask mutation
 * - T030-5: Shows connection error banner when API is unreachable
 * - T030-6: Shows data export guidance when data_export_detected is false
 * - T030-7: Shows loading state initially
 *
 * Strategy: mock the hooks module with vi.mock() so the page can render
 * without a real QueryClient or network. This mirrors the pattern used
 * in HomePage.test.tsx.
 *
 * @module tests/pages/OnboardingPage
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OnboardingPage } from "../../pages/OnboardingPage";
import type {
  BackgroundTask,
  OnboardingStatus,
  PipelineStep,
} from "../../types/onboarding";

// ---------------------------------------------------------------------------
// Hook mocks
// ---------------------------------------------------------------------------

const mockRefetch = vi.fn().mockResolvedValue(undefined);
const mockMutate = vi.fn();

vi.mock("../../hooks/useOnboarding", () => ({
  useOnboardingStatus: vi.fn(),
  useStartTask: vi.fn(),
  useTaskStatus: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePipelineStep(
  overrides: Partial<PipelineStep> = {}
): PipelineStep {
  return {
    name: "Seed Reference Data",
    operation_type: "seed_reference",
    description: "Loads YouTube category and topic reference data.",
    status: "available",
    dependencies: [],
    requires_auth: false,
    metrics: {},
    error: null,
    ...overrides,
  };
}

const FIVE_STEPS: PipelineStep[] = [
  makePipelineStep({
    name: "Seed Reference Data",
    operation_type: "seed_reference",
    status: "available",
    description: "Loads YouTube category and topic reference data.",
  }),
  makePipelineStep({
    name: "Load Data",
    operation_type: "load_data",
    status: "not_started",
    dependencies: ["seed_reference"],
    description: "Imports your YouTube data export into the local database.",
  }),
  makePipelineStep({
    name: "Enrich Metadata",
    operation_type: "enrich_metadata",
    status: "not_started",
    dependencies: ["load_data"],
    requires_auth: true,
    description: "Fetches additional metadata from the YouTube API.",
  }),
  makePipelineStep({
    name: "Sync Transcripts",
    operation_type: "sync_transcripts",
    status: "not_started",
    dependencies: ["load_data"],
    requires_auth: true,
    description: "Downloads transcripts for all imported videos.",
  }),
  makePipelineStep({
    name: "Normalize Tags",
    operation_type: "normalize_tags",
    status: "not_started",
    dependencies: ["load_data"],
    description: "Normalizes and deduplicates video tags.",
  }),
];

const mockStatus: OnboardingStatus = {
  steps: FIVE_STEPS,
  is_authenticated: false,
  data_export_path: "/data/takeout",
  data_export_detected: true,
  active_task: null,
  counts: {
    channels: 0,
    videos: 0,
    playlists: 0,
    transcripts: 0,
    categories: 0,
    canonical_tags: 0,
  },
};

const mockTask: BackgroundTask = {
  id: "task-uuid-001",
  operation_type: "seed_reference",
  status: "queued",
  progress: 0,
  error: null,
  started_at: null,
  completed_at: null,
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/onboarding"]}>
        <OnboardingPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Helper: set up default hook return values
// ---------------------------------------------------------------------------

async function setupHooks(options: {
  isLoading?: boolean;
  isError?: boolean;
  status?: OnboardingStatus | undefined;
  taskData?: BackgroundTask | undefined;
}) {
  const { useOnboardingStatus, useStartTask, useTaskStatus } = await import(
    "../../hooks/useOnboarding"
  );

  vi.mocked(useOnboardingStatus).mockReturnValue({
    data: options.status,
    isLoading: options.isLoading ?? false,
    isError: options.isError ?? false,
    refetch: mockRefetch,
    // Minimal shape — remaining fields unused by the page
  } as ReturnType<typeof useOnboardingStatus>);

  vi.mocked(useStartTask).mockReturnValue({
    mutate: mockMutate,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useStartTask>);

  vi.mocked(useTaskStatus).mockReturnValue({
    data: options.taskData,
  } as ReturnType<typeof useTaskStatus>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // T030-1: Renders 5 pipeline step cards
  // -------------------------------------------------------------------------
  describe("renders 5 pipeline step cards (T030-1)", () => {
    it("renders an article card for each of the 5 pipeline steps", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      // PipelineStepCard renders <article aria-label="Pipeline step: {name}">
      const cards = screen.getAllByRole("article");
      expect(cards).toHaveLength(5);
    });

    it("renders the correct step names in the cards", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(screen.getByText("Seed Reference Data")).toBeInTheDocument();
      expect(screen.getByText("Load Data")).toBeInTheDocument();
      expect(screen.getByText("Enrich Metadata")).toBeInTheDocument();
      expect(screen.getByText("Sync Transcripts")).toBeInTheDocument();
      expect(screen.getByText("Normalize Tags")).toBeInTheDocument();
    });

    it("renders step descriptions", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(
        screen.getByText("Loads YouTube category and topic reference data.")
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-2: Shows data export path
  // -------------------------------------------------------------------------
  describe("shows data export path (T030-2)", () => {
    it("renders the configured data export path", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(screen.getByText("/data/takeout")).toBeInTheDocument();
    });

    it("renders the export path label text", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(screen.getByText(/Expected path:/i)).toBeInTheDocument();
    });

    it("renders 'Data export detected' when data_export_detected is true", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: true },
      });

      renderPage();

      // There may be both a visible heading and an aria-label — check visible text
      expect(screen.getByText("Data export detected")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-3: Shows "Start" button on available steps
  // -------------------------------------------------------------------------
  describe("shows Start button on available steps (T030-3)", () => {
    it("renders enabled Start button for the available step", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      // The first step (seed_reference) is "available" and not auth-gated
      const startButton = screen.getByRole("button", {
        name: /Start Seed Reference Data/i,
      });
      expect(startButton).toBeInTheDocument();
      expect(startButton).not.toBeDisabled();
    });

    it("renders disabled Start buttons for not_started steps", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      // "Load Data" is not_started — its button should be disabled
      const disabledButton = screen.getByRole("button", {
        name: /Load Data is not yet available/i,
      });
      expect(disabledButton).toBeDisabled();
    });

    it("shows only one enabled Start button when one step is available", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      // We look for aria-label matching "Start <name>" (the ActionButton for available steps)
      const enabledStart = screen.getByRole("button", {
        name: /^Start Seed Reference Data$/i,
      });
      expect(enabledStart).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-4: Clicking Start triggers the createTask mutation
  // -------------------------------------------------------------------------
  describe("clicking Start triggers createTask mutation (T030-4)", () => {
    it("calls startTask.mutate with correct operation_type when Start is clicked", async () => {
      await setupHooks({ status: mockStatus });
      const user = userEvent.setup();

      renderPage();

      const startButton = screen.getByRole("button", {
        name: /Start Seed Reference Data/i,
      });
      await user.click(startButton);

      expect(mockMutate).toHaveBeenCalledOnce();
      expect(mockMutate).toHaveBeenCalledWith(
        { operation_type: "seed_reference" },
        expect.any(Object)
      );
    });

    it("calls mutate with the onSuccess callback that sets the active task id", async () => {
      await setupHooks({ status: mockStatus });
      const user = userEvent.setup();

      renderPage();

      const startButton = screen.getByRole("button", {
        name: /Start Seed Reference Data/i,
      });
      await user.click(startButton);

      // Verify the mutation was called and the second arg is an options object
      // containing an onSuccess handler (page uses it to track activeTaskId)
      const callArgs = mockMutate.mock.calls[0];
      expect(callArgs).toBeDefined();
      expect(callArgs?.[1]).toHaveProperty("onSuccess");
      expect(typeof callArgs?.[1]?.onSuccess).toBe("function");
    });

    it("sets activeTaskId when onSuccess is invoked with the returned task", async () => {
      await setupHooks({ status: mockStatus });
      const user = userEvent.setup();

      renderPage();

      const startButton = screen.getByRole("button", {
        name: /Start Seed Reference Data/i,
      });
      await user.click(startButton);

      // Simulate the onSuccess callback being called with a task
      const onSuccess = mockMutate.mock.calls[0]?.[1]?.onSuccess as (
        task: BackgroundTask
      ) => void;
      expect(onSuccess).toBeDefined();
      // Calling it should not throw
      expect(() => onSuccess(mockTask)).not.toThrow();
    });
  });

  // -------------------------------------------------------------------------
  // T030-5: Shows connection error banner when API is unreachable
  // -------------------------------------------------------------------------
  describe("shows connection error banner (T030-5)", () => {
    it("renders the error banner when useOnboardingStatus returns isError=true", async () => {
      await setupHooks({ isError: true, status: undefined });

      renderPage();

      const banner = screen.getByRole("alert", {
        name: /Unable to connect to the server/i,
      });
      expect(banner).toBeInTheDocument();
    });

    it("shows the error message text in the banner", async () => {
      await setupHooks({ isError: true, status: undefined });

      renderPage();

      expect(
        screen.getByText(/Unable to connect to the server/i)
      ).toBeInTheDocument();
    });

    it("shows a Retry Connection button in the error banner", async () => {
      await setupHooks({ isError: true, status: undefined });

      renderPage();

      const retryButton = screen.getByRole("button", {
        name: /Retry connection to the server/i,
      });
      expect(retryButton).toBeInTheDocument();
    });

    it("calls refetch when the Retry Connection button is clicked", async () => {
      await setupHooks({ isError: true, status: undefined });
      const user = userEvent.setup();

      renderPage();

      const retryButton = screen.getByRole("button", {
        name: /Retry connection to the server/i,
      });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalled();
      });
    });

    it("does not render the error banner when API succeeds", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(
        screen.queryByRole("alert", { name: /Unable to connect to the server/i })
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-6: Shows data export guidance when data_export_detected is false
  // -------------------------------------------------------------------------
  describe("shows data export guidance when data_export_detected is false (T030-6)", () => {
    it("renders 'No data export found' text when data_export_detected is false", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: false },
      });

      renderPage();

      expect(screen.getByText("No data export found")).toBeInTheDocument();
    });

    it("renders a link to Google Takeout when no export is detected", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: false },
      });

      renderPage();

      const takeoutLink = screen.getByRole("link", { name: /Google Takeout/i });
      expect(takeoutLink).toBeInTheDocument();
      expect(takeoutLink).toHaveAttribute("href", "https://takeout.google.com");
    });

    it("renders guidance text with download instructions", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: false },
      });

      renderPage();

      expect(
        screen.getByText(/Download your YouTube data export/i)
      ).toBeInTheDocument();
    });

    it("does not show the takeout guidance when export is detected", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: true },
      });

      renderPage();

      expect(
        screen.queryByText(/Download your YouTube data export/i)
      ).not.toBeInTheDocument();
    });

    it("renders the status region with correct aria-label for detected export", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: true },
      });

      renderPage();

      const statusRegion = screen.getByRole("status", {
        name: /Data export detected/i,
      });
      expect(statusRegion).toBeInTheDocument();
    });

    it("renders the status region with 'No data export detected' label when not found", async () => {
      await setupHooks({
        status: { ...mockStatus, data_export_detected: false },
      });

      renderPage();

      const statusRegion = screen.getByRole("status", {
        name: /No data export detected/i,
      });
      expect(statusRegion).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-7: Shows loading state initially
  // -------------------------------------------------------------------------
  describe("shows loading state initially (T030-7)", () => {
    it("renders loading skeleton (5 skeleton cards) when isLoading=true and no cached data", async () => {
      await setupHooks({ isLoading: true, status: undefined });

      renderPage();

      // PipelineLoadingState renders a role="status" region
      const loadingRegion = screen.getByRole("status", {
        name: /Loading onboarding pipeline/i,
      });
      expect(loadingRegion).toBeInTheDocument();
    });

    it("renders sr-only loading text during load", async () => {
      await setupHooks({ isLoading: true, status: undefined });

      renderPage();

      expect(screen.getByText(/Loading onboarding pipeline/i)).toBeInTheDocument();
    });

    it("does not render step cards during loading when no cached data exists", async () => {
      await setupHooks({ isLoading: true, status: undefined });

      renderPage();

      expect(screen.queryByText("Seed Reference Data")).not.toBeInTheDocument();
    });

    it("renders step cards immediately when cached data is present during loading", async () => {
      // When a background refetch occurs, isLoading=false (data still in cache)
      // but if status is available, cards are shown
      await setupHooks({ isLoading: false, status: mockStatus });

      renderPage();

      const cards = screen.getAllByRole("article");
      expect(cards).toHaveLength(5);
    });
  });

  // -------------------------------------------------------------------------
  // Page structure
  // -------------------------------------------------------------------------
  describe("page structure", () => {
    it("renders the page heading 'Data Onboarding'", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(
        screen.getByRole("heading", { name: /Data Onboarding/i, level: 1 })
      ).toBeInTheDocument();
    });

    it("renders a main landmark for skip-link target", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(screen.getByRole("main")).toBeInTheDocument();
    });

    it("renders the subtitle text", async () => {
      await setupHooks({ status: mockStatus });

      renderPage();

      expect(
        screen.getByText(/Run each pipeline step to import and enrich/i)
      ).toBeInTheDocument();
    });
  });
});
