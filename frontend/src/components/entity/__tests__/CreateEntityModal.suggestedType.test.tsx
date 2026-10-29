/**
 * Tests for CreateEntityModal — Wikidata-suggested entity type (Feature 098, US3).
 *
 * Grounding to a candidate pre-selects its `suggested_entity_type` unless the
 * user has already chosen a type; a null suggestion leaves the selector unset.
 */

import { render, screen, fireEvent } from "@testing-library/react";
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
    suggested_entity_type: null,
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
    canShowMore: false,
    isFetchingMore: false,
    showMore: vi.fn(),
    resolveByQid: vi.fn(),
    isResolvingQid: false,
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



describe("CreateEntityModal — suggested entity type (Feature 098, US3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  function ground(candidate: WikidataCandidate) {
    mockWikidata({ hasSearched: true, candidates: [candidate] });
  }

  it("grounds before any type is chosen", () => {
    ground(makeCandidate({ suggested_entity_type: "person", type_matches: null }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });

    expect(getTypeSelect().value).toBe("");
    expect(screen.getByRole("radio")).toBeInTheDocument();
  });

  it("pre-selects the suggested type when a candidate is grounded", () => {
    ground(makeCandidate({ suggested_entity_type: "person", type_matches: null }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getByRole("radio"));

    expect(getTypeSelect().value).toBe("person");
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
  });

  it("leaves the selector unset when the suggestion is null", () => {
    ground(makeCandidate({ suggested_entity_type: null, type_matches: null }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getByRole("radio"));

    expect(getTypeSelect().value).toBe("");
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
  });

  it("does not override a type the user chose explicitly", () => {
    ground(makeCandidate({ suggested_entity_type: "person" }));
    renderModal();
    fillNameAndType("Test Person", "organization");
    fireEvent.click(screen.getByRole("radio"));

    expect(getTypeSelect().value).toBe("organization");
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
  });

  it("preserves a user override made after a suggestion across a later candidate pick", () => {
    mockWikidata({
      hasSearched: true,
      candidates: [
        makeCandidate({ qid: "Q000001", label: "First", suggested_entity_type: "person" }),
        makeCandidate({ qid: "Q000002", label: "Second", suggested_entity_type: "place" }),
      ],
    });
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getAllByRole("radio")[0] as HTMLElement);
    expect(getTypeSelect().value).toBe("person");

    fireEvent.change(getTypeSelect(), { target: { value: "organization" } });
    fireEvent.click(screen.getAllByRole("radio")[1] as HTMLElement);

    expect(getTypeSelect().value).toBe("organization");
  });

  it("keeps a grounding made before any type when the user then picks a type (null suggestion)", () => {
    ground(makeCandidate({ suggested_entity_type: null, type_matches: null }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getByRole("radio"));
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();

    fireEvent.change(getTypeSelect(), { target: { value: "person" } });

    expect(getTypeSelect().value).toBe("person");
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();
    expect(screen.getByRole("radio")).toBeChecked();
  });

  it("clears the grounding when the type changes between two set values that differ from the suggestion", () => {
    ground(makeCandidate({ suggested_entity_type: "person" }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getByRole("radio"));
    expect(getTypeSelect().value).toBe("person");
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();

    fireEvent.change(getTypeSelect(), { target: { value: "organization" } });

    expect(screen.queryByText(/grounded to/i)).not.toBeInTheDocument();
  });

  it("clears the grounding when the name changes", () => {
    ground(makeCandidate({ suggested_entity_type: "person" }));
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getByRole("radio"));
    expect(screen.getByText(/grounded to/i)).toBeInTheDocument();

    fireEvent.change(getNameInput(), { target: { value: "Another Name" } });

    expect(screen.queryByText(/grounded to/i)).not.toBeInTheDocument();
  });

  it("a null-suggestion candidate picked after an applied one keeps the applied type and the grounding", () => {
    mockWikidata({
      hasSearched: true,
      candidates: [
        makeCandidate({ qid: "Q000001", label: "First", suggested_entity_type: "person" }),
        makeCandidate({ qid: "Q000002", label: "Second", suggested_entity_type: null }),
      ],
    });
    renderModal();
    fireEvent.change(getNameInput(), { target: { value: "Test Person" } });
    fireEvent.click(screen.getAllByRole("radio")[0] as HTMLElement);
    expect(getTypeSelect().value).toBe("person");

    fireEvent.click(screen.getAllByRole("radio")[1] as HTMLElement);

    expect(getTypeSelect().value).toBe("person");
    expect(screen.getByText(/Second \(Q000002\)/)).toBeInTheDocument();
  });
});
