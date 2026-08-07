/**
 * Tests for EntityTagSection (Feature 064, US1/US2).
 *
 * The assertions that matter are on the **request payload** and on the ARIA
 * contract, not on the fact that a call happened. A test asserting only
 * "addEntityTag was called" stays green while the payload carries a field the
 * API rejects — which is exactly the shape of test that stayed green all
 * evening while a `display_name` was writing an alias onto another entity.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../hooks/useCanonicalTags", () => ({
  useCanonicalTags: vi.fn(),
}));

vi.mock("../../../hooks/useEntityTags", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../hooks/useEntityTags")>();
  return { ...actual, useEntityTags: vi.fn() };
});

vi.mock("../../../api/entityMentions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../api/entityMentions")>();
  return {
    ...actual,
    addEntityTag: vi.fn(),
    unMergeEntityTag: vi.fn(),
    unlinkEntityTag: vi.fn(),
  };
});

import { EntityTagSection } from "../EntityTagSection";
import { useCanonicalTags } from "../../../hooks/useCanonicalTags";
import { useEntityTags } from "../../../hooks/useEntityTags";
import {
  addEntityTag,
  unlinkEntityTag,
  unMergeEntityTag,
} from "../../../api/entityMentions";

const ENTITY_ID = "entity-uuid-064";
const ENTITY_NAME = "Harbour Board";

const MATCH = {
  canonical_form: "Harbour Brd",
  normalized_form: "harbour brd",
  alias_count: 2,
  video_count: 3,
};

const EMPTY = {
  tags: [] as (typeof MATCH)[],
  suggestions: [],
  isLoading: false,
  isError: false,
  error: null,
  isRateLimited: false,
  rateLimitRetryAfter: 0,
};

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EntityTagSection entityId={ENTITY_ID} entityName={ENTITY_NAME} />
    </QueryClientProvider>
  );
}

function section() {
  return within(screen.getByRole("region", { name: "Tags" }));
}

async function pickMatch(user: ReturnType<typeof userEvent.setup>) {
  vi.mocked(useCanonicalTags).mockReturnValue({ ...EMPTY, tags: [MATCH] });
  await user.type(screen.getByLabelText("Search tags"), "harbour");
  await user.click(await section().findByRole("option", { name: /Harbour Brd/ }));
}

/** Shape a useEntityTags result without repeating the query fields. */
function tagsResult(linked: unknown[], needsAttention = false) {
  return {
    data: { linked_tags: linked, needs_attention: needsAttention },
    isLoading: false,
  } as unknown as ReturnType<typeof useEntityTags>;
}

const WITH_MERGED = {
  canonical_form: "Harbour Board",
  normalized_form: "harbour board",
  video_count: 12,
  alias_count: 4,
  merged_tags: [
    {
      canonical_form: "Harbour Brd",
      normalized_form: "harbour brd",
      contributed_video_count: 3,
      operation_id: "op-1" as string | null,
      operation_source_count: 1,
    },
  ],
};

const LINKED_TAG = {
  canonical_form: "Harbour Board",
  normalized_form: "harbour board",
  video_count: 12,
  alias_count: 4,
  merged_tags: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useCanonicalTags).mockReturnValue(EMPTY);
  vi.mocked(useEntityTags).mockReturnValue(tagsResult([]));
});

