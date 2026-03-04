/**
 * Tests for SegmentEditForm component (Feature 035, T022).
 *
 * Test coverage:
 * 1. Renders textarea pre-filled with initialText
 * 2. Correction type select defaults to "asr_error" with all 5 options
 * 3. Note input visible with 500-char maxLength and character counter
 * 4. Save triggers onSave with form data when text is valid
 * 5. Cancel triggers onCancel
 * 6. Empty text shows "Correction text cannot be empty." — onSave NOT called
 * 7. Identical text shows "Correction is identical to the current text." — onSave NOT called
 * 8. Validation error clears on keystroke in textarea
 * 9. aria-invalid="true" set on textarea when validation error present
 * 10. aria-describedby links error to textarea
 * 11. Escape key calls onCancel
 * 12. Save button disabled and shows "Saving…" when isPending is true
 * 13. Tab order: textarea → select → note → Save → Cancel
 * 14. Labels associated with inputs via htmlFor/id
 * 15. Server error displayed when serverError prop is set
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SegmentEditForm } from "../SegmentEditForm";
import type { SegmentEditFormProps } from "../SegmentEditForm";

/**
 * Default props factory for SegmentEditForm tests.
 */
function createDefaultProps(
  overrides: Partial<SegmentEditFormProps> = {}
): SegmentEditFormProps {
  return {
    initialText: "Original segment text",
    segmentId: 42,
    isPending: false,
    onSave: vi.fn(),
    onCancel: vi.fn(),
    serverError: null,
    ...overrides,
  };
}

