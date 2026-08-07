/**
 * Tests for the "Link an existing tag" section on EntityDetailPage (#183).
 *
 * The assertions that matter are on the *payload* sent to classifyTag, not on
 * the fact that it was called. The endpoint treats a disagreeing entity_type
 * as a 409, so a UI that helpfully included the entity's own type would break
 * every link — and a test asserting only "classifyTag was called" would pass
 * while it did.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(),
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
  useDeleteManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  })),
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
  useUpdateEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    reset: vi.fn(),
  })),
}));

vi.mock("../../hooks/useCanonicalTags", () => ({
  useCanonicalTags: vi.fn(),
}));

vi.mock("../../api/entityMentions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/entityMentions")>();
  return {
    ...actual,
    classifyTag: vi.fn(),
    createEntityAlias: vi.fn(),
    updateEntityAlias: vi.fn(),
  };
});

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));
vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";
import { useCanonicalTags } from "../../hooks/useCanonicalTags";
import { classifyTag } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-183";

const mockEntity = {
  entity_id: ENTITY_ID,
  canonical_name: "Harbour Authority",
  entity_type: "organization",
  description: null,
  status: "active",
  mention_count: 0,
  video_count: 0,
  aliases: [] as { alias_name: string; alias_type: string }[],
  exclusion_patterns: [] as string[],
};

const MATCHING_TAG = {
  canonical_form: "Harbour Authority",
  normalized_form: "harbour authority",
  alias_count: 2,
  video_count: 4,
};

const defaultCanonicalTags = {
  tags: [] as (typeof MATCHING_TAG)[],
  suggestions: [],
  isLoading: false,
  isError: false,
  error: null,
  isRateLimited: false,
  rateLimitRetryAfter: 0,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
        <Routes>
          <Route path="/entities/:entityId" element={<EntityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/**
 * The section, scoped.
 *
 * Queries must be scoped rather than global: the tag and the entity share a
 * name here, which is the case the feature exists for, so an unscoped search
 * for the tag's name also matches the entity name editor in the page header.
 */
function linkSection() {
  return within(
    screen.getByRole("region", { name: "Link an existing tag" })
  );
}

/** Type a query, then pick the matching tag from the results list. */
async function selectMatchingTag(user: ReturnType<typeof userEvent.setup>) {
  vi.mocked(useCanonicalTags).mockReturnValue({
    ...defaultCanonicalTags,
    tags: [MATCHING_TAG],
  });
  await user.type(screen.getByLabelText("Search tags"), "harbour");
  await user.click(
    await linkSection().findByRole("button", { name: /4 videos/ })
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useQuery).mockReturnValue({
    data: mockEntity,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useQuery>);
  vi.mocked(useEntityVideos).mockReturnValue({
    videos: [],
    total: null,
    pagination: null,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
  } as unknown as ReturnType<typeof useEntityVideos>);
  vi.mocked(useCanonicalTags).mockReturnValue(defaultCanonicalTags);
});

describe("EntityDetailPage — link an existing tag", () => {
  it("renders the section", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: "Link an existing tag" })
    ).toBeInTheDocument();
  });

  it("sends link_entity_id and omits entity_type", async () => {
    const user = userEvent.setup();
    vi.mocked(classifyTag).mockResolvedValue({
      entity_id: ENTITY_ID,
      canonical_name: "Harbour Authority",
      entity_type: "organization",
      description: null,
      alias_count: 1,
      entity_created: false,
      operation_id: "op-1",
    });

    renderPage();
    await selectMatchingTag(user);
    await user.click(linkSection().getByRole("button", { name: /^Link "/ }));

    await waitFor(() => expect(classifyTag).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(classifyTag).mock.calls[0]?.[0];
    expect(payload).toEqual({
      normalized_form: "harbour authority",
      link_entity_id: ENTITY_ID,
    });
    // Sending the entity's own type looks harmless and is a 409 — the backend
    // treats any supplied type that disagrees with the target as a conflict,
    // and this page has no guarantee the two agree.
    expect(payload).not.toHaveProperty("entity_type");
  });

  it("reports how many videos the link brings", async () => {
    const user = userEvent.setup();
    vi.mocked(classifyTag).mockResolvedValue({
      entity_id: ENTITY_ID,
      canonical_name: "Harbour Authority",
      entity_type: "organization",
      description: null,
      alias_count: 1,
      entity_created: false,
      operation_id: "op-1",
    });

    renderPage();
    await selectMatchingTag(user);
    await user.click(linkSection().getByRole("button", { name: /^Link "/ }));

    // The video count above is the only other evidence anything happened, so
    // the confirmation has to state the consequence rather than say "Done".
    expect(await linkSection().findByText(/4 videos now count toward/)).toBeInTheDocument();
  });

  it("surfaces the server's reason on a conflict rather than a generic message", async () => {
    const user = userEvent.setup();
    vi.mocked(classifyTag).mockRejectedValue({
      status: 409,
      detail: "Tag 'harbour authority' is already classified as 'place'.",
    });

    renderPage();
    await selectMatchingTag(user);
    await user.click(linkSection().getByRole("button", { name: /^Link "/ }));

    // A generic "already linked" would strand the user; the server names which
    // entity or type is in the way, which is the only actionable part.
    expect(await linkSection().findByRole("alert")).toHaveTextContent(
      "already classified as 'place'"
    );
  });

  it("falls back to its own message when the server sends no detail", async () => {
    const user = userEvent.setup();
    vi.mocked(classifyTag).mockRejectedValue({ status: 409 });

    renderPage();
    await selectMatchingTag(user);
    await user.click(linkSection().getByRole("button", { name: /^Link "/ }));

    expect(await linkSection().findByRole("alert")).toHaveTextContent(
      /already linked to an entity/
    );
  });

  it("does not claim success when the request fails", async () => {
    const user = userEvent.setup();
    vi.mocked(classifyTag).mockRejectedValue({ status: 500 });

    renderPage();
    await selectMatchingTag(user);
    await user.click(linkSection().getByRole("button", { name: /^Link "/ }));

    await linkSection().findByRole("alert");
    expect(linkSection().queryByText(/now count toward/)).not.toBeInTheDocument();
  });

  it("offers no link button until a tag is chosen", async () => {
    const user = userEvent.setup();
    vi.mocked(useCanonicalTags).mockReturnValue({
      ...defaultCanonicalTags,
      tags: [MATCHING_TAG],
    });

    renderPage();
    await user.type(screen.getByLabelText("Search tags"), "harbour");

    expect(
      linkSection().queryByRole("button", { name: /^Link "/ })
    ).not.toBeInTheDocument();
  });
});