describe("EntityTagSection", () => {
  it("renders the section", () => {
    renderSection();
    expect(screen.getByRole("heading", { name: "Tags" })).toBeInTheDocument();
  });

  it("asks the search to exclude tags that already represent an entity", async () => {
    const user = userEvent.setup();
    renderSection();
    await user.type(screen.getByLabelText("Search tags"), "harbour");

    // FR-007. Without this the picker offers another entity's tag, and acting
    // on it would steal that tag.
    expect(vi.mocked(useCanonicalTags)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ excludeLinked: true })
    );
  });

  it("sends only the normalized form", async () => {
    const user = userEvent.setup();
    vi.mocked(addEntityTag).mockResolvedValue({
      operation: "merge",
      operation_id: "op-1",
      target_normalized_form: "harbour board",
      entity_video_count: 4,
    });

    renderSection();
    await pickMatch(user);
    await user.click(section().getByRole("button", { name: /^Attach "/ }));

    await waitFor(() => expect(addEntityTag).toHaveBeenCalledTimes(1));
    // The server decides between link and merge from the entity's state.
    // Sending an entity_type would be a 409 whenever it disagreed with the
    // target, and this component cannot know that it agrees.
    expect(vi.mocked(addEntityTag).mock.calls[0]).toEqual([
      ENTITY_ID,
      "harbour brd",
    ]);
  });

  it("says merged when the server merged, not linked", async () => {
    const user = userEvent.setup();
    vi.mocked(addEntityTag).mockResolvedValue({
      operation: "merge",
      operation_id: "op-1",
      target_normalized_form: "harbour board",
      entity_video_count: 4,
    });

    renderSection();
    await pickMatch(user);
    await user.click(section().getByRole("button", { name: /^Attach "/ }));

    // "Linked" would misdescribe what happened: the chosen tag was folded into
    // the entity's existing one and no longer exists separately.
    expect(await section().findByText(/Merged "Harbour Brd" into/)).toBeInTheDocument();
    expect(section().queryByText(/^Linked/)).not.toBeInTheDocument();
  });

  it("reports how many videos now count", async () => {
    const user = userEvent.setup();
    vi.mocked(addEntityTag).mockResolvedValue({
      operation: "link",
      operation_id: "op-1",
      target_normalized_form: "harbour brd",
      entity_video_count: 3,
    });

    renderSection();
    await pickMatch(user);
    await user.click(section().getByRole("button", { name: /^Attach "/ }));

    expect(
      await section().findByText(/3 videos now count toward Harbour Board/)
    ).toBeInTheDocument();
  });

  it("surfaces the server's reason on a conflict", async () => {
    const user = userEvent.setup();
    vi.mocked(addEntityTag).mockRejectedValue({
      status: 409,
      detail: "Tag 'harbour brd' already represents 'Other Board'.",
    });

    renderSection();
    await pickMatch(user);
    await user.click(section().getByRole("button", { name: /^Attach "/ }));

    // Only the server knows which entity holds the tag. A generic message
    // would leave the curator with no next step.
    expect(await section().findByRole("alert")).toHaveTextContent("Other Board");
  });

  it("does not claim success when the request fails", async () => {
    const user = userEvent.setup();
    vi.mocked(addEntityTag).mockRejectedValue({ status: 500 });

    renderSection();
    await pickMatch(user);
    await user.click(section().getByRole("button", { name: /^Attach "/ }));

    await section().findByRole("alert");
    expect(section().queryByText(/now count toward/)).not.toBeInTheDocument();
  });

  it("exposes a combobox with a listbox and options", async () => {
    const user = userEvent.setup();
    vi.mocked(useCanonicalTags).mockReturnValue({ ...EMPTY, tags: [MATCH] });

    renderSection();
    const input = screen.getByRole("combobox", { name: "Search tags" });
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.type(input, "harbour");

    // FR-023: matching TagAutocomplete rather than the plainer picker.
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(section().getByRole("listbox")).toBeInTheDocument();
    expect(section().getAllByRole("option")).toHaveLength(1);
  });

  it("moves through results with the arrow keys", async () => {
    const user = userEvent.setup();
    const second = { ...MATCH, canonical_form: "Harbour B", normalized_form: "harbour b" };
    vi.mocked(useCanonicalTags).mockReturnValue({
      ...EMPTY,
      tags: [MATCH, second],
    });

    renderSection();
    const input = screen.getByRole("combobox", { name: "Search tags" });
    await user.type(input, "harbour");

    await user.keyboard("{ArrowDown}");
    expect(section().getAllByRole("option")[0]).toHaveAttribute(
      "aria-selected",
      "true"
    );
    await user.keyboard("{ArrowDown}");
    expect(section().getAllByRole("option")[1]).toHaveAttribute(
      "aria-selected",
      "true"
    );
    // Wraps, so the list is fully reachable without a mouse.
    await user.keyboard("{ArrowDown}");
    expect(section().getAllByRole("option")[0]).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("selects the highlighted option with Enter", async () => {
    const user = userEvent.setup();
    vi.mocked(useCanonicalTags).mockReturnValue({ ...EMPTY, tags: [MATCH] });

    renderSection();
    const input = screen.getByRole("combobox", { name: "Search tags" });
    await user.type(input, "harbour");
    await user.keyboard("{ArrowDown}{Enter}");

    expect(
      section().getByRole("button", { name: /^Attach "Harbour Brd"/ })
    ).toBeInTheDocument();
  });

  it("shows the tag that represents the entity", () => {
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([LINKED_TAG]));
    renderSection();

    expect(section().getByText("Harbour Board")).toBeInTheDocument();
    expect(section().getByText(/12 videos · 4 variations/)).toBeInTheDocument();
  });

  it("states plainly when no tag is linked", () => {
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([]));
    renderSection();

    // The empty state is the signal that the entity is under-counted, so it
    // has to say so rather than render nothing.
    expect(
      section().getByText(/No tag is linked to this entity/)
    ).toBeInTheDocument();
  });

  it("keeps what the tag absorbed behind a disclosure, closed by default", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    renderSection();

    // FR-012: the group's history is corrective detail, not the first thing a
    // curator needs.
    expect(section().queryByText(/brought 3 videos/)).not.toBeInTheDocument();
    const toggle = section().getByRole("button", { name: /Show 1 merged tag/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(section().getByText(/Harbour Brd/)).toBeInTheDocument();
    // "brought" not "has": a merged tag owns no videos now, and wording it as
    // a live count invites adding it to the parent's, double counting overlap.
    expect(section().getByText(/brought 3 videos/)).toBeInTheDocument();
  });

  it("uses the two verbs distinctly", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    renderSection();

    // Un-merge acts on a tag inside the group; Unlink empties the entity of
    // tags. Naming both "remove" is the conflation this feature corrects.
    expect(section().getByRole("button", { name: "Unlink" })).toBeInTheDocument();
    await user.click(section().getByRole("button", { name: /Show 1 merged tag/ }));
    expect(
      section().getByRole("button", { name: "Un-merge" })
    ).toBeInTheDocument();
  });

  it("un-merges a tag and says it is searchable again", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    vi.mocked(unMergeEntityTag).mockResolvedValue({
      restored: ["harbour brd"],
      operation_id: "op-1",
    });
    renderSection();

    await user.click(section().getByRole("button", { name: /Show 1 merged tag/ }));
    await user.click(section().getByRole("button", { name: "Un-merge" }));

    await waitFor(() => expect(unMergeEntityTag).toHaveBeenCalled());
    expect(vi.mocked(unMergeEntityTag).mock.calls[0]).toEqual([
      ENTITY_ID,
      "harbour brd",
      false,
    ]);
    expect(await section().findByText(/searchable again/)).toBeInTheDocument();
  });

  it("turns a multi-source refusal into a confirmation naming the tags", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    vi.mocked(unMergeEntityTag)
      .mockRejectedValueOnce({
        status: 409,
        detail:
          "Un-merging 'Harbour Brd' also restores 1 other tag, because they were merged in one operation: The Harbour Board.",
      })
      .mockResolvedValueOnce({ restored: ["harbour brd"], operation_id: "op-1" });
    renderSection();

    await user.click(section().getByRole("button", { name: /Show 1 merged tag/ }));
    await user.click(section().getByRole("button", { name: "Un-merge" }));

    // FR-016: a count alone cannot be judged, so the prompt repeats the names
    // the server supplied rather than asking a bare "are you sure?".
    const prompt = await section().findByRole("alert");
    expect(prompt).toHaveTextContent("The Harbour Board");

    await user.click(section().getByRole("button", { name: /Un-merge all of them/ }));

    await waitFor(() =>
      expect(vi.mocked(unMergeEntityTag).mock.calls[1]).toEqual([
        ENTITY_ID,
        "harbour brd",
        true,
      ])
    );
  });

  it("surfaces the reason when unlink is refused", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    vi.mocked(unlinkEntityTag).mockRejectedValue({
      status: 409,
      detail:
        "1 tag is merged into 'Harbour Board'. Un-merge it first — their raw forms live on this tag.",
    });
    renderSection();

    await user.click(section().getByRole("button", { name: "Unlink" }));

    expect(await section().findByRole("alert")).toHaveTextContent(
      /Un-merge it first/
    );
  });

  it("offers no un-merge control when no operation can reverse it", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(
      tagsResult([
        {
          ...WITH_MERGED,
          merged_tags: [{ ...WITH_MERGED.merged_tags[0], operation_id: null }],
        },
      ])
    );
    renderSection();

    await user.click(section().getByRole("button", { name: /Show 1 merged tag/ }));
    // Offering a control that cannot work is worse than omitting it.
    expect(
      section().queryByRole("button", { name: "Un-merge" })
    ).not.toBeInTheDocument();
  });

  it("flags an entity carrying more than one linked tag", () => {
    vi.mocked(useEntityTags).mockReturnValue(
      tagsResult(
        [LINKED_TAG, { ...LINKED_TAG, normalized_form: "harbour b", canonical_form: "Harbour B" }],
        true
      )
    );
    renderSection();

    // FR-011a: render the legacy state as needing repair, without inventing a
    // primary among them.
    expect(section().getByRole("alert")).toHaveTextContent(
      /2 tags representing it/
    );
  });

  it("is fully operable by keyboard alone", async () => {
    const user = userEvent.setup();
    vi.mocked(useEntityTags).mockReturnValue(tagsResult([WITH_MERGED]));
    vi.mocked(useCanonicalTags).mockReturnValue({ ...EMPTY, tags: [MATCH] });
    vi.mocked(addEntityTag).mockResolvedValue({
      operation: "merge",
      operation_id: "op-1",
      target_normalized_form: "harbour board",
      entity_video_count: 4,
    });
    renderSection();

    // FR-025: every control reachable and operable without a pointer. Tab
    // order alone is not enough — the listbox is only navigable by arrow key,
    // and the disclosure and both verbs must be activatable from the keyboard.
    await user.tab();
    expect(section().getByRole("button", { name: /Show 1 merged tag/ })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(section().getByRole("button", { name: "Un-merge" })).toBeInTheDocument();

    const input = screen.getByRole("combobox", { name: "Search tags" });
    input.focus();
    await user.keyboard("harbour{ArrowDown}{Enter}");
    expect(
      section().getByRole("button", { name: /^Attach "Harbour Brd"/ })
    ).toBeInTheDocument();

    // Escape abandons the selection without reaching for a Cancel button.
    await user.keyboard("{Escape}");
    expect(
      section().queryByRole("button", { name: /^Attach "/ })
    ).not.toBeInTheDocument();
  });

  it("offers no attach button until a tag is chosen", async () => {
    const user = userEvent.setup();
    vi.mocked(useCanonicalTags).mockReturnValue({ ...EMPTY, tags: [MATCH] });

    renderSection();
    await user.type(screen.getByLabelText("Search tags"), "harbour");

    expect(
      section().queryByRole("button", { name: /^Attach "/ })
    ).not.toBeInTheDocument();
  });
});