describe("SegmentEditForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Test 1 — Textarea pre-filled with initialText", () => {
    it("renders textarea with the initialText value", () => {
      const props = createDefaultProps({ initialText: "Hello world" });
      render(<SegmentEditForm {...props} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      expect(textarea).toBeInTheDocument();
      expect(textarea).toHaveValue("Hello world");
    });
  });

  describe("Test 2 — Correction type select defaults and options", () => {
    it("defaults to asr_error option", () => {
      render(<SegmentEditForm {...createDefaultProps()} />);

      const select = screen.getByRole("combobox", { name: /correction type/i });
      expect(select).toHaveValue("asr_error");
    });

    it("renders all 5 correction type options", () => {
      render(<SegmentEditForm {...createDefaultProps()} />);

      expect(screen.getByRole("option", { name: "Spelling" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "ASR Error" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Context Correction" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Profanity Fix" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Formatting" })).toBeInTheDocument();
    });
  });

  describe("Test 3 — Correction note input with maxLength and character counter", () => {
    it("renders note input with maxLength=500 and shows character counter", () => {
      render(<SegmentEditForm {...createDefaultProps()} />);

      const noteInput = screen.getByLabelText(/correction note/i);
      expect(noteInput).toBeInTheDocument();
      expect(noteInput).toHaveAttribute("maxLength", "500");

      // Character counter shows 0/500 initially
      expect(screen.getByText("0/500")).toBeInTheDocument();
    });

    it("updates character counter as user types in note input", async () => {
      const user = userEvent.setup();
      render(<SegmentEditForm {...createDefaultProps()} />);

      const noteInput = screen.getByLabelText(/correction note/i);
      await user.type(noteInput, "Hello");

      expect(screen.getByText("5/500")).toBeInTheDocument();
    });
  });

  describe("Test 4 — Save triggers onSave with correct form data when valid", () => {
    it("calls onSave with trimmed text, selected type, and note when data is valid", async () => {
      const user = userEvent.setup();
      const onSave = vi.fn();
      render(
        <SegmentEditForm
          {...createDefaultProps({ onSave })}
          initialText="Original text"
        />
      );

      // Change text to something different
      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);
      await user.type(textarea, "Corrected text");

      // Change correction type to spelling
      const select = screen.getByRole("combobox", { name: /correction type/i });
      await user.selectOptions(select, "spelling");

      // Add a note
      const noteInput = screen.getByLabelText(/correction note/i);
      await user.type(noteInput, "Fixed spelling error");

      // Click Save
      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(onSave).toHaveBeenCalledOnce();
      expect(onSave).toHaveBeenCalledWith({
        corrected_text: "Corrected text",
        correction_type: "spelling",
        correction_note: "Fixed spelling error",
      });
    });

    it("passes null for correction_note when note input is empty", async () => {
      const user = userEvent.setup();
      const onSave = vi.fn();
      render(
        <SegmentEditForm
          {...createDefaultProps({ onSave })}
          initialText="Original text"
        />
      );

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);
      await user.type(textarea, "Changed text");

      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({ correction_note: null })
      );
    });
  });

  describe("Test 5 — Cancel triggers onCancel", () => {
    it("calls onCancel when Cancel button is clicked", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<SegmentEditForm {...createDefaultProps({ onCancel })} />);

      await user.click(screen.getByRole("button", { name: /cancel/i }));

      expect(onCancel).toHaveBeenCalledOnce();
    });
  });

  describe("Test 6 — Empty text validation error", () => {
    it("shows 'Correction text cannot be empty.' when textarea is cleared and Save is clicked", async () => {
      const user = userEvent.setup();
      const onSave = vi.fn();
      render(<SegmentEditForm {...createDefaultProps({ onSave })} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);

      await user.click(screen.getByRole("button", { name: /save/i }));

      // role="alert" elements are announced by content, not by accessible name
      // Testing Library's getByRole with name filter works only for labelled elements.
      // Validate with text content query and role presence separately.
      expect(
        screen.getByText("Correction text cannot be empty.")
      ).toBeInTheDocument();
      // Confirm the error element has role="alert" for screen reader announcement
      const errorEl = screen.getByText("Correction text cannot be empty.");
      expect(errorEl).toHaveAttribute("role", "alert");

      expect(onSave).not.toHaveBeenCalled();
    });
  });

  describe("Test 7 — Identical text validation error", () => {
    it("shows 'Correction is identical to the current text.' when text is unchanged", async () => {
      const user = userEvent.setup();
      const onSave = vi.fn();
      render(
        <SegmentEditForm
          {...createDefaultProps({ onSave })}
          initialText="Original segment text"
        />
      );

      // Do not change the text — click Save directly
      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(
        screen.getByText("Correction is identical to the current text.")
      ).toBeInTheDocument();
      expect(onSave).not.toHaveBeenCalled();
    });
  });

  describe("Test 8 — Validation error clears on next keystroke", () => {
    it("clears validation error when user types in the textarea after a failed save", async () => {
      const user = userEvent.setup();
      render(<SegmentEditForm {...createDefaultProps()} />);

      // Trigger validation error by clearing and saving
      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);
      await user.click(screen.getByRole("button", { name: /save/i }));

      // Error is shown
      expect(screen.getByText("Correction text cannot be empty.")).toBeInTheDocument();

      // Now type something to clear the error
      await user.type(textarea, "a");

      expect(
        screen.queryByText("Correction text cannot be empty.")
      ).not.toBeInTheDocument();
    });
  });

  describe("Test 9 — aria-invalid on textarea when validation error present", () => {
    it("sets aria-invalid='true' on textarea when validation error is shown", async () => {
      const user = userEvent.setup();
      render(<SegmentEditForm {...createDefaultProps()} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      expect(textarea).toHaveAttribute("aria-invalid", "false");

      await user.clear(textarea);
      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(textarea).toHaveAttribute("aria-invalid", "true");
    });

    it("removes aria-invalid='true' when validation error is cleared by typing", async () => {
      const user = userEvent.setup();
      render(<SegmentEditForm {...createDefaultProps()} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);
      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(textarea).toHaveAttribute("aria-invalid", "true");

      await user.type(textarea, "New text");

      expect(textarea).toHaveAttribute("aria-invalid", "false");
    });
  });

  describe("Test 10 — aria-describedby links error message to textarea", () => {
    it("sets aria-describedby on textarea pointing to the error element id", async () => {
      const user = userEvent.setup();
      render(
        <SegmentEditForm {...createDefaultProps()} segmentId={42} />
      );

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });

      // No error initially — aria-describedby should not be set
      expect(textarea).not.toHaveAttribute("aria-describedby");

      await user.clear(textarea);
      await user.click(screen.getByRole("button", { name: /save/i }));

      // After error — aria-describedby should point to the error element
      expect(textarea).toHaveAttribute("aria-describedby", "segment-edit-error-42");

      const errorEl = document.getElementById("segment-edit-error-42");
      expect(errorEl).toBeInTheDocument();
    });
  });

  describe("Test 11 — Escape key calls onCancel", () => {
    it("calls onCancel when Escape is pressed inside the form", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<SegmentEditForm {...createDefaultProps({ onCancel })} />);

      // Focus the textarea and press Escape
      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.click(textarea);
      await user.keyboard("{Escape}");

      expect(onCancel).toHaveBeenCalledOnce();
    });
  });

  describe("Test 12 — isPending state on Save button", () => {
    it("disables Save button and shows 'Saving…' text when isPending is true", () => {
      render(<SegmentEditForm {...createDefaultProps({ isPending: true })} />);

      const saveButton = screen.getByRole("button", { name: /saving correction/i });
      expect(saveButton).toBeDisabled();
      expect(saveButton).toHaveTextContent("Saving…");
      expect(saveButton).toHaveAttribute("aria-busy", "true");
    });

    it("Cancel button remains enabled when isPending is true", () => {
      render(<SegmentEditForm {...createDefaultProps({ isPending: true })} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      expect(cancelButton).not.toBeDisabled();
    });

    it("Save button is enabled and shows 'Save' text when not pending", () => {
      render(<SegmentEditForm {...createDefaultProps({ isPending: false })} />);

      const saveButton = screen.getByRole("button", { name: /save/i });
      expect(saveButton).not.toBeDisabled();
      expect(saveButton).toHaveTextContent("Save");
    });
  });

  describe("Test 13 — Tab order: textarea → select → note → Save → Cancel", () => {
    it("all interactive elements are in the DOM and can receive focus", () => {
      render(<SegmentEditForm {...createDefaultProps()} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      const select = screen.getByRole("combobox", { name: /correction type/i });
      const noteInput = screen.getByLabelText(/correction note/i);
      const saveButton = screen.getByRole("button", { name: /save/i });
      const cancelButton = screen.getByRole("button", { name: /cancel/i });

      // All elements exist and are not hidden
      expect(textarea).toBeVisible();
      expect(select).toBeVisible();
      expect(noteInput).toBeVisible();
      expect(saveButton).toBeVisible();
      expect(cancelButton).toBeVisible();
    });

    it("Tab key moves focus through interactive elements in correct order", async () => {
      const user = userEvent.setup();
      render(<SegmentEditForm {...createDefaultProps()} />);

      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      const select = screen.getByRole("combobox", { name: /correction type/i });
      const noteInput = screen.getByLabelText(/correction note/i);
      const saveButton = screen.getByRole("button", { name: /save/i });
      const cancelButton = screen.getByRole("button", { name: /cancel/i });

      // Start from textarea (auto-focused on mount)
      textarea.focus();
      expect(document.activeElement).toBe(textarea);

      await user.tab();
      expect(document.activeElement).toBe(select);

      await user.tab();
      expect(document.activeElement).toBe(noteInput);

      await user.tab();
      expect(document.activeElement).toBe(saveButton);

      await user.tab();
      expect(document.activeElement).toBe(cancelButton);
    });
  });

  describe("Test 14 — Labels associated with inputs via htmlFor/id", () => {
    it("textarea has accessible label 'Edit segment text'", () => {
      render(<SegmentEditForm {...createDefaultProps()} segmentId={5} />);

      // getByLabelText also validates htmlFor → id association
      const textarea = screen.getByLabelText("Edit segment text");
      expect(textarea).toBeInTheDocument();
      expect(textarea.tagName).toBe("TEXTAREA");
    });

    it("correction type select has associated label via htmlFor/id", () => {
      render(<SegmentEditForm {...createDefaultProps()} segmentId={5} />);

      const select = screen.getByLabelText("Correction type");
      expect(select).toBeInTheDocument();
      expect(select.tagName).toBe("SELECT");
      expect(select).toHaveAttribute("id", "correction-type-5");
    });

    it("note input has associated label via htmlFor/id", () => {
      render(<SegmentEditForm {...createDefaultProps()} segmentId={5} />);

      const input = screen.getByLabelText("Correction note (optional)");
      expect(input).toBeInTheDocument();
      expect(input.tagName).toBe("INPUT");
      expect(input).toHaveAttribute("id", "correction-note-5");
    });
  });

  describe("Test 15 — Server error displayed when serverError prop is set", () => {
    it("shows serverError message with role='alert' when prop is provided", () => {
      render(
        <SegmentEditForm
          {...createDefaultProps({
            serverError: "Failed to save correction.",
          })}
        />
      );

      const alerts = screen.getAllByRole("alert");
      const serverAlert = alerts.find((el) =>
        el.textContent?.includes("Failed to save correction.")
      );
      expect(serverAlert).toBeInTheDocument();
    });

    it("does not show error area when serverError is null", () => {
      render(
        <SegmentEditForm {...createDefaultProps({ serverError: null })} />
      );

      expect(
        screen.queryByText("Failed to save correction.")
      ).not.toBeInTheDocument();
    });

    it("shows both validation error and server error simultaneously", async () => {
      const user = userEvent.setup();
      render(
        <SegmentEditForm
          {...createDefaultProps({
            serverError: "Server rejected the correction.",
          })}
        />
      );

      // Trigger validation error too
      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      await user.clear(textarea);
      await user.click(screen.getByRole("button", { name: /save/i }));

      expect(
        screen.getByText("Correction text cannot be empty.")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Server rejected the correction.")
      ).toBeInTheDocument();
    });
  });
});
