/**
 * Feature 072 — the /entities page searches accent-insensitively AND across
 * aliases. Accent-insensitivity is enforced entirely in the backend; the
 * frontend's job is to OPT IN by sending `search_aliases=true` on every
 * entity-list request.
 *
 * Feature 110 removed the `exclude_alias_types=asr_error` param: transcript-error
 * forms were relocated out of entity_aliases, so the name store holds only names
 * and there is nothing to exclude. This test now also pins that the param is NO
 * LONGER sent (re-adding it would be dead weight).
 *
 * This test mocks only the network boundary (`fetchEntities`) and drives the REAL
 * `useEntities` hook, so it verifies the page -> hook -> request path end to end.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../api/entityMentions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/entityMentions")>();
  return { ...actual, fetchEntities: vi.fn() };
});

import { fetchEntities } from "../../api/entityMentions";
import { EntitiesPage } from "../EntitiesPage";

const EMPTY_PAGE = {
  data: [],
  pagination: { total: 0, limit: 20, offset: 0, has_more: false },
};

function renderPage(entry = "/entities") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <EntitiesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EntitiesPage entity-search request params (Feature 072)", () => {
  beforeEach(() => {
    vi.mocked(fetchEntities).mockReset();
    vi.mocked(fetchEntities).mockResolvedValue(EMPTY_PAGE);
  });

  it("sends search_aliases=true and no exclude_alias_types param", async () => {
    renderPage();

    await waitFor(() => expect(fetchEntities).toHaveBeenCalled());

    const params = vi.mocked(fetchEntities).mock.calls[0]?.[0];
    expect(params).toEqual(
      expect.objectContaining({
        search_aliases: true,
      }),
    );
    expect(params).not.toHaveProperty("exclude_alias_types");
  });

  it("keeps the alias param when a search term is present", async () => {
    renderPage("/entities?search=renee");

    await waitFor(() => expect(fetchEntities).toHaveBeenCalled());

    const params = vi.mocked(fetchEntities).mock.calls[0]?.[0];
    expect(params).toEqual(
      expect.objectContaining({
        search: "renee",
        search_aliases: true,
      }),
    );
    expect(params).not.toHaveProperty("exclude_alias_types");
  });
});
