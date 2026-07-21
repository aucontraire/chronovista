/**
 * Tests for MergeTagsPage composition (Feature 056, T033).
 *
 * Child components (TagMergeSelector, MergeConfirmation, MergeResultBanner)
 * and the mutation hooks are mocked so this suite focuses purely on the
 * page's own wiring: empty-state gating, confirm/cancel/undo handlers, and
 * the request payloads passed to the mutations.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MergeTagsPage } from "../MergeTagsPage";
import { useMergeTags } from "../../hooks/useMergeTags";
import { useUndoMerge } from "../../hooks/useUndoMerge";
import type { SelectedMergeTag } from "../../types/canonical-tags";

vi.mock("../../hooks/useMergeTags");
vi.mock("../../hooks/useUndoMerge");

vi.mock("../../components/tags/TagMergeSelector", () => ({
  TagMergeSelector: (props: {
    sources: SelectedMergeTag[];
    target: SelectedMergeTag | null;
    onAddSource: (tag: SelectedMergeTag) => void;
    onSetTarget: (tag: SelectedMergeTag | null) => void;
    disabled?: boolean;
  }) => (
    <div data-testid="tag-merge-selector">
      <button onClick={() => props.onAddSource(fryTag)}>mock-add-source</button>
      <button onClick={() => props.onSetTarget(hannahFryTag)}>mock-set-target</button>
      <span data-testid="selector-disabled">{String(props.disabled ?? false)}</span>
    </div>
  ),
}));

vi.mock("../../components/tags/MergeConfirmation", () => ({
  MergeConfirmation: (props: {
    sources: SelectedMergeTag[];
    target: SelectedMergeTag;
    onConfirm: () => void;
    onCancel: () => void;
    isMerging: boolean;
  }) => (
    <div data-testid="merge-confirmation">
      <span>{props.sources.length} sources -&gt; {props.target.canonical_form}</span>
      <button onClick={props.onConfirm}>mock-confirm</button>
      <button onClick={props.onCancel}>mock-cancel</button>
      <span data-testid="is-merging">{String(props.isMerging)}</span>
    </div>
  ),
}));

vi.mock("../../components/tags/MergeResultBanner", () => ({
  MergeResultBanner: (props: {
    result: { operation_id: string };
    onUndo?: () => void;
    isUndoing?: boolean;
    undoSuccess?: boolean;
  }) => (
    <div data-testid="merge-result-banner">
      <span>{props.result.operation_id}</span>
      {props.onUndo && <button onClick={props.onUndo}>mock-undo</button>}
      <span data-testid="undo-success">{String(props.undoSuccess ?? false)}</span>
    </div>
  ),
}));

const mockedUseMergeTags = vi.mocked(useMergeTags);
const mockedUseUndoMerge = vi.mocked(useUndoMerge);

const fryTag: SelectedMergeTag = {
  canonical_form: "Professor Hannah Fry",
  normalized_form: "professor hannah fry",
  alias_count: 2,
  video_count: 12,
};

const hannahFryTag: SelectedMergeTag = {
  canonical_form: "Hannah Fry",
  normalized_form: "hannah fry",
  alias_count: 5,
  video_count: 30,
};

const mergeResult = {
  source_tags: ["Professor Hannah Fry"],
  target_tag: "Hannah Fry",
  aliases_moved: 2,
  new_alias_count: 7,
  new_video_count: 40,
  operation_id: "op-abc-123",
  entity_hint: null,
};

function mockMergeTags(overrides: Partial<ReturnType<typeof useMergeTags>> = {}) {
  const mutate = vi.fn();
  const reset = vi.fn();
  mockedUseMergeTags.mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    data: undefined,
    error: null,
    isPending: false,
    isError: false,
    isSuccess: false,
    reset,
    status: "idle",
    ...overrides,
  } as unknown as ReturnType<typeof useMergeTags>);
  return { mutate, reset };
}

function mockUndoMerge(overrides: Partial<ReturnType<typeof useUndoMerge>> = {}) {
  const mutate = vi.fn();
  const reset = vi.fn();
  mockedUseUndoMerge.mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    data: undefined,
    error: null,
    isPending: false,
    isError: false,
    isSuccess: false,
    reset,
    status: "idle",
    ...overrides,
  } as unknown as ReturnType<typeof useUndoMerge>);
  return { mutate, reset };
}

describe("MergeTagsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMergeTags();
    mockUndoMerge();
  });

  it("shows the empty-state prompt before any tag is selected", () => {
    render(<MergeTagsPage />);
    expect(screen.getByText(/search for tags above/i)).toBeInTheDocument();
    expect(screen.queryByTestId("merge-confirmation")).not.toBeInTheDocument();
  });

  it("shows MergeConfirmation once a source and target are both selected", async () => {
    render(<MergeTagsPage />);

    await userEvent.click(screen.getByText("mock-add-source"));
    await userEvent.click(screen.getByText("mock-set-target"));

    expect(screen.getByTestId("merge-confirmation")).toBeInTheDocument();
    expect(screen.getByText(/1 sources -> Hannah Fry/)).toBeInTheDocument();
    expect(screen.queryByText(/search for tags above/i)).not.toBeInTheDocument();
  });

  it("calls the merge mutation with the correct payload on confirm", async () => {
    const { mutate } = mockMergeTags();
    render(<MergeTagsPage />);

    await userEvent.click(screen.getByText("mock-add-source"));
    await userEvent.click(screen.getByText("mock-set-target"));
    await userEvent.click(screen.getByText("mock-confirm"));

    expect(mutate).toHaveBeenCalledWith(
      {
        source_normalized_forms: ["professor hannah fry"],
        target_normalized_form: "hannah fry",
      },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it("resets the selection when Cancel is clicked", async () => {
    render(<MergeTagsPage />);

    await userEvent.click(screen.getByText("mock-add-source"));
    await userEvent.click(screen.getByText("mock-set-target"));
    expect(screen.getByTestId("merge-confirmation")).toBeInTheDocument();

    await userEvent.click(screen.getByText("mock-cancel"));

    expect(screen.queryByTestId("merge-confirmation")).not.toBeInTheDocument();
    expect(screen.getByText(/search for tags above/i)).toBeInTheDocument();
  });

  it("shows the result banner and clears the selection after a successful merge", async () => {
    const { mutate } = mockMergeTags();
    mutate.mockImplementation((_req, opts: { onSuccess: (r: typeof mergeResult) => void }) => {
      opts.onSuccess(mergeResult);
    });

    render(<MergeTagsPage />);

    await userEvent.click(screen.getByText("mock-add-source"));
    await userEvent.click(screen.getByText("mock-set-target"));
    await userEvent.click(screen.getByText("mock-confirm"));

    expect(screen.getByTestId("merge-result-banner")).toBeInTheDocument();
    expect(screen.getByText("op-abc-123")).toBeInTheDocument();
    // Selection was cleared -> confirmation panel gone, empty state back
    expect(screen.queryByTestId("merge-confirmation")).not.toBeInTheDocument();
    expect(screen.getByText(/search for tags above/i)).toBeInTheDocument();
  });

  it("disables the selector while a merge is in flight", async () => {
    mockMergeTags({ isPending: true } as Partial<ReturnType<typeof useMergeTags>>);
    render(<MergeTagsPage />);

    expect(screen.getByTestId("selector-disabled")).toHaveTextContent("true");
  });

  it("wires the undo callback from the result banner to the undo mutation", async () => {
    const { mutate: mergeMutate } = mockMergeTags();
    mergeMutate.mockImplementation(
      (_req, opts: { onSuccess: (r: typeof mergeResult) => void }) => {
        opts.onSuccess(mergeResult);
      }
    );
    const { mutate: undoMutate } = mockUndoMerge();

    render(<MergeTagsPage />);

    await userEvent.click(screen.getByText("mock-add-source"));
    await userEvent.click(screen.getByText("mock-set-target"));
    await userEvent.click(screen.getByText("mock-confirm"));

    await userEvent.click(screen.getByText("mock-undo"));

    expect(undoMutate).toHaveBeenCalledWith(
      "op-abc-123",
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });
});
