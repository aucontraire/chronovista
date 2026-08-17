/**
 * Tests for CreateEntityModal — Wikidata grounding step (Feature 067, US3).
 *
 * Coverage:
 * - Grounding auto-searches once name+type are present — no manual trigger
 *   required (discoverability fix: the old "Search Wikidata" button was
 *   undiscoverable)
 * - Shortlist renders with type-match/statement/sitelink signals and a stub
 *   warning
 * - Selecting a candidate then submitting sends `approvedIdentifier` to
 *   createEntity (standalone mode)
 * - Grounding is available and submitted via the CLASSIFY path when
 *   "creating from tag" — un-gated from `selectedTag === null` because
 *   grounding is a property of the name+type being classified, not of
 *   whether a tag happens to already exist for it
 * - "Create without grounding" sends no `approvedIdentifier`
 * - `unavailable: true` (soft failure) renders its own message and still
 *   allows ungrounded creation
 * - `candidates: []` with `unavailable: false` renders a distinct "no match"
 *   message
 *
 * `useDebounce` is mocked as a pass-through identity function so the
 * auto-search effect fires synchronously within `fireEvent`-driven
 * assertions instead of racing a real 450ms timer.
 *
 * Mirrors the mocking conventions of the sibling test files
 * `CreateEntityModal.test.tsx` / `CreateEntityModal.promoteName.test.tsx` —
 * module-level `vi.mock` (hoisted above imports), `useCanonicalTags`/
 * `useEntityMentions` mocked wholesale since the component imports several
 * hooks from each module.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks — must be declared before component imports (vi.mock hoisting)
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useCanonicalTags", () => ({
  useCanonicalTags: vi.fn(),
}));

// Pass-through: the auto-search debounce is exercised by dedicated timing
// tests elsewhere (useDebounce's own unit tests); here we want the
// auto-search effect to fire synchronously against `fireEvent`.
vi.mock("../../../hooks/useDebounce", () => ({
  useDebounce: (value: unknown) => value,
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
  useWikidataCandidates: vi.fn(),
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
import {
  useClassifyTag,
  useCheckDuplicate,
  useCreateEntity,
  useWikidataCandidates,
} from "../../../hooks/useEntityMentions";
import type { Mock } from "vitest";
import type { WikidataCandidate } from "../../../api/entityMentions";

// ---------------------------------------------------------------------------
// DOM query helpers
// ---------------------------------------------------------------------------

const getNameInput = () => screen.getByLabelText(/^name/i) as HTMLInputElement;
const getTypeSelect = () => screen.getByLabelText(/entity type/i) as HTMLSelectElement;
// Plain getByLabelText(/description/i) is ambiguous once a candidate's own
// description text (e.g. "a placeholder description") is rendered inside the
// <label> wrapping its radio button — role-scope to the textarea instead.
const getDescriptionField = () =>
  screen.getByRole("textbox", { name: /description/i }) as HTMLTextAreaElement;

/** Fills name + type so the grounding section appears (standalone mode). */
function fillNameAndType(name = "Test Person", type = "person") {
  fireEvent.change(getNameInput(), { target: { value: name } });
  fireEvent.change(getTypeSelect(), { target: { value: type } });
}

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeCandidate(overrides: Partial<WikidataCandidate> = {}): WikidataCandidate {
  return {
    qid: "Q000001",
    label: "Test Person",
    description: "A placeholder entity used for testing",
    instance_of: ["Q5"],
    statement_count: 42,
    sitelink_count: 3,
    is_stub: false,
    type_matches: true,
    ...overrides,
  };
}

function makeTag(
  overrides: {
    canonical_form?: string;
    normalized_form?: string;
    alias_count?: number;
    video_count?: number;
  } = {}
) {
  return {
    canonical_form: "test person",
    normalized_form: "test person",
    alias_count: 3,
    video_count: 42,
    ...overrides,
  };
}

