/**
 * Tests for CreateEntityModal's promote-from-tag display-name field
 * (Feature 057, User Story 2, T026/T031).
 *
 * Coverage:
 * - Display name field appears only once a tag is selected ("creating from
 *   tag" mode)
 * - Pre-filled with the auto-derived (title-cased) suggestion of the tag's
 *   canonical form (FR-008)
 * - Freely editable
 * - Sent verbatim as `display_name` on submit (FR-009)
 * - Leaving the default unedited still sends it (equivalent to the backend's
 *   own auto-derivation — FR-010)
 * - Field is removed/reset when the tag selection is cleared (X button) or
 *   the search name is edited (FR-004 mode transition)
 * - Submit is disabled if the display name is cleared to empty
 * - Accessible: labeled via getByLabelText
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
  useScanEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useScanVideoEntities: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import CreateEntityModal from "../CreateEntityModal";
import type { CreateEntityModalProps } from "../CreateEntityModal";
import { useCanonicalTags } from "../../../hooks/useCanonicalTags";
import { useClassifyTag, useCheckDuplicate, useCreateEntity } from "../../../hooks/useEntityMentions";
import type { Mock } from "vitest";

// ---------------------------------------------------------------------------
// DOM query helpers
// ---------------------------------------------------------------------------

const getNameInput = () => screen.getByLabelText(/^name/i) as HTMLInputElement;
const getTypeSelect = () => screen.getByLabelText(/entity type/i) as HTMLSelectElement;
const getDisplayNameInput = () =>
  screen.getByLabelText(/display name/i) as HTMLInputElement;

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeTag(
  overrides: {
    canonical_form?: string;
    normalized_form?: string;
    alias_count?: number;
    video_count?: number;
  } = {}
) {
  return {
    canonical_form: "openai",
    normalized_form: "openai",
    alias_count: 3,
    video_count: 42,
    ...overrides,
  };
}

function makeClassifyTagMutation(
  overrides: {
    mutate?: Mock;
    isPending?: boolean;
    isError?: boolean;
    error?: Error | null;
  } = {}
) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

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

  (useCreateEntity as Mock).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  });

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

/** Types into the name combobox and selects the first (only) matching tag option. */
function selectTag(canonicalForm: string) {
  fireEvent.change(getNameInput(), { target: { value: canonicalForm.slice(0, 3) } });
  fireEvent.click(screen.getByRole("option", { name: new RegExp(canonicalForm, "i") }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CreateEntityModal — promote-from-tag display name (Feature 057)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  describe("Field visibility", () => {
    it("does not show a display-name field before a tag is selected", () => {
      renderModal();
      expect(screen.queryByLabelText(/display name/i)).not.toBeInTheDocument();
    });

    it("shows a display-name field once a tag is selected", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");

      expect(getDisplayNameInput()).toBeInTheDocument();
    });

    it("hides the display-name field again when the tag selection is cleared", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      expect(getDisplayNameInput()).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /remove tag link/i }));

      expect(screen.queryByLabelText(/display name/i)).not.toBeInTheDocument();
    });

    it("hides the display-name field when the search name is edited after selection", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      expect(getDisplayNameInput()).toBeInTheDocument();

      fireEvent.change(getNameInput(), { target: { value: "openai-typo" } });

      expect(screen.queryByLabelText(/display name/i)).not.toBeInTheDocument();
    });
  });

  describe("Pre-filled default suggestion (FR-008)", () => {
    it("pre-fills with the title-cased suggestion of the tag's canonical form", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");

      expect(getDisplayNameInput()).toHaveValue("Openai");
    });

    it("title-cases each word for a multi-word canonical form", () => {
      mockTagResults([
        makeTag({ canonical_form: "elon musk", normalized_form: "elon musk" }),
      ]);
      renderModal();

      selectTag("elon musk");

      expect(getDisplayNameInput()).toHaveValue("Elon Musk");
    });
  });

  describe("Editable (FR-008)", () => {
    it("allows the user to freely edit the display name", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      fireEvent.change(getDisplayNameInput(), { target: { value: "OpenAI" } });

      expect(getDisplayNameInput()).toHaveValue("OpenAI");
    });
  });

  describe("Submit sends display_name verbatim (FR-009)", () => {
    it("sends the edited display name verbatim, without re-casing", () => {
      const mutate = vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      fireEvent.change(getDisplayNameInput(), { target: { value: "OpenAI" } });
      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          normalized_form: "openai",
          entity_type: "organization",
          display_name: "OpenAI",
        }),
        expect.any(Object)
      );
    });

    it("sends the pre-filled default when the user leaves it untouched (FR-010)", () => {
      const mutate = vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          normalized_form: "openai",
          entity_type: "organization",
          display_name: "Openai",
        }),
        expect.any(Object)
      );
    });
  });

  describe("Submit disabled when display name is cleared", () => {
    it("disables the submit button when the display name is emptied", () => {
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
      fireEvent.change(getDisplayNameInput(), { target: { value: "   " } });

      expect(screen.getByRole("button", { name: /create entity/i })).toBeDisabled();
    });
  });

  describe("Disabled during submission", () => {
    it("disables the display-name field while the request is pending", async () => {
      let capturedCallbacks: { onSettled?: () => void } = {};
      const mutate = vi.fn((_vars: unknown, callbacks: typeof capturedCallbacks) => {
        capturedCallbacks = callbacks;
      });
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "openai", normalized_form: "openai" })]);
      renderModal();

      selectTag("openai");
      fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      await waitFor(() => {
        expect(getDisplayNameInput()).toBeDisabled();
      });

      act(() => {
        capturedCallbacks.onSettled?.();
      });
    });
  });
});
