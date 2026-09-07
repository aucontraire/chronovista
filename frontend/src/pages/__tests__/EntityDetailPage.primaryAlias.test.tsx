/**
 * EntityDetailPage — Primary (canonical) alias marker (Feature 075, #301).
 *
 * When an entity is created, its canonical name is also stored as an ordinary
 * name_variant alias (the "self-alias"). This suite verifies the entity detail
 * alias list marks the alias whose case/accent-folded name equals the entity's
 * folded canonical name with a "Primary" badge — and nothing else. Detection is
 * DERIVED at render time (no backend field), so it also covers the post-rename
 * state (the self-alias goes stale and nothing is marked) and fold-collisions.
 *
 * Neutral placeholder names only (public repo).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(() => ({
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
  })),
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

vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));
vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));
vi.mock("../../components/entity/CooccurringPanel", () => ({
  CooccurringPanel: () => null,
}));

vi.mock("../../api/entityMentions", () => ({
  createEntityAlias: vi.fn(),
  updateEntityAlias: vi.fn(),
  deleteEntityAlias: vi.fn(),
  undoAliasDeletion: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

import { useQuery } from "@tanstack/react-query";

const ENTITY_ID = "entity-uuid-075";

interface AliasFixture {
  id: string;
  alias_name: string;
  alias_type?: string;
  occurrence_count?: number;
  case_sensitive?: boolean;
}

function mockEntity(canonicalName: string, aliases: AliasFixture[]) {
  return {
    entity_id: ENTITY_ID,
    canonical_name: canonicalName,
    entity_type: "organization",
    description: null,
    status: "active",
    mention_count: 10,
    video_count: 3,
    by_source: { manual: 0, transcript: 3, title: 0, description: 0, tag: 0 },
    aliases: aliases.map((a) => ({
      id: a.id,
      alias_name: a.alias_name,
      alias_type: a.alias_type ?? "name_variant",
      occurrence_count: a.occurrence_count ?? 1,
      case_sensitive: a.case_sensitive ?? false,
    })),
    exclusion_patterns: [] as string[],
  };
}

function setEntity(entity: ReturnType<typeof mockEntity>) {
  vi.mocked(useQuery).mockReturnValue({
    data: entity,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useQuery>);
}

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
 * The row container for a given alias name, scoped to the Aliases section so a
 * name that also appears in the page header (the canonical name renders in the
 * `<h1>`) is not ambiguous.
 */
function aliasRow(aliasName: string): HTMLElement {
  const section = screen.getByRole("region", { name: /aliases/i });
  const nameEl = within(section).getByText(aliasName);
  const row = nameEl.closest("div");
  if (!row) throw new Error(`no row for alias "${aliasName}"`);
  return row as HTMLElement;
}

describe("EntityDetailPage — Primary alias marker (#301)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("(a) marks the alias equal to the canonical name as Primary", () => {
    setEntity(
      mockEntity("Acme Corporation", [
        { id: "a1", alias_name: "Acme Corporation" }, // self-alias
        { id: "a2", alias_name: "Acme", alias_type: "nickname" },
        { id: "a3", alias_name: "ACME Corp", alias_type: "abbreviation" },
      ])
    );
    renderPage();

    expect(within(aliasRow("Acme Corporation")).getByText("Primary")).toBeInTheDocument();
  });

  it("(b) does not mark ordinary aliases as Primary", () => {
    setEntity(
      mockEntity("Acme Corporation", [
        { id: "a1", alias_name: "Acme Corporation" },
        { id: "a2", alias_name: "Acme", alias_type: "nickname" },
        { id: "a3", alias_name: "ACME Corp", alias_type: "abbreviation" },
      ])
    );
    renderPage();

    // Exactly one Primary badge, and not on the ordinary rows.
    expect(screen.getAllByText("Primary")).toHaveLength(1);
    expect(within(aliasRow("Acme")).queryByText("Primary")).not.toBeInTheDocument();
    expect(within(aliasRow("ACME Corp")).queryByText("Primary")).not.toBeInTheDocument();
  });

  it("(c) marks an alias that differs from the canonical name only by case", () => {
    setEntity(
      mockEntity("Acme Corporation", [
        { id: "a1", alias_name: "acme corporation" }, // case-only difference
        { id: "a2", alias_name: "Globex", alias_type: "nickname" },
      ])
    );
    renderPage();

    expect(within(aliasRow("acme corporation")).getByText("Primary")).toBeInTheDocument();
    expect(within(aliasRow("Globex")).queryByText("Primary")).not.toBeInTheDocument();
  });

  it("(c') marks an alias that differs only by accent (fold match)", () => {
    // Canonical without accent, alias with accent -> fold equal -> Primary.
    const canonical = "Pena Group";
    const accented = "Peña Group"; // built literally; foldName strips the accent
    setEntity(
      mockEntity(canonical, [
        { id: "a1", alias_name: accented },
        { id: "a2", alias_name: "PG", alias_type: "abbreviation" },
      ])
    );
    renderPage();

    expect(within(aliasRow(accented)).getByText("Primary")).toBeInTheDocument();
    expect(within(aliasRow("PG")).queryByText("Primary")).not.toBeInTheDocument();
  });

  it("(d) marks nothing when no alias equals the canonical name", () => {
    setEntity(
      mockEntity("Acme Corporation", [
        { id: "a2", alias_name: "Acme", alias_type: "nickname" },
        { id: "a3", alias_name: "ACME Corp", alias_type: "abbreviation" },
      ])
    );
    renderPage();

    expect(screen.queryByText("Primary")).not.toBeInTheDocument();
    // list still renders normally
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("(e) post-rename: canonical folds to none of the aliases -> no Primary badge", () => {
    // Entity renamed to "Acme Global"; the stale self-alias still reads
    // "Acme Corporation" and no alias folds to the new canonical name.
    setEntity(
      mockEntity("Acme Global", [
        { id: "a1", alias_name: "Acme Corporation" }, // stale self-alias
        { id: "a2", alias_name: "Acme", alias_type: "nickname" },
      ])
    );
    renderPage();

    expect(screen.queryByText("Primary")).not.toBeInTheDocument();
    expect(screen.getByText("Acme Corporation")).toBeInTheDocument();
  });

  it("(f) fold-collision: two aliases fold to the canonical name -> both marked, no throw", () => {
    setEntity(
      mockEntity("Pena Group", [
        { id: "a1", alias_name: "Pena Group" },
        { id: "a2", alias_name: "Peña Group" }, // folds to the same value
      ])
    );
    renderPage();

    expect(screen.getAllByText("Primary")).toHaveLength(2);
  });
});
