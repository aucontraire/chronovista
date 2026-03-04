/**
 * Tests for RevertConfirmation component (Feature 035, T025).
 *
 * Test coverage:
 * 1. Renders "Revert to previous version?" text
 * 2. Confirm button triggers onConfirm
 * 3. Cancel button triggers onCancel
 * 4. Escape key triggers onCancel
 * 5. Focus moves to Confirm button on mount
 * 6. Warning icon has aria-hidden="true"
 * 7. Focus-visible ring present on buttons (class assertion)
 * 8. Confirm button disabled when isPending, shows "Reverting..."
 * 9. Cancel button always enabled even when isPending
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RevertConfirmation } from "../RevertConfirmation";
import type { RevertConfirmationProps } from "../RevertConfirmation";

/**
 * Default props factory for RevertConfirmation tests.
 */
function createDefaultProps(
  overrides: Partial<RevertConfirmationProps> = {}
): RevertConfirmationProps {
  return {
    isPending: false,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
}

describe("RevertConfirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Test 1 — Renders 'Revert to previous version?' text", () => {
    it("displays the confirmation label text", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      expect(screen.getByText("Revert to previous version?")).toBeInTheDocument();
    });
  });

  describe("Test 2 — Confirm button triggers onConfirm", () => {
    it("calls onConfirm when Confirm button is clicked", async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      render(<RevertConfirmation {...createDefaultProps({ onConfirm })} />);

      await user.click(screen.getByRole("button", { name: /confirm/i }));

      expect(onConfirm).toHaveBeenCalledOnce();
    });
  });

  describe("Test 3 — Cancel button triggers onCancel", () => {
    it("calls onCancel when Cancel button is clicked", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<RevertConfirmation {...createDefaultProps({ onCancel })} />);

      await user.click(screen.getByRole("button", { name: /cancel/i }));

      expect(onCancel).toHaveBeenCalledOnce();
    });
  });

  describe("Test 4 — Escape key triggers onCancel", () => {
    it("calls onCancel when Escape is pressed inside the container", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<RevertConfirmation {...createDefaultProps({ onCancel })} />);

      // Focus the Confirm button (auto-focused on mount) and press Escape
      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      confirmButton.focus();
      await user.keyboard("{Escape}");

      expect(onCancel).toHaveBeenCalledOnce();
    });

    it("calls onCancel when Escape is pressed while Cancel button is focused", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<RevertConfirmation {...createDefaultProps({ onCancel })} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      cancelButton.focus();
      await user.keyboard("{Escape}");

      expect(onCancel).toHaveBeenCalledOnce();
    });
  });

  describe("Test 5 — Focus moves to Confirm button on mount", () => {
    it("auto-focuses the Confirm button when the component mounts", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      expect(document.activeElement).toBe(confirmButton);
    });
  });

  describe("Test 6 — Warning icon has aria-hidden='true'", () => {
    it("marks the warning SVG icon as decorative with aria-hidden", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      // SVG elements don't have a role by default, so we find by querying the DOM
      const svgs = document.querySelectorAll("svg[aria-hidden='true']");
      expect(svgs.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("Test 7 — Focus-visible ring classes present on buttons", () => {
    it("Confirm button has focus-visible ring classes", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      expect(confirmButton.className).toContain("focus-visible:ring-2");
      expect(confirmButton.className).toContain("focus-visible:ring-blue-500");
    });

    it("Cancel button has focus-visible ring classes", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton.className).toContain("focus-visible:ring-2");
      expect(cancelButton.className).toContain("focus-visible:ring-blue-500");
    });
  });

  describe("Test 8 — Confirm button disabled and shows 'Reverting...' when isPending", () => {
    it("disables Confirm button and shows 'Reverting...' text when isPending is true", () => {
      render(<RevertConfirmation {...createDefaultProps({ isPending: true })} />);

      // When isPending the button text changes to "Reverting..." so query by that text
      const confirmButton = screen.getByRole("button", { name: /reverting/i });
      expect(confirmButton).toBeDisabled();
      expect(confirmButton).toHaveTextContent("Reverting...");
      expect(confirmButton).toHaveAttribute("aria-busy", "true");
    });

    it("shows 'Confirm' text when not pending", () => {
      render(<RevertConfirmation {...createDefaultProps({ isPending: false })} />);

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      expect(confirmButton).not.toBeDisabled();
      expect(confirmButton).toHaveTextContent("Confirm");
    });

    it("does not set aria-busy when not pending", () => {
      render(<RevertConfirmation {...createDefaultProps({ isPending: false })} />);

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      expect(confirmButton).not.toHaveAttribute("aria-busy");
    });
  });

  describe("Test 9 — Cancel button always enabled even when isPending", () => {
    it("Cancel button is not disabled when isPending is true", () => {
      render(<RevertConfirmation {...createDefaultProps({ isPending: true })} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).not.toBeDisabled();
    });

    it("Cancel button is not disabled when isPending is false", () => {
      render(<RevertConfirmation {...createDefaultProps({ isPending: false })} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).not.toBeDisabled();
    });

    it("Cancel button calls onCancel even when isPending is true", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(
        <RevertConfirmation
          {...createDefaultProps({ isPending: true, onCancel })}
        />
      );

      await user.click(screen.getByRole("button", { name: /cancel/i }));

      expect(onCancel).toHaveBeenCalledOnce();
    });
  });

  describe("WCAG touch target sizes", () => {
    it("Confirm button has minimum 44x44px touch target classes", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      expect(confirmButton.className).toContain("min-h-[44px]");
      expect(confirmButton.className).toContain("min-w-[44px]");
    });

    it("Cancel button has minimum 44x44px touch target classes", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton.className).toContain("min-h-[44px]");
      expect(cancelButton.className).toContain("min-w-[44px]");
    });
  });

  describe("Container styles", () => {
    it("renders amber-50 background container with border", () => {
      render(<RevertConfirmation {...createDefaultProps()} />);

      // The label text is inside the container — find its parent container
      const label = screen.getByText("Revert to previous version?");
      const container = label.closest("div");
      expect(container).not.toBeNull();
      expect(container!.className).toContain("bg-amber-50");
      expect(container!.className).toContain("border-amber-200");
    });
  });
});
