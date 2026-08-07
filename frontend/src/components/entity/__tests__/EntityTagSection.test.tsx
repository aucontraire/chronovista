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

vi.mock("../../../api/entityMentions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../api/entityMentions")>();
  return { ...actual, addEntityTag: vi.fn() };
});

import { EntityTagSection } from "../EntityTagSection";
import { useCanonicalTags } from "../../../hooks/useCanonicalTags";
import { addEntityTag } from "../../../api/entityMentions";

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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useCanonicalTags).mockReturnValue(EMPTY);
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
