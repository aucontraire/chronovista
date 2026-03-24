/**
 * Tests for CreateEntityModal — tag-backed creation path.
 *
 * Coverage (Feature 038, T019 [US1]):
 * - Modal opens with focus on name field
 * - Autocomplete queries useCanonicalTags after 2+ chars
 * - Tag selection shows "Creating from tag" chip with canonical form (FR-004)
 * - Entity type selector lists all 8 ENTITY_PRODUCING_TYPES (FR-005)
 * - Tooltip text appears for a selected type (FR-005.1)
 * - "Other" type shows non-blocking hint text (FR-005.2)
 * - Submit calls classifyTag mutation with correct params (tag-backed path)
 * - Loading state disables fields and changes button text (FR-016)
 * - Error banner appears on mutation failure and modal stays open (FR-016)
 * - Modal closes and onSuccess is called after successful submission
 * - onClose callback is called (parent is responsible for focus return)
 * - Escape closes the modal when no dropdown is open
 * - Escape closes the dropdown first when one is open, then the modal
 * - Focus trap: Tab from last focusable element wraps to first
 * - Shift+Tab from first focusable element wraps to last
 * - Backdrop click calls onClose
 * - X button calls onClose
 * - Cancel button calls onClose
 * - Editing name after tag selection clears the tag chip (FR-004 mode transition)
 * - Submit button is disabled until name and type are both provided
 * - Form resets when the modal closes and re-opens
 *
 * NOTE: The entity type <select> carries the implicit ARIA role "combobox".
 * To avoid ambiguity with the name <input role="combobox">, all queries that
 * target the name input use getByLabelText("Name") and queries that target
 * the type select use getByLabelText(/entity type/i).
 */

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks — must be declared before component imports (vi.mock hoisting)
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useCanonicalTags", () => ({
  useCanonicalTags: vi.fn(),
}));

