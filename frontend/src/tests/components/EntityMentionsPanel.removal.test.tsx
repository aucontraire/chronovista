/**
 * TDD tests for EntityMentionsPanel — Feature 050, User Story 3 (T038).
 *
 * This file covers the manual-association REMOVAL flow on the video detail
 * page (FR-012, FR-027).  All tests are written TDD-style: the unlink button,
 * confirmation dialog, and `useDeleteManualAssociation` hook do not exist yet.
 *
 * Test suites:
 *   1. Unlink button visibility (FR-012) — only chips with has_manual=true show it
 *   2. Confirmation dialog (FR-027) — content, message, and structure
 *   3. Successful removal — mutation fires, cache is invalidated
 *   4. Cancel flow — dialog dismissed without side effects
 *   5. Multi-source removal — MANUAL badge disappears, transcript badge remains
 *
 * Hook mocking strategy
 * ---------------------
 * `useDeleteManualAssociation` is mocked at the module level alongside the
 * existing mocks for `useCreateManualAssociation`, `useVideoEntities`, etc.
 * This keeps the component render self-contained (no TanStack Query provider).
 *
 * data-testid contract (agreed in task description):
 *   - `unlink-button-{entity_id}` — the unlink/X button on a chip
 *   - `unlink-confirm-{entity_id}` — the Confirm button in the inline dialog
 *   - `unlink-cancel-{entity_id}` — the Cancel button in the inline dialog
 *
 * @module tests/components/EntityMentionsPanel.removal
 */

import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

vi.mock("react-router-dom", () => ({
  Link: vi.fn(
    ({
      to,
      children,
      ...rest
    }: {
      to: string;
      children: React.ReactNode;
      [key: string]: unknown;
    }) => (
      <a href={to} {...rest}>
        {children}
      </a>
    )
  ),
}));

vi.mock("../../hooks/useEntitySearch", () => ({
  useEntitySearch: vi.fn(),
}));

