/**
 * Tests for MergeConfirmation (Feature 056).
 *
 * Coverage:
 * - T031/T034: renders sources/target, triggers and displays the exact
 *   preview counts, optional reason field, confirm/cancel wiring
 * - FR-008/FR-008a: confirm is disabled until an exact preview succeeds
 * - Loading/error states for the preview mutation
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MergeConfirmation } from "../MergeConfirmation";
import type { SelectedMergeTag, MergePreview } from "../../../types/canonical-tags";
import { useMergePreview } from "../../../hooks/useMergePreview";

vi.mock("../../../hooks/useMergePreview");

const mockedUseMergePreview = vi.mocked(useMergePreview);

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

const mockPreview: MergePreview = {
  source_tags: ["Professor Hannah Fry"],
  target_tag: "Hannah Fry",
  resulting_alias_count: 7,
  resulting_video_count: 40,
  source_alias_count: 2,
  source_video_count: 12,
};

function mockPreviewHook(
  overrides: Partial<ReturnType<typeof useMergePreview>> = {}
) {
  const mutate = vi.fn();
  mockedUseMergePreview.mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    data: undefined,
    error: null,
    isPending: false,
    isError: false,
    isSuccess: false,
    isIdle: true,
    reset: vi.fn(),
    status: "idle",
    variables: undefined,
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    ...overrides,
  } as unknown as ReturnType<typeof useMergePreview>);
  return mutate;
}

function renderConfirmation(
  overrides: Partial<React.ComponentProps<typeof MergeConfirmation>> = {}
) {
  const props: React.ComponentProps<typeof MergeConfirmation> = {
    sources: [fryTag],
    target: hannahFryTag,
    reason: "",
    onReasonChange: vi.fn(),
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    isMerging: false,
    ...overrides,
  };
  render(<MergeConfirmation {...props} />);
  return props;
}

describe("MergeConfirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("triggers a preview request for the selected sources and target", () => {
    const mutate = mockPreviewHook();
    renderConfirmation();

    expect(mutate).toHaveBeenCalledWith({
      source_normalized_forms: ["professor hannah fry"],
      target_normalized_form: "hannah fry",
    });
  });

  it("renders the source tags and target tag", () => {
    mockPreviewHook();
    renderConfirmation();

    expect(screen.getByText("Professor Hannah Fry")).toBeInTheDocument();
    expect(screen.getByText("Hannah Fry")).toBeInTheDocument();
  });

  it("shows a loading indicator while the preview is pending", () => {
    mockPreviewHook({ isPending: true, status: "pending" } as Partial<
      ReturnType<typeof useMergePreview>
    >);
    renderConfirmation();

    expect(screen.getByRole("status")).toHaveTextContent(/calculating exact resulting counts/i);
  });

  it("renders exact preview counts once the preview succeeds (FR-008a)", () => {
    mockPreviewHook({
      isSuccess: true,
      isPending: false,
      status: "success",
      data: mockPreview,
    } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation();

    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("shows an error message and retry button when the preview fails", () => {
    mockPreviewHook({
      isError: true,
      status: "error",
      error: new Error("Tag not found: ghost-tag"),
    } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation();

    expect(screen.getByRole("alert")).toHaveTextContent("Tag not found: ghost-tag");
    expect(screen.getByRole("button", { name: /retry preview/i })).toBeInTheDocument();
  });

  it("disables the confirm button until the preview succeeds", () => {
    mockPreviewHook({ isPending: true } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation();

    expect(screen.getByRole("button", { name: /confirm merge/i })).toBeDisabled();
  });

  it("enables the confirm button once the preview succeeds", () => {
    mockPreviewHook({
      isSuccess: true,
      status: "success",
      data: mockPreview,
    } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation();

    expect(screen.getByRole("button", { name: /confirm merge/i })).toBeEnabled();
  });

  it("calls onConfirm when the confirm button is clicked", async () => {
    mockPreviewHook({
      isSuccess: true,
      status: "success",
      data: mockPreview,
    } as Partial<ReturnType<typeof useMergePreview>>);
    const props = renderConfirmation();

    await userEvent.click(screen.getByRole("button", { name: /confirm merge/i }));
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when the cancel button is clicked", async () => {
    mockPreviewHook();
    const props = renderConfirmation();

    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onReasonChange as the user types in the reason field", async () => {
    mockPreviewHook();
    const props = renderConfirmation();

    const textarea = screen.getByLabelText(/reason/i);
    await userEvent.type(textarea, "x");
    expect(props.onReasonChange).toHaveBeenCalledWith("x");
  });

  it("disables confirm and cancel while a merge is in flight", () => {
    mockPreviewHook({
      isSuccess: true,
      status: "success",
      data: mockPreview,
    } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation({ isMerging: true });

    expect(screen.getByRole("button", { name: /merging/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("supports multiple source tags in the summary list", () => {
    mockPreviewHook();
    renderConfirmation({
      sources: [
        fryTag,
        {
          canonical_form: "Dr. Hannah Fry",
          normalized_form: "dr hannah fry",
          alias_count: 1,
          video_count: 3,
        },
      ],
    });

    expect(screen.getByText("Professor Hannah Fry")).toBeInTheDocument();
    expect(screen.getByText("Dr. Hannah Fry")).toBeInTheDocument();
    expect(screen.getByText(/2 source tags/i)).toBeInTheDocument();
  });

  it("does not render an entity_hint field (belongs to the post-merge result banner)", () => {
    mockPreviewHook({
      isSuccess: true,
      status: "success",
      data: mockPreview,
    } as Partial<ReturnType<typeof useMergePreview>>);
    renderConfirmation();

    // MergePreview has no entity_hint field — nothing entity-related should render here.
    expect(screen.queryByText(/entity/i)).not.toBeInTheDocument();
  });
});
