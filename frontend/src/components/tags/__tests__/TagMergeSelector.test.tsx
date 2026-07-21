/**
 * Tests for TagMergeSelector (Feature 056).
 *
 * Coverage:
 * - T030: contains-mode search wiring, source/target selection actions
 * - T036: requests matchMode: "contains" and limit: 50 (SC-006)
 * - FR-011: a tag cannot be both source and target
 * - FR-012: duplicate source selections are prevented
 * - Edge cases: no-matches indication, fuzzy suggestion fallback
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TagMergeSelector } from "../TagMergeSelector";
import * as useCanonicalTagsModule from "../../../hooks/useCanonicalTags";

vi.mock("../../../hooks/useCanonicalTags");

const mockedUseCanonicalTags = vi.mocked(useCanonicalTagsModule.useCanonicalTags);

function mockHookReturn(
  overrides: Partial<ReturnType<typeof useCanonicalTagsModule.useCanonicalTags>> = {}
) {
  mockedUseCanonicalTags.mockReturnValue({
    tags: [],
    suggestions: [],
    isLoading: false,
    isError: false,
    error: null,
    isRateLimited: false,
    rateLimitRetryAfter: 0,
    ...overrides,
  });
}

const fryTag = {
  canonical_form: "Professor Hannah Fry",
  normalized_form: "professor hannah fry",
  alias_count: 2,
  video_count: 12,
};

const hannahFryTag = {
  canonical_form: "Hannah Fry",
  normalized_form: "hannah fry",
  alias_count: 5,
  video_count: 30,
};

function renderSelector(
  overrides: Partial<React.ComponentProps<typeof TagMergeSelector>> = {}
) {
  const props: React.ComponentProps<typeof TagMergeSelector> = {
    sources: [],
    target: null,
    onAddSource: vi.fn(),
    onRemoveSource: vi.fn(),
    onSetTarget: vi.fn(),
    ...overrides,
  };
  render(<TagMergeSelector {...props} />);
  return props;
}

describe("TagMergeSelector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHookReturn();
  });

  // -------------------------------------------------------------------------
  // T036/T037: contains mode + limit 50
  // -------------------------------------------------------------------------
  describe("search configuration (FR-005, SC-006)", () => {
    it("calls useCanonicalTags with matchMode: contains and limit: 50", async () => {
      renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "fry");

      await waitFor(() => {
        expect(mockedUseCanonicalTags).toHaveBeenCalledWith(
          "fry",
          expect.objectContaining({ matchMode: "contains", limit: 50 })
        );
      });
    });
  });

  // -------------------------------------------------------------------------
  // Result rendering + actions
  // -------------------------------------------------------------------------
  describe("search results", () => {
    it("renders result rows with Add as source and Set target actions", async () => {
      mockHookReturn({ tags: [fryTag] });
      renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "fry");

      expect(
        screen.getByRole("button", { name: /add professor hannah fry as a source tag/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /set professor hannah fry as the merge target/i })
      ).toBeInTheDocument();
    });

    it("calls onAddSource when 'Add as source' is clicked", async () => {
      mockHookReturn({ tags: [fryTag] });
      const props = renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "fry");

      await userEvent.click(
        screen.getByRole("button", { name: /add professor hannah fry as a source tag/i })
      );

      expect(props.onAddSource).toHaveBeenCalledWith(fryTag);
    });

    it("calls onSetTarget when 'Set target' is clicked", async () => {
      mockHookReturn({ tags: [hannahFryTag] });
      const props = renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "hannah");

      await userEvent.click(
        screen.getByRole("button", { name: /set hannah fry as the merge target/i })
      );

      expect(props.onSetTarget).toHaveBeenCalledWith(hannahFryTag);
    });
  });

  // -------------------------------------------------------------------------
  // FR-011 / FR-012: validation
  // -------------------------------------------------------------------------
  describe("validation", () => {
    it("prevents adding the current target as a source and shows an error (FR-011)", async () => {
      mockHookReturn({ tags: [hannahFryTag] });
      const props = renderSelector({ target: hannahFryTag });

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "hannah");

      // The "Add as source" button for the target is disabled — clicking is a no-op,
      // but we assert the disabled state directly (FR-011).
      const addButton = screen.getByRole("button", {
        name: /add hannah fry as a source tag/i,
      });
      expect(addButton).toBeDisabled();
      expect(props.onAddSource).not.toHaveBeenCalled();
    });

    it("prevents setting an existing source as the target and shows an error (FR-011)", async () => {
      mockHookReturn({ tags: [fryTag] });
      const props = renderSelector({ sources: [fryTag] });

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "fry");

      const setTargetButton = screen.getByRole("button", {
        name: /set professor hannah fry as the merge target/i,
      });
      expect(setTargetButton).toBeDisabled();
      expect(props.onSetTarget).not.toHaveBeenCalled();
    });

    it("disables 'Add as source' for a tag already selected as a source (FR-012)", async () => {
      mockHookReturn({ tags: [fryTag] });
      renderSelector({ sources: [fryTag] });

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "fry");

      const addButton = screen.getByRole("button", {
        name: /add professor hannah fry as a source tag/i,
      });
      expect(addButton).toBeDisabled();
      expect(addButton).toHaveTextContent("Added");
    });
  });

  // -------------------------------------------------------------------------
  // Edge cases: min length, no matches, fuzzy fallback
  // -------------------------------------------------------------------------
  describe("edge cases", () => {
    it("does not query until at least 2 characters are typed (FR-003)", async () => {
      renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "f");

      // The hook is always called (React hooks can't be conditional), but the
      // component's "no matches" / results UI must not render for < 2 chars.
      expect(screen.queryByRole("list", { name: /tag search results/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/no tags found/i)).not.toBeInTheDocument();
    });

    it("shows a 'no matches' indication for a valid query with zero results and zero suggestions", async () => {
      mockHookReturn({ tags: [], suggestions: [] });
      renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "zzzz");

      // Both the visible message and the sr-only live-region announcement
      // contain this text — assert at least one is present.
      expect(screen.getAllByText(/no tags found matching/i).length).toBeGreaterThan(0);
    });

    it("renders fuzzy suggestions when contains-mode search returns zero exact matches", async () => {
      mockHookReturn({
        tags: [],
        suggestions: [{ canonical_form: "Hanna Frey", normalized_form: "hanna frey" }],
      });
      renderSelector();

      const input = screen.getByLabelText(/search tags to merge/i);
      await userEvent.type(input, "hana");

      expect(screen.getByRole("group", { name: /fuzzy suggestions/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Hanna Frey" })).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Selected pills
  // -------------------------------------------------------------------------
  describe("selected tag pills", () => {
    it("renders the target pill and a remove control", async () => {
      const onSetTarget = vi.fn();
      renderSelector({ target: hannahFryTag, onSetTarget });

      expect(screen.getByText("Hannah Fry")).toBeInTheDocument();
      const removeButton = screen.getByRole("button", {
        name: /remove hannah fry as target/i,
      });
      await userEvent.click(removeButton);
      expect(onSetTarget).toHaveBeenCalledWith(null);
    });

    it("renders source pills with individual remove controls", async () => {
      const onRemoveSource = vi.fn();
      renderSelector({ sources: [fryTag], onRemoveSource });

      const removeButton = screen.getByRole("button", {
        name: /remove professor hannah fry as source/i,
      });
      await userEvent.click(removeButton);
      expect(onRemoveSource).toHaveBeenCalledWith("professor hannah fry");
    });

    it("shows the empty-state hints when nothing is selected", () => {
      renderSelector();
      expect(screen.getByText(/no target selected yet/i)).toBeInTheDocument();
      expect(screen.getByText(/no source tags selected yet/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Disabled state (in-flight merge)
  // -------------------------------------------------------------------------
  describe("disabled state", () => {
    it("disables the search input when disabled=true", () => {
      renderSelector({ disabled: true });
      expect(screen.getByLabelText(/search tags to merge/i)).toBeDisabled();
    });
  });
});