vi.mock("../../../hooks/useEntityMentions", () => ({
  useClassifyTag: vi.fn(),
  useVideoEntities: vi.fn(),
  useEntityVideos: vi.fn(),
  useEntities: vi.fn(),
  useCreateManualAssociation: vi.fn(),
  useDeleteManualAssociation: vi.fn(),
  useCheckDuplicate: vi.fn(),
  useCreateEntity: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import CreateEntityModal from "../CreateEntityModal";
import type { CreateEntityModalProps } from "../CreateEntityModal";
import { useCanonicalTags } from "../../../hooks/useCanonicalTags";
import { useClassifyTag, useCheckDuplicate, useCreateEntity } from "../../../hooks/useEntityMentions";
import type { Mock } from "vitest";
import { ENTITY_PRODUCING_TYPES, ENTITY_TYPE_TOOLTIPS } from "../../../constants/entityTypes";

// ---------------------------------------------------------------------------
// DOM query helpers
// ---------------------------------------------------------------------------

/** The name <input role="combobox"> is labelled "Name" via htmlFor. */
const getNameInput = () => screen.getByLabelText(/^name/i) as HTMLInputElement;

/** The entity-type <select> is labelled "Entity type" via htmlFor. */
const getTypeSelect = () => screen.getByLabelText(/entity type/i) as HTMLSelectElement;

/** Description textarea. */
const getDescriptionField = () => screen.getByLabelText(/description/i) as HTMLTextAreaElement;

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeTag(overrides: {
  canonical_form?: string;
  normalized_form?: string;
  alias_count?: number;
  video_count?: number;
} = {}) {
  return {
    canonical_form: "Garfield",
    normalized_form: "garfield",
    alias_count: 3,
    video_count: 42,
    ...overrides,
  };
}

function makeClassifyTagMutation(overrides: {
  mutate?: Mock;
  isPending?: boolean;
  isError?: boolean;
  error?: Error | null;
} = {}) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function makeCreateEntityMutation(overrides: {
  mutate?: Mock;
  isPending?: boolean;
  isError?: boolean;
  error?: Error | null;
} = {}) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default hook mock values
// ---------------------------------------------------------------------------

function setupDefaultMocks() {
  (useCanonicalTags as Mock).mockReturnValue({
    tags: [],
    suggestions: [],
    isLoading: false,
    isError: false,
    error: null,
    isRateLimited: false,
    rateLimitRetryAfter: 0,
  });

  (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation());

  (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation());

  // Default: no duplicate found — keeps all pre-existing tests green.
  (useCheckDuplicate as Mock).mockReturnValue({
    data: { is_duplicate: false, existing_entity: null },
    isLoading: false,
    isError: false,
  });
}

function mockTagResults(tags: ReturnType<typeof makeTag>[]) {
  (useCanonicalTags as Mock).mockReturnValue({
    tags,
    suggestions: [],
    isLoading: false,
    isError: false,
    error: null,
    isRateLimited: false,
    rateLimitRetryAfter: 0,
  });
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderModal(props: Partial<CreateEntityModalProps> = {}) {
  const defaults: CreateEntityModalProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
    ...props,
  };
  return {
    onClose: defaults.onClose as Mock,
    onSuccess: defaults.onSuccess as Mock,
    ...render(
      <MemoryRouter>
        <CreateEntityModal {...defaults} />
      </MemoryRouter>
    ),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CreateEntityModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // -------------------------------------------------------------------------
  // Conditional rendering
  // -------------------------------------------------------------------------

  describe("Conditional rendering", () => {
    it("renders nothing when isOpen is false", () => {
      renderModal({ isOpen: false });
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("renders the dialog when isOpen is true", () => {
      renderModal({ isOpen: true });
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("dialog has an accessible title 'Create Entity'", () => {
      renderModal();
      expect(
        screen.getByRole("dialog", { name: /create entity/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Auto-focus on open
  // -------------------------------------------------------------------------

  describe("Focus management", () => {
    it("moves focus to the name input on open", async () => {
      renderModal();
      const nameInput = getNameInput();
      // The component uses requestAnimationFrame; waitFor polls until it resolves.
      await waitFor(() => {
        expect(nameInput).toHaveFocus();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Tag autocomplete: query trigger
  // -------------------------------------------------------------------------

  describe("Tag autocomplete — search trigger", () => {
    it("passes an empty string to useCanonicalTags on initial render (name is empty)", () => {
      renderModal();
      expect(useCanonicalTags).toHaveBeenCalledWith("");
    });

    it("passes the typed value to useCanonicalTags when name has 2+ chars", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      expect(useCanonicalTags).toHaveBeenCalledWith("gar");
    });

    it("passes empty string to useCanonicalTags after a tag is selected (prevents re-query)", () => {
      mockTagResults([makeTag()]);

      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      // Select the option to set selectedTag
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));

      // After selection, the hook receives "" so no new search fires
      const calls = (useCanonicalTags as Mock).mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[0]).toBe("");
    });
  });

  // -------------------------------------------------------------------------
  // Tag autocomplete: dropdown items
  // -------------------------------------------------------------------------

  describe("Tag autocomplete — dropdown items", () => {
    it("shows a listbox of tag results when name has 2+ chars and results arrive", () => {
      mockTagResults([
        makeTag({ canonical_form: "Garfield", normalized_form: "garfield" }),
        makeTag({ canonical_form: "Garmin", normalized_form: "garmin", alias_count: 1, video_count: 5 }),
      ]);

      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "gar" } });

      expect(
        screen.getByRole("listbox", { name: /matching canonical tags/i })
      ).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /garfield/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /garmin/i })).toBeInTheDocument();
    });

    it("shows video count inside each dropdown option", () => {
      mockTagResults([makeTag({ canonical_form: "Mexico", video_count: 910 })]);

      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "me" } });

      expect(screen.getByText("910 videos")).toBeInTheDocument();
    });

    it("shows alias count when alias_count is greater than 1", () => {
      mockTagResults([makeTag({ canonical_form: "AOC", alias_count: 4, video_count: 20 })]);

      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "ao" } });

      // alias label = alias_count - 1 aliases
      expect(screen.getByText("3 aliases")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Tag selection — chip and label (FR-004)
  // -------------------------------------------------------------------------

  describe("Tag selection (FR-004)", () => {
    beforeEach(() => {
      mockTagResults([
        makeTag({
          canonical_form: "Alexandria Ocasio-Cortez",
          normalized_form: "alexandria_ocasio_cortez",
        }),
      ]);
    });

    it("shows 'Creating from tag' label after a tag is selected", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "alex" } });
      fireEvent.click(screen.getByRole("option", { name: /alexandria ocasio-cortez/i }));

      expect(screen.getByText("Creating from tag")).toBeInTheDocument();
    });

    it("shows a chip with the canonical form after tag selection", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "alex" } });
      fireEvent.click(screen.getByRole("option", { name: /alexandria ocasio-cortez/i }));

      // The chip text renders the canonical form
      expect(screen.getAllByText("Alexandria Ocasio-Cortez").length).toBeGreaterThanOrEqual(1);
    });

    it("hides the dropdown after a tag is selected", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "alex" } });
      fireEvent.click(screen.getByRole("option", { name: /alexandria ocasio-cortez/i }));

      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("clears the tag chip and shows 'Creating standalone entity' when name is edited after selection (FR-004 mode transition)", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "alex" } });
      fireEvent.click(screen.getByRole("option", { name: /alexandria ocasio-cortez/i }));

      // Edit the name — triggers FR-004 mode transition
      fireEvent.change(getNameInput(), { target: { value: "alexandria modified" } });

      expect(screen.queryByText("Creating from tag")).not.toBeInTheDocument();
      // Text appears in both the visible <p> and the sr-only aria-live region.
      expect(screen.getAllByText("Creating standalone entity").length).toBeGreaterThanOrEqual(1);
    });

    it("clicking the chip X button removes the tag link", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "alex" } });
      fireEvent.click(screen.getByRole("option", { name: /alexandria ocasio-cortez/i }));

      const removeButton = screen.getByRole("button", {
        name: /remove tag link to alexandria ocasio-cortez/i,
      });
      fireEvent.click(removeButton);

      expect(screen.queryByText("Creating from tag")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Standalone label (FR-011)
  // -------------------------------------------------------------------------

  describe("Standalone entity label (FR-011)", () => {
    it("shows 'Creating standalone entity' when name has text but no tag selected", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "new entity name" } });
      // Text appears in both the visible <p> and the sr-only aria-live region.
      expect(screen.getAllByText("Creating standalone entity").length).toBeGreaterThanOrEqual(1);
    });

    it("does not show 'Creating standalone entity' when name is empty", () => {
      renderModal();
      // name defaults to ""; no changes applied
      expect(screen.queryByText("Creating standalone entity")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Entity type selector (FR-005)
  // -------------------------------------------------------------------------

  describe("Entity type selector (FR-005)", () => {
    it("renders a type select dropdown", () => {
      renderModal();
      expect(getTypeSelect()).toBeInTheDocument();
    });

    it("includes all 8 entity-producing types as option values", () => {
      renderModal();
      const options = Array.from(getTypeSelect().options)
        .map((opt) => opt.value)
        .filter(Boolean); // exclude the empty placeholder

      expect(options).toHaveLength(ENTITY_PRODUCING_TYPES.length);
      ENTITY_PRODUCING_TYPES.forEach((type) => {
        expect(options).toContain(type);
      });
    });

    it("shows tooltip text for a selected type (FR-005.1)", () => {
      renderModal();
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      expect(screen.getByText(ENTITY_TYPE_TOOLTIPS["person"]!)).toBeInTheDocument();
    });

    it("shows tooltip text for 'organization' type", () => {
      renderModal();
      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
      expect(screen.getByText(ENTITY_TYPE_TOOLTIPS["organization"]!)).toBeInTheDocument();
    });

    it("shows 'Other' hint text when 'other' type is selected (FR-005.2)", () => {
      renderModal();
      fireEvent.change(getTypeSelect(), { target: { value: "other" } });
      expect(screen.getByRole("note")).toHaveTextContent(
        /consider whether this entity fits one of the specific types above/i
      );
    });

    it("does not show 'Other' hint when a non-other type is selected", () => {
      renderModal();
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      expect(screen.queryByRole("note")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Submit button disabled state
  // -------------------------------------------------------------------------

  describe("Submit button disabled state", () => {
    it("submit button is disabled when name is empty", () => {
      renderModal();
      expect(screen.getByRole("button", { name: /create entity/i })).toBeDisabled();
    });

    it("submit button is disabled when entity type is not selected", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "some name" } });
      // entityType still ""
      expect(screen.getByRole("button", { name: /create entity/i })).toBeDisabled();
    });

    it("submit button is enabled when name and type are both provided", () => {
      mockTagResults([makeTag()]);

      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(screen.getByRole("button", { name: /create entity/i })).not.toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Submit handler — calls classifyTag with correct params (tag-backed path)
  // -------------------------------------------------------------------------

  describe("Submit handler (tag-backed path)", () => {
    function setupForSubmit(mutateMock?: Mock) {
      const mutate = mutateMock ?? vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "Garfield", normalized_form: "garfield" })]);
      return mutate;
    }

    it("calls classifyTag.mutate with normalized_form and entity_type", () => {
      const mutate = setupForSubmit();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          normalized_form: "garfield",
          entity_type: "person",
        }),
        expect.any(Object) // mutation option callbacks
      );
    });

    it("includes description when provided", () => {
      const mutate = setupForSubmit();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      fireEvent.change(getDescriptionField(), {
        target: { value: "Famous cartoon cat" },
      });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          normalized_form: "garfield",
          entity_type: "person",
          description: "Famous cartoon cat",
        }),
        expect.any(Object)
      );
    });

    it("omits description key when description field is empty", () => {
      const mutate = setupForSubmit();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      // description left blank
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("description");
    });
  });

  // -------------------------------------------------------------------------
  // Loading state during submission (FR-016)
  // -------------------------------------------------------------------------

  describe("Loading state during submission (FR-016)", () => {
    function setupSubmittingState() {
      let capturedCallbacks: { onSettled?: () => void } = {};
      const mutate = vi.fn((_vars: unknown, callbacks: typeof capturedCallbacks) => {
        capturedCallbacks = callbacks;
      });
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag()]);
      return { mutate, getCallbacks: () => capturedCallbacks };
    }

    function triggerSubmit() {
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));
    }

    it("shows 'Creating…' text and aria-busy on the submit button while submitting", async () => {
      const { getCallbacks } = setupSubmittingState();
      renderModal();
      triggerSubmit();

      // Wait for the spinner span — its text is the ellipsis character "…" (U+2026),
      // not the ASCII "..." sequence. The component renders: Creating…
      await waitFor(() => {
        expect(screen.getByText("Creating…")).toBeInTheDocument();
      });

      // The submit button should report aria-busy while isSubmitting is true.
      // It no longer matches "Create Entity" (that text is gone), so we query
      // by aria-busy attribute on the button element.
      const submitBtn = screen
        .getAllByRole("button")
        .find((btn) => btn.getAttribute("aria-busy") === "true");
      expect(submitBtn).toBeDefined();
      expect(submitBtn).toHaveAttribute("aria-busy", "true");

      // Resolve to avoid act() warnings after test completes
      act(() => { getCallbacks().onSettled?.(); });
    });

    it("disables name input, type select, and description textarea while submitting", async () => {
      const { getCallbacks } = setupSubmittingState();
      renderModal();
      triggerSubmit();

      await waitFor(() => {
        expect(screen.getByText("Creating…")).toBeInTheDocument();
      });

      // getByLabelText works on disabled elements — it finds by label association
      expect(getNameInput()).toBeDisabled();
      expect(getTypeSelect()).toBeDisabled();
      expect(getDescriptionField()).toBeDisabled();

      act(() => { getCallbacks().onSettled?.(); });
    });
  });

  // -------------------------------------------------------------------------
  // Error display on mutation failure (FR-016)
  // -------------------------------------------------------------------------

  describe("Error display on mutation failure (FR-016)", () => {
    interface CapturableCallbacks {
      onError?: (err: Error) => void;
      onSettled?: () => void;
    }

    function setupWithCapturableError() {
      let capturedCallbacks: CapturableCallbacks = {};
      const mutate = vi.fn((_vars: unknown, callbacks: CapturableCallbacks) => {
        capturedCallbacks = callbacks;
      });
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag()]);

      return {
        mutate,
        fireError: (msg: string) => {
          act(() => {
            capturedCallbacks.onError?.(new Error(msg));
            capturedCallbacks.onSettled?.();
          });
        },
      };
    }

    function triggerSubmit() {
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));
    }

    it("shows an error banner with the error message", async () => {
      const { fireError } = setupWithCapturableError();
      renderModal();
      triggerSubmit();
      fireError("Tag already classified");

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent("Tag already classified");
      });
    });

    it("modal stays open and onClose is not called after a mutation error", async () => {
      const { fireError } = setupWithCapturableError();
      const onClose = vi.fn();
      renderModal({ onClose });
      triggerSubmit();
      fireError("Something went wrong");

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("uses a fallback message when the error has an empty message string", async () => {
      const { fireError } = setupWithCapturableError();
      renderModal();
      triggerSubmit();
      fireError("");

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(/failed to create entity/i);
      });
    });

    it("clears the error banner when the user edits the name after a failure", async () => {
      const { fireError } = setupWithCapturableError();
      renderModal();
      triggerSubmit();
      fireError("Server error");

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      // Editing the name should clear the error
      fireEvent.change(getNameInput(), { target: { value: "garfield updated" } });

      await waitFor(() => {
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Success: modal closes and onSuccess is called
  // -------------------------------------------------------------------------

  describe("Success behaviour", () => {
    it("calls onSuccess and onClose after successful mutation", async () => {
      interface CapturableCallbacks { onSuccess?: () => void; onSettled?: () => void }
      let capturedCallbacks: CapturableCallbacks = {};
      const mutate = vi.fn((_vars: unknown, cbs: CapturableCallbacks) => {
        capturedCallbacks = cbs;
      });
      const onClose = vi.fn();
      const onSuccess = vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag()]);

      renderModal({ onClose, onSuccess });
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      act(() => {
        capturedCallbacks.onSuccess?.();
        capturedCallbacks.onSettled?.();
      });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
      });
    });
  });

  // -------------------------------------------------------------------------
  // Close mechanisms
  // -------------------------------------------------------------------------

  describe("Close mechanisms", () => {
    it("calls onClose when the X (close dialog) button is clicked", () => {
      const onClose = vi.fn();
      renderModal({ onClose });
      fireEvent.click(screen.getByRole("button", { name: /close dialog/i }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("calls onClose when the Cancel button is clicked", () => {
      const onClose = vi.fn();
      renderModal({ onClose });
      fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("calls onClose when the backdrop wrapper is clicked", () => {
      const onClose = vi.fn();
      renderModal({ onClose });
      // The dialog role element is the inner panel. Its parent is the full-screen backdrop.
      const backdrop = screen.getByRole("dialog").parentElement!;
      fireEvent.click(backdrop);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("does NOT call onClose when the dialog panel itself is clicked", () => {
      const onClose = vi.fn();
      renderModal({ onClose });
      // Clicking the dialog panel (not the backdrop) should not close the modal.
      fireEvent.click(screen.getByRole("dialog"));
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Escape key behaviour
  // -------------------------------------------------------------------------

  describe("Escape key", () => {
    it("calls onClose when Escape is pressed and no dropdown is open", () => {
      const onClose = vi.fn();
      renderModal({ onClose });
      fireEvent.keyDown(document, { key: "Escape" });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes the dropdown on first Escape, then the modal on second Escape", () => {
      const onClose = vi.fn();
      mockTagResults([makeTag()]);

      renderModal({ onClose });
      fireEvent.change(getNameInput(), { target: { value: "gar" } });

      // Dropdown should be visible
      expect(screen.getByRole("listbox")).toBeInTheDocument();

      // First Escape: closes dropdown only
      fireEvent.keyDown(document, { key: "Escape" });
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(onClose).not.toHaveBeenCalled();

      // Second Escape: closes modal
      fireEvent.keyDown(document, { key: "Escape" });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("does not call onClose when Escape is pressed while the modal is closed", () => {
      const onClose = vi.fn();
      renderModal({ isOpen: false, onClose });
      fireEvent.keyDown(document, { key: "Escape" });
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Focus trap (Tab/Shift+Tab wrapping)
  // -------------------------------------------------------------------------

  describe("Focus trap", () => {
    const FOCUSABLE_SELECTOR = [
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      '[tabindex]:not([tabindex="-1"])',
    ].join(", ");

    it("Tab from the last focusable element wraps focus to the first", () => {
      renderModal();
      const dialog = screen.getByRole("dialog");
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => !el.hidden);

      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;

      last.focus();
      fireEvent.keyDown(dialog, { key: "Tab", shiftKey: false });

      expect(document.activeElement).toBe(first);
    });

    it("Shift+Tab from the first focusable element wraps focus to the last", () => {
      renderModal();
      const dialog = screen.getByRole("dialog");
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => !el.hidden);

      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;

      first.focus();
      fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });

      expect(document.activeElement).toBe(last);
    });
  });

  // -------------------------------------------------------------------------
  // Dropdown keyboard navigation (ArrowDown, ArrowUp, Enter)
  // -------------------------------------------------------------------------

  describe("Dropdown keyboard navigation", () => {
    beforeEach(() => {
      mockTagResults([
        makeTag({ canonical_form: "Alpha", normalized_form: "alpha" }),
        makeTag({ canonical_form: "Beta", normalized_form: "beta" }),
      ]);
    });

    it("ArrowDown highlights the first option", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "al" } });
      fireEvent.keyDown(getNameInput(), { key: "ArrowDown" });

      const options = screen.getAllByRole("option");
      expect(options[0]).toHaveAttribute("aria-selected", "true");
    });

    it("Enter on a highlighted option selects it and shows the chip", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "al" } });
      fireEvent.keyDown(getNameInput(), { key: "ArrowDown" });
      fireEvent.keyDown(getNameInput(), { key: "Enter" });

      expect(screen.getByText("Creating from tag")).toBeInTheDocument();
      expect(getNameInput()).toHaveValue("Alpha");
    });

    it("Escape when dropdown is open closes the dropdown without closing the modal", () => {
      const onClose = vi.fn();
      renderModal({ onClose });

      fireEvent.change(getNameInput(), { target: { value: "al" } });
      expect(screen.getByRole("listbox")).toBeInTheDocument();

      // Escape on the input element (not document) — component handles it inline
      fireEvent.keyDown(getNameInput(), { key: "Escape" });
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      // Modal stays open
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Form reset on close/re-open
  // -------------------------------------------------------------------------

  describe("Form reset on close", () => {
    it("resets the name field when the modal is closed and re-opened", () => {
      const { rerender } = renderModal({ isOpen: true });

      fireEvent.change(getNameInput(), { target: { value: "some text" } });
      expect(getNameInput()).toHaveValue("some text");

      // Close
      rerender(
        <MemoryRouter>
          <CreateEntityModal isOpen={false} onClose={vi.fn()} />
        </MemoryRouter>
      );

      // Re-open
      rerender(
        <MemoryRouter>
          <CreateEntityModal isOpen={true} onClose={vi.fn()} />
        </MemoryRouter>
      );

      expect(getNameInput()).toHaveValue("");
    });

    it("resets the entity type select when the modal is closed and re-opened", () => {
      const { rerender } = renderModal({ isOpen: true });

      fireEvent.change(getTypeSelect(), { target: { value: "person" } });
      expect(getTypeSelect()).toHaveValue("person");

      rerender(
        <MemoryRouter>
          <CreateEntityModal isOpen={false} onClose={vi.fn()} />
        </MemoryRouter>
      );
      rerender(
        <MemoryRouter>
          <CreateEntityModal isOpen={true} onClose={vi.fn()} />
        </MemoryRouter>
      );

      expect(getTypeSelect()).toHaveValue("");
    });
  });

  // -------------------------------------------------------------------------
  // Duplicate Detection (US3)
  // -------------------------------------------------------------------------

  describe("Duplicate Detection (US3)", () => {
    /** Shared factory for the existing-entity payload. */
    function makeExistingEntity(overrides: {
      entity_id?: string;
      canonical_name?: string;
      entity_type?: string;
      description?: string | null;
    } = {}) {
      return {
        entity_id: "uuid-123",
        canonical_name: "Garland Nixon",
        entity_type: "person",
        description: "Political commentator",
        ...overrides,
      };
    }

    /** Mock useCheckDuplicate to return a confirmed duplicate. */
    function mockDuplicateFound(overrides: ReturnType<typeof makeExistingEntity> = makeExistingEntity()) {
      (useCheckDuplicate as Mock).mockReturnValue({
        data: { is_duplicate: true, existing_entity: overrides },
        isLoading: false,
        isError: false,
      });
    }

    /** Mock useCheckDuplicate to return no duplicate. */
    function mockNoDuplicate() {
      (useCheckDuplicate as Mock).mockReturnValue({
        data: { is_duplicate: false, existing_entity: null },
        isLoading: false,
        isError: false,
      });
    }

    it("warning appears when a duplicate is found", () => {
      mockDuplicateFound();
      renderModal();

      // Trigger the component to render with a name + type (hook is controlled by mock)
      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(
        screen.getByText("An entity with this name and type already exists:")
      ).toBeInTheDocument();
    });

    it("submit button is disabled when a duplicate is found", () => {
      mockDuplicateFound();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(screen.getByRole("button", { name: /create entity/i })).toBeDisabled();
    });

    it("warning contains a link that navigates to the existing entity", () => {
      mockDuplicateFound();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      const link = screen.getByRole("link", { name: /view existing entity/i });
      expect(link).toHaveAttribute("href", "/entities/uuid-123");
    });

    it("warning clears when the name is changed and no duplicate exists for the new value", async () => {
      // First render with duplicate
      mockDuplicateFound();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(
        screen.getByText("An entity with this name and type already exists:")
      ).toBeInTheDocument();

      // Simulate the hook returning no duplicate for the updated name
      mockNoDuplicate();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon Jr" } });

      await waitFor(() => {
        expect(
          screen.queryByText("An entity with this name and type already exists:")
        ).not.toBeInTheDocument();
      });
    });

    it("warning clears when the entity type is changed and no duplicate exists for the new type", async () => {
      // Start with a duplicate detected for "person"
      mockDuplicateFound();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(
        screen.getByText("An entity with this name and type already exists:")
      ).toBeInTheDocument();

      // Simulate the hook returning no duplicate for "organization" type
      mockNoDuplicate();

      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });

      await waitFor(() => {
        expect(
          screen.queryByText("An entity with this name and type already exists:")
        ).not.toBeInTheDocument();
      });
    });

    it("fallback: submit is NOT disabled when the duplicate check endpoint fails (FR-012)", () => {
      // isError = true means the endpoint failed — fallback allows submission
      (useCheckDuplicate as Mock).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });

      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(screen.getByRole("button", { name: /create entity/i })).not.toBeDisabled();
    });

    it("duplicate warning element has aria-live='assertive'", () => {
      mockDuplicateFound();
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      // The warning div carries both role="alert" and aria-live="assertive".
      // role="alert" has no computed accessible name from inner text, so we
      // locate it via role then confirm the attribute directly.
      const warningEl = screen.getByRole("alert");
      expect(warningEl).toHaveAttribute("aria-live", "assertive");
    });

    it("submit button is disabled while the duplicate check is pending", () => {
      // isLoading = true simulates an in-flight request
      (useCheckDuplicate as Mock).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });

      renderModal();

      // Provide name (2+ chars) and type so isDuplicateCheckPending evaluates to true
      fireEvent.change(getNameInput(), { target: { value: "Garland Nixon" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(screen.getByRole("button", { name: /create entity/i })).toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Standalone Entity Creation (US2)
  // -------------------------------------------------------------------------

  describe("Standalone Entity Creation (US2)", () => {
    // -----------------------------------------------------------------------
    // 1. "Creating standalone entity" label when no tag match
    // -----------------------------------------------------------------------

    it("shows 'Creating standalone entity' label when name has text and no tag is selected", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "edward snowden" } });
      // The text appears in both the visible <p> and the sr-only aria-live region.
      expect(screen.getAllByText("Creating standalone entity").length).toBeGreaterThanOrEqual(1);
    });

    // -----------------------------------------------------------------------
    // 2. Add alias fields (up to 20)
    // -----------------------------------------------------------------------

    it("shows an alias input after clicking 'Add Alias'", () => {
      renderModal();
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);
      expect(screen.getByLabelText("Alias 1")).toBeInTheDocument();
    });

    it("shows a second alias input after clicking 'Add Alias' twice", () => {
      renderModal();
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);
      fireEvent.click(addButton);
      expect(screen.getByLabelText("Alias 1")).toBeInTheDocument();
      expect(screen.getByLabelText("Alias 2")).toBeInTheDocument();
    });

    it("disables 'Add Alias' button after 20 aliases are added", () => {
      renderModal();
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      // Click 20 times to reach the cap.
      for (let i = 0; i < 20; i++) {
        fireEvent.click(addButton);
      }
      expect(addButton).toBeDisabled();
    });

    // -----------------------------------------------------------------------
    // 3. Remove alias field
    // -----------------------------------------------------------------------

    it("removes an alias input when the remove (X) button is clicked", () => {
      renderModal();
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);

      const aliasInput = screen.getByLabelText("Alias 1");
      fireEvent.change(aliasInput, { target: { value: "Ed Snowden" } });

      const removeButton = screen.getByRole("button", { name: "Remove alias 1" });
      fireEvent.click(removeButton);

      expect(screen.queryByLabelText("Alias 1")).not.toBeInTheDocument();
    });

    // -----------------------------------------------------------------------
    // 4. Mode transition: tag-backed → standalone on name edit; aliases cleared
    //    when switching back to tag-backed mode.
    // -----------------------------------------------------------------------

    it("transitions from 'Creating from tag' to 'Creating standalone entity' when name is edited", () => {
      mockTagResults([makeTag({ canonical_form: "Garfield", normalized_form: "garfield" })]);
      renderModal();

      // Select a tag → tag-backed mode.
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));
      expect(screen.getByText("Creating from tag")).toBeInTheDocument();

      // Edit the name → standalone mode.
      fireEvent.change(getNameInput(), { target: { value: "garfield modified" } });
      expect(screen.queryByText("Creating from tag")).not.toBeInTheDocument();
      // Text appears in both the visible <p> and the sr-only aria-live region.
      expect(screen.getAllByText("Creating standalone entity").length).toBeGreaterThanOrEqual(1);
    });

    it("clears alias inputs when switching back to tag-backed mode via tag selection", () => {
      mockTagResults([makeTag({ canonical_form: "Garfield", normalized_form: "garfield" })]);
      renderModal();

      // Add an alias in standalone mode.
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);
      expect(screen.getByLabelText("Alias 1")).toBeInTheDocument();

      // Type enough to trigger the dropdown and select a tag (switches to tag-backed mode).
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));

      // Aliases should be cleared; the alias section is hidden in tag-backed mode.
      expect(screen.queryByLabelText("Alias 1")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /\+ add alias/i })).not.toBeInTheDocument();
    });

    // -----------------------------------------------------------------------
    // 5. aria-live="polite" announcement on mode switch
    // -----------------------------------------------------------------------

    it("has an aria-live='polite' region that announces 'Creating standalone entity' when in standalone mode", () => {
      renderModal();
      fireEvent.change(getNameInput(), { target: { value: "edward snowden" } });

      // The sr-only div carries aria-live="polite".
      const liveRegions = document
        .querySelectorAll('[aria-live="polite"]');

      // At least one live region must contain the standalone announcement.
      const announcementRegion = Array.from(liveRegions).find(
        (el) => el.textContent?.includes("Creating standalone entity")
      );
      expect(announcementRegion).toBeDefined();
    });

    it("has an aria-live='polite' region that announces the tag name when a tag is selected", () => {
      mockTagResults([makeTag({ canonical_form: "Garfield", normalized_form: "garfield" })]);
      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));

      const liveRegions = document.querySelectorAll('[aria-live="polite"]');
      const announcementRegion = Array.from(liveRegions).find(
        (el) => el.textContent?.includes("Creating from tag: Garfield")
      );
      expect(announcementRegion).toBeDefined();
    });

    // -----------------------------------------------------------------------
    // 6. Submit triggers createEntity with correct params including aliases
    // -----------------------------------------------------------------------

    it("calls createEntity.mutate with name, entity_type, and aliases on submit", () => {
      const mockMutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate: mockMutate }));

      renderModal();

      // Fill in the form in standalone mode (no tag selected).
      fireEvent.change(getNameInput(), { target: { value: "edward snowden" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      // Add two aliases.
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);
      fireEvent.change(screen.getByLabelText("Alias 1"), {
        target: { value: "Ed Snowden" },
      });
      fireEvent.click(addButton);
      fireEvent.change(screen.getByLabelText("Alias 2"), {
        target: { value: "Snowden" },
      });

      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "edward snowden",
          entity_type: "person",
          aliases: ["Ed Snowden", "Snowden"],
        }),
        expect.any(Object)
      );
    });

    it("omits aliases key from createEntity payload when all alias inputs are blank", () => {
      const mockMutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate: mockMutate }));

      renderModal();

      fireEvent.change(getNameInput(), { target: { value: "edward snowden" } });
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      // Add an alias but leave it blank.
      const addButton = screen.getByRole("button", { name: /\+ add alias/i });
      fireEvent.click(addButton);
      // Alias input left empty — it will be filtered out.

      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      const calledWith = (mockMutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("aliases");
    });

    // -----------------------------------------------------------------------
    // 7. Alias inputs NOT shown in tag-backed mode
    // -----------------------------------------------------------------------

    it("does not show 'Add Alias' button when a tag is selected (tag-backed mode)", () => {
      mockTagResults([makeTag({ canonical_form: "Garfield", normalized_form: "garfield" })]);
      renderModal();

      // Select a tag to enter tag-backed mode.
      fireEvent.change(getNameInput(), { target: { value: "gar" } });
      fireEvent.click(screen.getByRole("option", { name: /garfield/i }));

      expect(screen.queryByRole("button", { name: /\+ add alias/i })).not.toBeInTheDocument();
    });
  });
});