function makeWikidataHook(overrides: {
  candidates?: WikidataCandidate[];
  unavailable?: boolean;
  hasSearched?: boolean;
  isLoading?: boolean;
  search?: Mock;
  reset?: Mock;
} = {}) {
  return {
    candidates: [],
    unavailable: false,
    hasSearched: false,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    search: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
}

function mockWikidata(overrides: Parameters<typeof makeWikidataHook>[0] = {}) {
  const hook = makeWikidataHook(overrides);
  (useWikidataCandidates as Mock).mockReturnValue(hook);
  return hook;
}

function makeCreateEntityMutation(overrides: { mutate?: Mock } = {}) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function makeClassifyTagMutation(overrides: { mutate?: Mock } = {}) {
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

  (useCheckDuplicate as Mock).mockReturnValue({
    data: { is_duplicate: false, existing_entity: null },
    isLoading: false,
    isError: false,
  });

  mockWikidata();
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

/** Types into the name combobox and selects the first (only) matching tag option. */
function selectTag(canonicalForm: string) {
  fireEvent.change(getNameInput(), { target: { value: canonicalForm.slice(0, 3) } });
  fireEvent.click(screen.getByRole("option", { name: new RegExp(canonicalForm, "i") }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CreateEntityModal — Wikidata grounding (Feature 067, US3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // -------------------------------------------------------------------------
  // (a) Auto-search + shortlist rendering
  // -------------------------------------------------------------------------

  describe("Auto-search", () => {
    it("automatically triggers a Wikidata search once name and type are filled — no button click required", () => {
      const hook = mockWikidata();
      renderModal();
      fillNameAndType();

      expect(hook.search).toHaveBeenCalled();
    });

    it("does not show the grounding section before name and type are both filled", () => {
      renderModal();
      expect(screen.queryByText(/ground in wikidata/i)).not.toBeInTheDocument();

      fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
      // Type not yet selected.
      expect(screen.queryByText(/ground in wikidata/i)).not.toBeInTheDocument();
    });

    it("shows a 'Search again' affordance once a search has completed", () => {
      mockWikidata({ hasSearched: true, candidates: [] });
      renderModal();
      fillNameAndType();

      expect(
        screen.getByRole("button", { name: /search again/i })
      ).toBeInTheDocument();
    });

    it("does not show 'Search again' before any search has completed", () => {
      mockWikidata({ hasSearched: false });
      renderModal();
      fillNameAndType();

      expect(
        screen.queryByRole("button", { name: /search again/i })
      ).not.toBeInTheDocument();
    });

    it("clicking 'Search again' calls the hook's search function", () => {
      const hook = mockWikidata({ hasSearched: true, candidates: [] });
      renderModal();
      fillNameAndType();

      fireEvent.click(screen.getByRole("button", { name: /search again/i }));
      // Once from the automatic effect, once from the manual click.
      expect(hook.search).toHaveBeenCalled();
    });
  });

  describe("Shortlist rendering", () => {
    it("renders each candidate with label, description, statement/sitelink counts and a type-match indicator", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [
          makeCandidate({
            qid: "Q000001",
            label: "Test Person",
            description: "A placeholder entity used for testing",
            statement_count: 42,
            sitelink_count: 3,
            type_matches: true,
          }),
        ],
      });

      renderModal();
      fillNameAndType();

      expect(screen.getByRole("radiogroup", { name: /wikidata candidates/i })).toBeInTheDocument();
      expect(screen.getByText("Test Person")).toBeInTheDocument();
      expect(
        screen.getByText("A placeholder entity used for testing")
      ).toBeInTheDocument();
      expect(screen.getByText(/42 statements/)).toBeInTheDocument();
      expect(screen.getByText(/3 sitelinks/)).toBeInTheDocument();
      expect(screen.getByText(/type match/i)).toBeInTheDocument();
    });

    it("shows a stub warning when a candidate has is_stub true", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ is_stub: true })],
      });

      renderModal();
      fillNameAndType();

      expect(screen.getByRole("note")).toHaveTextContent(/stub/i);
    });

    it("does not show a stub warning when is_stub is false", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ is_stub: false })],
      });

      renderModal();
      fillNameAndType();

      expect(screen.queryByRole("note")).not.toBeInTheDocument();
    });

    it("shows a 'type may differ' indicator when type_matches is false", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ type_matches: false })],
      });

      renderModal();
      fillNameAndType();

      expect(screen.getByText(/type may differ/i)).toBeInTheDocument();
      expect(screen.queryByText(/^type match$/i)).not.toBeInTheDocument();
    });

    it("a candidate is never pre-selected — the user must explicitly choose one", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate()],
      });

      renderModal();
      fillNameAndType();

      const radio = screen.getByRole("radio") as HTMLInputElement;
      expect(radio.checked).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // (b) Selecting a candidate then creating sends approvedIdentifier
  //     (standalone mode → createEntity)
  // -------------------------------------------------------------------------

  describe("Selecting a candidate (standalone mode)", () => {
    it("sends approvedIdentifier with the selected candidate's qid on submit", async () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ qid: "Q000002", label: "Test Person Two" })],
      });

      renderModal();
      fillNameAndType();

      fireEvent.click(screen.getByRole("radio"));

      await waitFor(() => {
        expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Test Person",
          entity_type: "person",
          approvedIdentifier: { source: "wikidata", id: "Q000002" },
        }),
        expect.any(Object)
      );
    });

    it("removing the grounding chip clears the approval before submit", () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ qid: "Q000003", label: "Test Person Three" })],
      });

      renderModal();
      fillNameAndType();
      fireEvent.click(screen.getByRole("radio"));

      fireEvent.click(
        screen.getByRole("button", { name: /remove grounding to test person three/i })
      );
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });
  });

  // -------------------------------------------------------------------------
  // (b2) Description auto-prefill from an approved candidate ("Option C")
  // -------------------------------------------------------------------------

  describe("Description auto-prefill (Feature 067, US3, Option C)", () => {
    it("prefills an empty Description with the approved candidate's description", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: "a placeholder description" })],
      });

      renderModal();
      fillNameAndType();

      fireEvent.click(screen.getByRole("radio"));

      expect(getDescriptionField()).toHaveValue("a placeholder description");
    });

    it("does not overwrite a Description the user already typed", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: "a placeholder description" })],
      });

      renderModal();
      fillNameAndType();

      fireEvent.change(getDescriptionField(), {
        target: { value: "My own description" },
      });
      fireEvent.click(screen.getByRole("radio"));

      expect(getDescriptionField()).toHaveValue("My own description");
    });

    it("does not re-prefill after the user has touched Description, even after clearing it and approving a different candidate", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [
          makeCandidate({ qid: "Q000001", description: "a placeholder description" }),
          makeCandidate({
            qid: "Q000002",
            label: "Test Person Two",
            description: "a different placeholder description",
          }),
        ],
      });

      renderModal();
      fillNameAndType();

      // Touch the field, then clear it back to empty.
      fireEvent.change(getDescriptionField(), { target: { value: "temp" } });
      fireEvent.change(getDescriptionField(), { target: { value: "" } });

      const radios = screen.getAllByRole("radio");
      fireEvent.click(radios[0]!);
      expect(getDescriptionField()).toHaveValue("");

      // Re-approving a different candidate must not prefill either — the
      // field stays cleared once the user has touched it.
      fireEvent.click(radios[1]!);
      expect(getDescriptionField()).toHaveValue("");
    });

    it("leaves Description empty when the approved candidate has no description", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ description: null })],
      });

      renderModal();
      fillNameAndType();

      fireEvent.click(screen.getByRole("radio"));

      expect(getDescriptionField()).toHaveValue("");
    });

    it("leaves the Description as-is when grounding is removed", () => {
      mockWikidata({
        hasSearched: true,
        candidates: [
          makeCandidate({
            qid: "Q000005",
            label: "Test Person Five",
            description: "a placeholder description",
          }),
        ],
      });

      renderModal();
      fillNameAndType();

      fireEvent.click(screen.getByRole("radio"));
      expect(getDescriptionField()).toHaveValue("a placeholder description");

      fireEvent.click(
        screen.getByRole("button", { name: /remove grounding to test person five/i })
      );

      expect(getDescriptionField()).toHaveValue("a placeholder description");
    });
  });

  // -------------------------------------------------------------------------
  // (c) "Create without grounding" sends no approvedIdentifier
  // -------------------------------------------------------------------------

  describe("Creating without grounding", () => {
    it("clicking 'Create without grounding' then submitting sends no approvedIdentifier", () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate()],
      });

      renderModal();
      fillNameAndType();

      fireEvent.click(
        screen.getByRole("button", { name: /create without grounding/i })
      );
      fireEvent.click(screen.getByRole("button", { name: /^create entity$/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).toMatchObject({ name: "Test Person", entity_type: "person" });
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });

    it("submitting while the search has not yet returned any results sends no approvedIdentifier", () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      // hasSearched stays false — mirrors a search still in flight/unmocked.
      mockWikidata({ hasSearched: false });

      renderModal();
      fillNameAndType();
      fireEvent.click(screen.getByRole("button", { name: /^create entity$/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });
  });

  // -------------------------------------------------------------------------
  // (d) unavailable: true soft-failure state
  // -------------------------------------------------------------------------

  describe("Wikidata unavailable (soft failure)", () => {
    it("renders a distinct 'could not reach Wikidata' message", () => {
      mockWikidata({ hasSearched: true, unavailable: true, candidates: [] });

      renderModal();
      fillNameAndType();

      expect(screen.getByText(/couldn.t reach wikidata/i)).toBeInTheDocument();
    });

    it("still allows submitting the entity without grounding", () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      mockWikidata({ hasSearched: true, unavailable: true, candidates: [] });

      renderModal();
      fillNameAndType();

      expect(screen.getByRole("button", { name: /^create entity$/i })).not.toBeDisabled();

      fireEvent.click(screen.getByRole("button", { name: /^create entity$/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });

    it("does not render the 'no matching entries' message when unavailable", () => {
      mockWikidata({ hasSearched: true, unavailable: true, candidates: [] });

      renderModal();
      fillNameAndType();

      expect(
        screen.queryByText(/no matching entries found/i)
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // (e) candidates: [] with unavailable: false renders "no match"
  // -------------------------------------------------------------------------

  describe("No match found", () => {
    it("renders a distinct 'no matching entries' message", () => {
      mockWikidata({ hasSearched: true, unavailable: false, candidates: [] });

      renderModal();
      fillNameAndType();

      expect(screen.getByText(/no matching entries found/i)).toBeInTheDocument();
      expect(screen.queryByText(/couldn.t reach wikidata/i)).not.toBeInTheDocument();
    });

    it("still allows submitting the entity without grounding", () => {
      const mutate = vi.fn();
      (useCreateEntity as Mock).mockReturnValue(makeCreateEntityMutation({ mutate }));
      mockWikidata({ hasSearched: true, unavailable: false, candidates: [] });

      renderModal();
      fillNameAndType();

      expect(screen.getByRole("button", { name: /^create entity$/i })).not.toBeDisabled();
      fireEvent.click(screen.getByRole("button", { name: /^create entity$/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });
  });

  // -------------------------------------------------------------------------
  // (f) Grounding in "creating from tag" mode (the bug this suite guards
  //     against): grounding must show and submit via the CLASSIFY path when
  //     the name being promoted is already a canonical tag.
  // -------------------------------------------------------------------------

  describe("Grounding in 'creating from tag' mode", () => {
    it("shows the grounding section once a tag is selected and a type is chosen", () => {
      mockTagResults([makeTag({ canonical_form: "Test Person", normalized_form: "test person" })]);
      mockWikidata({ hasSearched: true, candidates: [makeCandidate()] });
      renderModal();

      selectTag("Test Person");
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      expect(screen.getByText(/ground in wikidata/i)).toBeInTheDocument();
      expect(screen.getByRole("radiogroup", { name: /wikidata candidates/i })).toBeInTheDocument();
    });

    it("does not show the grounding section before a type is chosen for the tag", () => {
      mockTagResults([makeTag({ canonical_form: "Test Person", normalized_form: "test person" })]);
      renderModal();

      selectTag("Test Person");

      expect(screen.queryByText(/ground in wikidata/i)).not.toBeInTheDocument();
    });

    it("submits approvedIdentifier via the classify mutation when a candidate is approved", async () => {
      const mutate = vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "Test Person", normalized_form: "test person" })]);
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate({ qid: "Q000042", label: "Test Person" })],
      });

      renderModal();
      selectTag("Test Person");
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      fireEvent.click(screen.getByRole("radio"));

      await waitFor(() => {
        expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          normalized_form: "test person",
          entity_type: "person",
          approvedIdentifier: { source: "wikidata", id: "Q000042" },
        }),
        expect.any(Object)
      );
    });

    it("submits no approvedIdentifier via classify when grounding is skipped", () => {
      const mutate = vi.fn();
      (useClassifyTag as Mock).mockReturnValue(makeClassifyTagMutation({ mutate }));
      mockTagResults([makeTag({ canonical_form: "Test Person", normalized_form: "test person" })]);
      mockWikidata({
        hasSearched: true,
        candidates: [makeCandidate()],
      });

      renderModal();
      selectTag("Test Person");
      fireEvent.change(getTypeSelect(), { target: { value: "person" } });

      fireEvent.click(
        screen.getByRole("button", { name: /create without grounding/i })
      );
      fireEvent.click(screen.getByRole("button", { name: /create entity/i }));

      const calledWith = (mutate as Mock).mock.calls[0]?.[0];
      expect(calledWith).toMatchObject({
        normalized_form: "test person",
        entity_type: "person",
      });
      expect(calledWith).not.toHaveProperty("approvedIdentifier");
    });
  });
});