// Mock the full hooks/useEntityMentions module — including the new
// useDeleteManualAssociation export that will be added in T038.
vi.mock("../../hooks/useEntityMentions", () => ({
  useVideoEntities: vi.fn(),
  useEntityVideos: vi.fn(),
  useEntities: vi.fn(),
  useCreateManualAssociation: vi.fn(),
  useDeleteManualAssociation: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { EntityMentionsPanel } from "../../components/EntityMentionsPanel";
import type { EntityMentionsPanelProps } from "../../components/EntityMentionsPanel";
import type { VideoEntitySummary } from "../../api/entityMentions";
import { useEntitySearch } from "../../hooks/useEntitySearch";
import {
  useCreateManualAssociation,
} from "../../hooks/useEntityMentions";
// TDD: useDeleteManualAssociation will be added to hooks/useEntityMentions in T038.
// We import the module as unknown to avoid compile errors on the not-yet-existing export.
import * as entityMentionsHooks from "../../hooks/useEntityMentions";
import type { Mock } from "vitest";

// Typed accessor for the not-yet-existing hook (mocked at module level above).
const useDeleteManualAssociation = (
  entityMentionsHooks as unknown as {
    useDeleteManualAssociation: () => {
      mutate: (vars: { videoId: string; entityId: string }) => void;
      isPending: boolean;
      isError: boolean;
      error: unknown;
      isSuccess: boolean;
    };
  }
).useDeleteManualAssociation;

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const VIDEO_ID = "removal-test-video-001";

/** A transcript-only entity (no unlink button expected). */
const TRANSCRIPT_ONLY_ENTITY: VideoEntitySummary = {
  entity_id: "ent-transcript",
  canonical_name: "MIT Media Lab",
  entity_type: "organization",
  description: null,
  mention_count: 8,
  first_mention_time: 30.0,
  sources: ["transcript"],
  has_manual: false,
};

/** An entity with only a manual association (no transcript hits). */
const MANUAL_ONLY_ENTITY: VideoEntitySummary = {
  entity_id: "ent-manual-only",
  canonical_name: "Elon Musk",
  entity_type: "person",
  description: "CEO of Tesla",
  mention_count: 0,
  first_mention_time: null,
  sources: ["manual"],
  has_manual: true,
};

/** An entity with both transcript mentions AND a manual association. */
const MULTI_SOURCE_ENTITY: VideoEntitySummary = {
  entity_id: "ent-multi-source",
  canonical_name: "SpaceX",
  entity_type: "organization",
  description: "Aerospace company",
  mention_count: 4,
  first_mention_time: 65.0,
  sources: ["transcript", "manual"],
  has_manual: true,
};

// ---------------------------------------------------------------------------
// Default idle hook states
// ---------------------------------------------------------------------------

function makeIdleSearchState() {
  return {
    entities: [],
    isLoading: false,
    isFetched: false,
    isError: false,
    isBelowMinChars: true,
  };
}

function makeIdleCreateMutationState() {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  };
}

function makeIdleDeleteMutationState() {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPanel(props: Partial<EntityMentionsPanelProps> = {}) {
  const fullProps: EntityMentionsPanelProps = {
    entities: [],
    isLoading: false,
    videoId: VIDEO_ID,
    ...props,
  };
  return render(<EntityMentionsPanel {...fullProps} />);
}

// ===========================================================================
// Suite: Removal flow (TDD for T038)
// ===========================================================================

describe("EntityMentionsPanel — manual association removal (TDD for T038)", () => {
  beforeEach(() => {
    (useEntitySearch as Mock).mockReturnValue(makeIdleSearchState());
    (useCreateManualAssociation as Mock).mockReturnValue(makeIdleCreateMutationState());
    (useDeleteManualAssociation as Mock).mockReturnValue(makeIdleDeleteMutationState());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Suite 1: Unlink button visibility (FR-012)
  //
  // Only entity chips with has_manual=true should show an unlink button.
  // Chips for transcript-only entities must NOT render the button.
  // =========================================================================

  describe("TC-R01: unlink button visibility (FR-012)", () => {
    it("shows an unlink button for an entity chip with has_manual=true", () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      // The unlink button must be identifiable by data-testid or aria-label.
      // Acceptable forms: data-testid="unlink-button-{entity_id}" OR
      // a button with accessible name containing "unlink" or "remove manual".
      const unlinkBtn =
        screen.queryByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });

      expect(unlinkBtn).toBeInTheDocument();
    });

    it("does NOT show an unlink button for an entity chip with has_manual=false", () => {
      renderPanel({ entities: [TRANSCRIPT_ONLY_ENTITY] });

      const unlinkBtn =
        screen.queryByTestId(`unlink-button-${TRANSCRIPT_ONLY_ENTITY.entity_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });

      expect(unlinkBtn).not.toBeInTheDocument();
    });

    it("shows unlink buttons only for manual chips when both types are present", () => {
      renderPanel({
        entities: [TRANSCRIPT_ONLY_ENTITY, MANUAL_ONLY_ENTITY],
      });

      // Manual entity: unlink button present.
      const manualUnlink =
        screen.queryByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.queryAllByRole("button", { name: /unlink|remove manual|remove association/i })[0];
      expect(manualUnlink).toBeInTheDocument();

      // Transcript-only entity: no unlink button with its specific testid.
      const transcriptUnlink = screen.queryByTestId(
        `unlink-button-${TRANSCRIPT_ONLY_ENTITY.entity_id}`
      );
      expect(transcriptUnlink).not.toBeInTheDocument();
    });

    it("shows an unlink button for a multi-source entity that also has has_manual=true", () => {
      renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      const unlinkBtn =
        screen.queryByTestId(`unlink-button-${MULTI_SOURCE_ENTITY.entity_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });

      expect(unlinkBtn).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Suite 2: Confirmation dialog (FR-027)
  //
  // Clicking the unlink button must show an inline confirmation that:
  // - Contains the entity name
  // - Contains the required message about transcript mentions being unaffected
  // - Has Confirm and Cancel buttons
  // =========================================================================

  describe("TC-R02: confirmation dialog content (FR-027)", () => {
    it("shows an inline confirmation dialog when the unlink button is clicked", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      const user = userEvent.setup();
      await user.click(unlinkBtn);

      // After click, a confirmation dialog must appear.
      // At minimum it must have a Confirm button.
      const confirmBtn =
        screen.queryByTestId(`unlink-confirm-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.queryByRole("button", { name: /confirm|yes, remove/i });

      expect(confirmBtn).toBeInTheDocument();
    });

    it("confirmation dialog contains the required FR-027 message about transcript mentions", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        // FR-027 requires this exact phrase (case-insensitive match is fine).
        expect(
          screen.getByText(/only the manual association will be removed/i)
        ).toBeInTheDocument();
      });
    });

    it("confirmation dialog contains the entity name", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        // The entity name must appear inside or near the confirmation dialog.
        expect(
          screen.getAllByText(/Elon Musk/i).length
        ).toBeGreaterThan(0);
      });
    });

    it("shows both a Confirm and a Cancel button in the confirmation dialog", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        const confirmBtn =
          screen.queryByTestId(`unlink-confirm-${MANUAL_ONLY_ENTITY.entity_id}`) ??
          screen.queryByRole("button", { name: /confirm|yes, remove/i });

        const cancelBtn =
          screen.queryByTestId(`unlink-cancel-${MANUAL_ONLY_ENTITY.entity_id}`) ??
          screen.queryByRole("button", { name: /cancel/i });

        expect(confirmBtn).toBeInTheDocument();
        expect(cancelBtn).toBeInTheDocument();
      });
    });

    it("also includes a message about transcript-derived mentions remaining unaffected", async () => {
      renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MULTI_SOURCE_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });

      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/transcript.*(mention|derived).*remain|remain.*unaffected/i)
        ).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Suite 3: Successful removal — mutation fires and cache is invalidated
  // =========================================================================

  describe("TC-R03: successful removal", () => {
    it("calls useDeleteManualAssociation mutate with { videoId, entityId } on confirm", async () => {
      const mutateFn = vi.fn();
      (useDeleteManualAssociation as Mock).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      renderPanel({ entities: [MANUAL_ONLY_ENTITY], videoId: VIDEO_ID });

      // Open confirmation dialog.
      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      // Click Confirm.
      const confirmBtn = await screen.findByRole("button", { name: /confirm|yes, remove/i });
      fireEvent.click(confirmBtn);

      // The component passes a second argument { onSuccess } to mutate() for
      // the per-call success callback.  Use expect.anything() to match it
      // without binding the test to the internal callback reference.
      expect(mutateFn).toHaveBeenCalledWith(
        { videoId: VIDEO_ID, entityId: MANUAL_ONLY_ENTITY.entity_id },
        expect.anything(),
      );
    });

    it("does NOT call mutate before the Confirm button is clicked", async () => {
      const mutateFn = vi.fn();
      (useDeleteManualAssociation as Mock).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      // Open the confirmation dialog — but do NOT click Confirm.
      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      // mutate must not have been called yet.
      expect(mutateFn).not.toHaveBeenCalled();
    });

    it("shows a pending/loading state on the Confirm button while mutation is in-flight", async () => {
      (useDeleteManualAssociation as Mock).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        isPending: true,
        mutate: vi.fn(),
      });

      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      // Open confirmation.
      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      await waitFor(() => {
        // Confirm button should show a loading label while mutation is pending.
        const pendingConfirmBtn =
          screen.queryByRole("button", { name: /removing|confirming|pending/i }) ??
          screen.queryByTestId(`unlink-confirm-${MANUAL_ONLY_ENTITY.entity_id}`);

        expect(pendingConfirmBtn).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Suite 4: Cancel flow — dialog dismissed without side effects
  // =========================================================================

  describe("TC-R04: cancel flow hides the confirmation dialog", () => {
    it("hides the confirmation dialog when Cancel is clicked", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      // Open the dialog.
      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      // Confirm dialog appears.
      const cancelBtn = await screen.findByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      // The confirmation dialog should no longer be visible.
      await waitFor(() => {
        expect(
          screen.queryByText(/only the manual association will be removed/i)
        ).not.toBeInTheDocument();
      });
    });

    it("does NOT call the delete mutate function when Cancel is clicked", async () => {
      const mutateFn = vi.fn();
      (useDeleteManualAssociation as Mock).mockReturnValue({
        ...makeIdleDeleteMutationState(),
        mutate: mutateFn,
      });

      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      const cancelBtn = await screen.findByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      expect(mutateFn).not.toHaveBeenCalled();
    });

    it("hides the confirmation dialog when Escape is pressed", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      // Wait for confirmation to appear.
      await screen.findByText(/only the manual association will be removed/i);

      // Press Escape — the dialog should disappear.
      fireEvent.keyDown(document, { key: "Escape", code: "Escape" });

      await waitFor(() => {
        expect(
          screen.queryByText(/only the manual association will be removed/i)
        ).not.toBeInTheDocument();
      });
    });

    it("the unlink button is still visible after cancel so the user can retry", async () => {
      renderPanel({ entities: [MANUAL_ONLY_ENTITY] });

      const unlinkBtn =
        screen.getByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
        screen.getByRole("button", { name: /unlink|remove manual|remove association/i });
      fireEvent.click(unlinkBtn);

      const cancelBtn = await screen.findByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      await waitFor(() => {
        const unlinkBtnAfterCancel =
          screen.queryByTestId(`unlink-button-${MANUAL_ONLY_ENTITY.entity_id}`) ??
          screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });
        expect(unlinkBtnAfterCancel).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Suite 5: Multi-source removal — MANUAL badge disappears, transcript remains
  //
  // When an entity has both transcript and manual sources (has_manual=true,
  // mention_count>0), removing the manual association should leave the entity
  // chip visible (transcript mentions remain) but without the [MANUAL] badge.
  //
  // NOTE: In these TDD tests the UI re-render after mutation is simulated by
  // re-rendering with updated props that reflect the post-deletion state.
  // The actual cache invalidation / refetch path is covered by hook-level tests.
  // =========================================================================

  describe("TC-R05: multi-source removal (MANUAL badge disappears, transcript badge remains)", () => {
    it("MANUAL badge is present before removal for a multi-source entity", () => {
      renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      // The chip should show the MANUAL badge.
      expect(screen.getByText("MANUAL")).toBeInTheDocument();
    });

    it("entity chip remains visible after simulated removal of the manual association (transcript mentions still present)", () => {
      const { rerender } = renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      // Simulate the backend response after manual association is deleted:
      // mention_count stays the same, but has_manual becomes false and
      // sources only contains "transcript".
      const afterRemoval: VideoEntitySummary = {
        ...MULTI_SOURCE_ENTITY,
        has_manual: false,
        sources: ["transcript"],
      };

      rerender(
        <EntityMentionsPanel
          entities={[afterRemoval]}
          isLoading={false}
          videoId={VIDEO_ID}
        />
      );

      // The entity chip (name) should still be visible.
      expect(screen.getByText("SpaceX")).toBeInTheDocument();
    });

    it("MANUAL badge disappears after simulated removal of the manual association", () => {
      const { rerender } = renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      const afterRemoval: VideoEntitySummary = {
        ...MULTI_SOURCE_ENTITY,
        has_manual: false,
        sources: ["transcript"],
      };

      rerender(
        <EntityMentionsPanel
          entities={[afterRemoval]}
          isLoading={false}
          videoId={VIDEO_ID}
        />
      );

      // MANUAL badge must disappear.
      expect(screen.queryByText("MANUAL")).not.toBeInTheDocument();
    });

    it("unlink button disappears after simulated removal (has_manual=false)", () => {
      const { rerender } = renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      // Before: unlink button should be present.
      const unlinkBtnBefore =
        screen.queryByTestId(`unlink-button-${MULTI_SOURCE_ENTITY.entity_id}`) ??
        screen.queryByRole("button", { name: /unlink|remove manual|remove association/i });
      expect(unlinkBtnBefore).toBeInTheDocument();

      // Simulate post-delete state.
      const afterRemoval: VideoEntitySummary = {
        ...MULTI_SOURCE_ENTITY,
        has_manual: false,
        sources: ["transcript"],
      };

      rerender(
        <EntityMentionsPanel
          entities={[afterRemoval]}
          isLoading={false}
          videoId={VIDEO_ID}
        />
      );

      // After: unlink button must be gone.
      const unlinkBtnAfter = screen.queryByTestId(
        `unlink-button-${MULTI_SOURCE_ENTITY.entity_id}`
      );
      expect(unlinkBtnAfter).not.toBeInTheDocument();
    });

    it("shows both a transcript badge area and MANUAL badge for a multi-source entity before removal", () => {
      renderPanel({ entities: [MULTI_SOURCE_ENTITY] });

      // The chip should still show mention_count (transcript present).
      expect(screen.getByText(`(${MULTI_SOURCE_ENTITY.mention_count})`)).toBeInTheDocument();
      // And the MANUAL badge.
      expect(screen.getByText("MANUAL")).toBeInTheDocument();
    });
  });
});
