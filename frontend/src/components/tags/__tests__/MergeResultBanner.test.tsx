/**
 * Tests for MergeResultBanner (Feature 056).
 *
 * Coverage:
 * - T032: success message, copyable operation ID, error display
 * - T039: undo affordance is session-scoped (absent after remount without
 *   onUndo), operation_id remains regardless (FR-010, FR-010a, US4-4)
 * - T043: undo button wiring (loading, success, error states)
 * - FR-016: entity_hint surfaced when present
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MergeResultBanner } from "../MergeResultBanner";
import type { MergeResult } from "../../../types/canonical-tags";

function makeResult(overrides: Partial<MergeResult> = {}): MergeResult {
  return {
    source_tags: ["Professor Hannah Fry"],
    target_tag: "Hannah Fry",
    aliases_moved: 2,
    new_alias_count: 7,
    new_video_count: 40,
    operation_id: "op-123e4567-e89b-12d3-a456-426614174000",
    entity_hint: null,
    ...overrides,
  };
}

describe("MergeResultBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom defines navigator.clipboard as a getter-only property — redefine
    // it so we can spy on writeText.
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it("renders a success summary naming the sources and target", () => {
    render(<MergeResultBanner result={makeResult()} />);

    expect(screen.getByText(/merge complete/i)).toBeInTheDocument();
    expect(screen.getByText(/professor hannah fry/i)).toBeInTheDocument();
    expect(screen.getAllByText(/hannah fry/i).length).toBeGreaterThan(0);
  });

  it("displays the aliases moved and resulting counts", () => {
    render(
      <MergeResultBanner
        result={makeResult({ aliases_moved: 3, new_alias_count: 9, new_video_count: 55 })}
      />
    );

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("55")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // FR-009: copyable operation ID
  // -------------------------------------------------------------------------
  describe("operation ID (FR-009)", () => {
    it("displays the operation ID", () => {
      render(<MergeResultBanner result={makeResult()} />);
      expect(
        screen.getByText("op-123e4567-e89b-12d3-a456-426614174000")
      ).toBeInTheDocument();
    });

    it("copies the operation ID to the clipboard when Copy is clicked", async () => {
      render(<MergeResultBanner result={makeResult()} />);

      await userEvent.click(screen.getByRole("button", { name: /copy operation id/i }));

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        "op-123e4567-e89b-12d3-a456-426614174000"
      );
      expect(screen.getByRole("button", { name: /copy operation id/i })).toHaveTextContent(
        "Copied!"
      );
    });

    it("shows the CLI fallback command referencing the operation ID", () => {
      render(<MergeResultBanner result={makeResult()} />);
      expect(
        screen.getByText(/chronovista tags undo op-123e4567-e89b-12d3-a456-426614174000/i)
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // FR-016: entity hint
  // -------------------------------------------------------------------------
  describe("entity hint (FR-016)", () => {
    it("surfaces the entity_hint when present", () => {
      render(
        <MergeResultBanner
          result={makeResult({ entity_hint: "Linked to entity: Hannah Fry (person)" })}
        />
      );
      expect(
        screen.getByText("Linked to entity: Hannah Fry (person)")
      ).toBeInTheDocument();
    });

    it("does not render an entity hint block when entity_hint is null", () => {
      render(<MergeResultBanner result={makeResult({ entity_hint: null })} />);
      expect(screen.queryByText(/linked to entity/i)).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T043: undo wiring
  // -------------------------------------------------------------------------
  describe("undo action", () => {
    it("renders an Undo button when onUndo is provided", () => {
      render(<MergeResultBanner result={makeResult()} onUndo={vi.fn()} />);
      expect(screen.getByRole("button", { name: /undo this merge/i })).toBeInTheDocument();
    });

    it("calls onUndo when the Undo button is clicked", async () => {
      const onUndo = vi.fn();
      render(<MergeResultBanner result={makeResult()} onUndo={onUndo} />);

      await userEvent.click(screen.getByRole("button", { name: /undo this merge/i }));
      expect(onUndo).toHaveBeenCalledTimes(1);
    });

    it("shows a loading state and disables the button while undoing", () => {
      render(<MergeResultBanner result={makeResult()} onUndo={vi.fn()} isUndoing />);
      expect(screen.getByRole("button", { name: /undoing/i })).toBeDisabled();
    });

    it("shows a confirmation and hides the button once undo succeeds", () => {
      render(
        <MergeResultBanner result={makeResult()} onUndo={vi.fn()} undoSuccess />
      );
      expect(screen.getByText(/merge undone/i)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /undo this merge/i })
      ).not.toBeInTheDocument();
    });

    it("shows an inline error message when undo fails", () => {
      render(
        <MergeResultBanner
          result={makeResult()}
          onUndo={vi.fn()}
          undoError={new Error("This operation has already been undone")}
        />
      );
      expect(screen.getByRole("alert")).toHaveTextContent(
        "This operation has already been undone"
      );
    });
  });

  // -------------------------------------------------------------------------
  // T039: session-scoped undo affordance
  // -------------------------------------------------------------------------
  describe("session-scoped undo affordance (FR-010, FR-010a, US4-4)", () => {
    it("shows the Undo button when onUndo is wired (active session)", () => {
      render(<MergeResultBanner result={makeResult()} onUndo={vi.fn()} />);
      expect(screen.getByRole("button", { name: /undo this merge/i })).toBeInTheDocument();
    });

    it("does not render an Undo button when onUndo is omitted (session lost, e.g. after a refresh)", () => {
      cleanup();
      render(<MergeResultBanner result={makeResult()} />);

      expect(
        screen.queryByRole("button", { name: /undo this merge/i })
      ).not.toBeInTheDocument();
    });

    it("still displays the operation ID as the CLI fallback when the undo affordance is unavailable", () => {
      cleanup();
      render(<MergeResultBanner result={makeResult()} />);

      expect(
        screen.getByText("op-123e4567-e89b-12d3-a456-426614174000")
      ).toBeInTheDocument();
      expect(
        screen.getByText(/chronovista tags undo op-123e4567-e89b-12d3-a456-426614174000/i)
      ).toBeInTheDocument();
    });

    it("a fresh remount without onUndo no longer offers undo even though a prior mount did", () => {
      // Simulates the same merge result surviving in memory across a
      // remount (e.g. a parent re-render) that no longer wires onUndo —
      // representing the loss of session-scoped undo capability.
      const { unmount } = render(
        <MergeResultBanner result={makeResult()} onUndo={vi.fn()} />
      );
      expect(screen.getByRole("button", { name: /undo this merge/i })).toBeInTheDocument();
      unmount();

      render(<MergeResultBanner result={makeResult()} />);
      expect(
        screen.queryByRole("button", { name: /undo this merge/i })
      ).not.toBeInTheDocument();
      // The operation ID is still the documented path to reversing the merge.
      expect(
        screen.getByText("op-123e4567-e89b-12d3-a456-426614174000")
      ).toBeInTheDocument();
    });
  });
});
