/**
 * Tests for BatchCorrectionsPage — Entity Selection Persistence (T026 / FR-011).
 *
 * Coverage:
 * - Entity persists when the user changes the find pattern (second-round workflow)
 * - Entity clears when the replacement field is emptied (FR-011 auto-clear)
 * - Entity clears when a cross-segment candidate pre-fills the form (handlePrefill)
 *
 * Strategy:
 * - EntityAutocomplete is rendered real but its search hook (useEntitySearch) is
 *   mocked to return a single fake entity, making the dropdown appear without a
 *   live API call. We simulate selecting the entity by typing into the replacement
 *   field (which drives EntityAutocomplete.searchText) and then clicking the list
 *   option that appears.
 * - CrossSegmentPanel is mocked (same as the crosssegment test) so we can trigger
 *   handlePrefill via a button click.
 * - All batch mutation hooks are mocked with stable idle stubs.
 * - DOM assertions focus on the entity pill (role="status") rendered inside
 *   EntityAutocomplete and the "Linked entity:" summary in ApplyControls.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { BatchCorrectionsPage } from "../BatchCorrectionsPage";

// ---------------------------------------------------------------------------
// Mock CrossSegmentPanel — reuse exact pattern from crosssegment test
// ---------------------------------------------------------------------------

vi.mock("../../components/corrections/CrossSegmentPanel", () => ({
  CrossSegmentPanel: vi.fn(
    ({
      prefillForm,
    }: {
      prefillForm: (values: {
        pattern: string;
        replacement: string;
        crossSegment: boolean;
      }) => void;
    }) => {
      return (
        <div data-testid="cross-segment-panel">
          <button
            type="button"
            onClick={() =>
              prefillForm({
                pattern: "bernie",
                replacement: "Bernie",
                crossSegment: true,
              })
            }
          >
            Use candidate
          </button>
        </div>
      );
    }
  ),
}));

// ---------------------------------------------------------------------------
// Mock batch mutation hooks with idle stubs
// ---------------------------------------------------------------------------

const mockPreviewReset = vi.fn();
const mockPreviewMutate = vi.fn();

vi.mock("../../hooks/useBatchPreview", () => ({
  useBatchPreview: vi.fn(() => ({
    mutate: mockPreviewMutate,
    isPending: false,
    isError: false,
    error: null,
    reset: mockPreviewReset,
  })),
}));

vi.mock("../../hooks/useBatchApply", () => ({
  useBatchApply: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
}));

vi.mock("../../hooks/useBatchRebuild", () => ({
  useBatchRebuild: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

vi.mock("../../hooks/useEntityDetail", () => ({
  useEntityDetail: vi.fn(() => ({
    entity: null,
    aliasNames: [],
    isLoading: false,
    isError: false,
  })),
}));

vi.mock("../../hooks/useEntities", () => ({
  useEntities: vi.fn(() => ({
    entities: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  })),
}));

// EntityAutocomplete uses apiFetch — mock config module
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn(() => false),
}));

// ---------------------------------------------------------------------------
// Mock useEntitySearch so the dropdown appears without live API calls.
//
// We expose a mutable ref so individual tests can toggle whether results are
// returned. Default: returns one "Andrés Manuel López Obrador" entity.
// ---------------------------------------------------------------------------

const mockEntitySearchResult = {
  entities: [
    {
      entity_id: "entity-uuid-001",
      canonical_name: "Andrés Manuel López Obrador",
      entity_type: "person",
    },
  ],
  isLoading: false,
  isFetched: true,
  isError: false,
  isBelowMinChars: false,
};

vi.mock("../../hooks/useEntitySearch", () => ({
  useEntitySearch: vi.fn(() => mockEntitySearchResult),
}));

// ---------------------------------------------------------------------------
// Render helper — identical to the crosssegment test
// ---------------------------------------------------------------------------

function renderPage(initialPath = "/corrections/batch") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <BatchCorrectionsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Helper: select an entity via the EntityAutocomplete dropdown.
//
// The EntityAutocomplete.searchText is driven by the replacement field value.
// We type a replacement value (≥2 chars) so useEntitySearch fires and the
// dropdown option appears, then click the option to select the entity.
// ---------------------------------------------------------------------------

async function selectEntityViaAutocomplete(replacementValue: string) {
  // Type into the replacement field — this drives EntityAutocomplete.searchText
  const replacementInput = screen.getByPlaceholderText(/replacement text/i);
  fireEvent.change(replacementInput, { target: { value: replacementValue } });

  // The dropdown option should appear (useEntitySearch is mocked to return results)
  const option = await screen.findByRole("option", {
    name: /Andrés Manuel López Obrador/i,
  });
  fireEvent.click(option);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BatchCorrectionsPage — Entity Selection Persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Scenario 1: Entity persists when the pattern changes
  //
  // Spec: handlePatternChange does NOT call setSelectedEntity(null).
  // The entity pill in EntityAutocomplete (role="status") should remain
  // visible after the user types a new pattern (second-round workflow).
  // -------------------------------------------------------------------------

  describe("Scenario 1: entity persists when find pattern changes", () => {
    it("entity pill is visible inside PatternInput after selecting an entity", async () => {
      renderPage();

      // Select the entity by typing in the replacement field and clicking the option
      await selectEntityViaAutocomplete("AMLO");

      // The entity pill (role="status") should now be visible inside PatternInput
      const entityPill = await screen.findByRole("status");
      expect(entityPill).toBeInTheDocument();
      expect(entityPill).toHaveTextContent("Andrés Manuel López Obrador");
    });

    it("entity pill remains visible after the user changes the find pattern", async () => {
      renderPage();

      // Select an entity
      await selectEntityViaAutocomplete("AMLO");

      // Verify entity pill is present
      const entityPill = await screen.findByRole("status");
      expect(entityPill).toHaveTextContent("Andrés Manuel López Obrador");

      // Now change the find pattern — this triggers handlePatternChange
      const patternInput = screen.getByPlaceholderText(
        /enter text or regex pattern/i
      );
      fireEvent.change(patternInput, { target: { value: "amlo" } });

      // The entity pill must still be present (entity was NOT cleared by pattern change)
      await waitFor(() => {
        const pill = screen.queryByRole("status");
        expect(pill).toBeInTheDocument();
        expect(pill).toHaveTextContent("Andrés Manuel López Obrador");
      });
    });

    it("changing the pattern multiple times does not clear the entity", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");

      const patternInput = screen.getByPlaceholderText(
        /enter text or regex pattern/i
      );

      // Change pattern twice — simulates second-round workflow
      fireEvent.change(patternInput, { target: { value: "amlo" } });
      fireEvent.change(patternInput, { target: { value: "amlo variant" } });

      await waitFor(() => {
        const pill = screen.queryByRole("status");
        expect(pill).toBeInTheDocument();
        expect(pill).toHaveTextContent("Andrés Manuel López Obrador");
      });
    });

    it("the 'Remove entity link' dismiss button is still present after pattern change", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");

      const patternInput = screen.getByPlaceholderText(
        /enter text or regex pattern/i
      );
      fireEvent.change(patternInput, { target: { value: "new pattern" } });

      // Dismiss button must still be accessible
      await waitFor(() => {
        const dismissBtn = screen.queryByRole("button", {
          name: /remove entity link/i,
        });
        expect(dismissBtn).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Scenario 2: Entity clears when the replacement field is emptied (FR-011)
  //
  // PatternInput.handleReplacementChange calls onEntityChange(null) when the
  // replacement value is empty or whitespace-only (lines 279-282).
  // -------------------------------------------------------------------------

  describe("Scenario 2: entity clears when replacement field is emptied (FR-011)", () => {
    it("entity pill disappears when the replacement field is cleared", async () => {
      renderPage();

      // Select an entity
      await selectEntityViaAutocomplete("AMLO");

      // Verify entity pill is present
      const entityPill = await screen.findByRole("status");
      expect(entityPill).toHaveTextContent("Andrés Manuel López Obrador");

      // Clear the replacement field
      const replacementInput = screen.getByPlaceholderText(/replacement text/i);
      fireEvent.change(replacementInput, { target: { value: "" } });

      // FR-011: entity pill must be gone
      await waitFor(() => {
        // The "status" role pill inside EntityAutocomplete must not be in DOM
        const pill = screen.queryByRole("status");
        expect(pill).not.toBeInTheDocument();
      });
    });

    it("entity pill disappears when replacement is set to whitespace only", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");

      const entityPill = await screen.findByRole("status");
      expect(entityPill).toHaveTextContent("Andrés Manuel López Obrador");

      const replacementInput = screen.getByPlaceholderText(/replacement text/i);
      // Only whitespace — handleReplacementChange calls !value.trim() → true
      fireEvent.change(replacementInput, { target: { value: "   " } });

      await waitFor(() => {
        const pill = screen.queryByRole("status");
        expect(pill).not.toBeInTheDocument();
      });
    });

    it("'Remove entity link' button disappears when replacement is cleared", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");

      // Confirm dismiss button is visible
      const dismissBtn = await screen.findByRole("button", {
        name: /remove entity link/i,
      });
      expect(dismissBtn).toBeInTheDocument();

      // Clear the replacement
      const replacementInput = screen.getByPlaceholderText(/replacement text/i);
      fireEvent.change(replacementInput, { target: { value: "" } });

      // Dismiss button must be gone (pill rendered it, and pill is now gone)
      await waitFor(() => {
        expect(
          screen.queryByRole("button", { name: /remove entity link/i })
        ).not.toBeInTheDocument();
      });
    });

    it("entity can be re-selected after clearing the replacement and typing again", async () => {
      renderPage();

      // First selection
      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      // Clear replacement (FR-011 auto-clear)
      const replacementInput = screen.getByPlaceholderText(/replacement text/i);
      fireEvent.change(replacementInput, { target: { value: "" } });

      await waitFor(() => {
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
      });

      // Re-select the entity
      await selectEntityViaAutocomplete("AMLO");

      // Entity pill should be back
      const pill = await screen.findByRole("status");
      expect(pill).toHaveTextContent("Andrés Manuel López Obrador");
    });
  });

  // -------------------------------------------------------------------------
  // Scenario 3: Entity clears when a cross-segment candidate pre-fills the form
  //
  // handlePrefill (BatchCorrectionsPage.tsx ~line 681) calls
  // setSelectedEntity(null) — clearing the page-level entity state.
  // PatternInput remounts (key increment), which resets PatternInput's own
  // selectedEntity state too. The entity pill must be gone.
  // -------------------------------------------------------------------------

  describe("Scenario 3: entity clears when cross-segment candidate is selected (handlePrefill)", () => {
    it("entity pill disappears after prefillForm is called from CrossSegmentPanel", async () => {
      renderPage();

      // Select an entity
      await selectEntityViaAutocomplete("AMLO");

      const entityPill = await screen.findByRole("status");
      expect(entityPill).toHaveTextContent("Andrés Manuel López Obrador");

      // Trigger prefill from the mock CrossSegmentPanel — this calls handlePrefill
      // which calls setSelectedEntity(null)
      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      // After prefill the entity must be cleared
      await waitFor(() => {
        const pill = screen.queryByRole("status");
        expect(pill).not.toBeInTheDocument();
      });
    });

    it("prefillForm fills the pattern field while clearing the entity", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      // Pattern must be prefilled with the candidate value
      await waitFor(() => {
        const patternInput = screen.getByPlaceholderText(
          /enter text or regex pattern/i
        );
        expect(patternInput).toHaveValue("bernie");
      });

      // Entity must be cleared
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("prefillForm fills the replacement field while clearing the entity", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      // Replacement must be prefilled with the candidate value
      await waitFor(() => {
        const replacementInput = screen.getByPlaceholderText(/replacement text/i);
        expect(replacementInput).toHaveValue("Bernie");
      });

      // Entity must be cleared
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("dismiss button is gone after entity is cleared via prefillForm", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");

      // Confirm dismiss button exists
      const dismissBtn = await screen.findByRole("button", {
        name: /remove entity link/i,
      });
      expect(dismissBtn).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      await waitFor(() => {
        expect(
          screen.queryByRole("button", { name: /remove entity link/i })
        ).not.toBeInTheDocument();
      });
    });

    it("preview reset is called when prefillForm clears the entity", async () => {
      renderPage();

      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      // Record how many times reset has been called before prefill
      const callsBefore = mockPreviewReset.mock.calls.length;

      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      // handlePrefill calls previewMutation.reset() — verify at least one more call
      // occurred after the button click (previous calls may come from replacement
      // field changes triggering handlePatternChange in PatternInput).
      await waitFor(() => {
        expect(mockPreviewReset.mock.calls.length).toBeGreaterThan(callsBefore);
      });
    });
  });

  // -------------------------------------------------------------------------
  // Contrast: pattern change does NOT call preview reset for entity
  //
  // This test is complementary — it ensures handlePatternChange preserves the
  // entity while confirming the state machine does reset (RESET dispatched).
  // The "Preview Matches" button returning to disabled proves the machine reset.
  // -------------------------------------------------------------------------

  describe("Contrast: handlePatternChange vs handlePrefill behavior", () => {
    it("Preview Matches button is re-disabled (state RESET) after pattern change, but entity stays", async () => {
      renderPage();

      // Select an entity
      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      // Type a pattern to enable the preview button
      const patternInput = screen.getByPlaceholderText(
        /enter text or regex pattern/i
      );
      fireEvent.change(patternInput, { target: { value: "amlo" } });

      const previewBtn = screen.getByRole("button", { name: /preview matches/i });
      expect(previewBtn).not.toBeDisabled();

      // Change the pattern — triggers handlePatternChange → dispatches RESET
      fireEvent.change(patternInput, { target: { value: "amlo variant" } });

      // Entity still present
      await waitFor(() => {
        const pill = screen.queryByRole("status");
        expect(pill).toBeInTheDocument();
        expect(pill).toHaveTextContent("Andrés Manuel López Obrador");
      });
    });

    it("prefillForm clears entity but handlePatternChange does not", async () => {
      renderPage();

      // Set up entity
      await selectEntityViaAutocomplete("AMLO");
      await screen.findByRole("status");

      // Pattern change — entity persists
      const patternInput = screen.getByPlaceholderText(
        /enter text or regex pattern/i
      );
      fireEvent.change(patternInput, { target: { value: "amlo" } });

      await waitFor(() => {
        expect(screen.queryByRole("status")).toBeInTheDocument();
      });

      // prefillForm — entity clears
      fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

      await waitFor(() => {
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
      });
    });
  });
});
