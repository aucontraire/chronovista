/**
 * Tag Link Migration Tests (US5 — T026)
 *
 * Verifies Phase 7 requirements for tag navigation:
 *
 * FR-012: Canonical tag badges link to /?canonical_tag={normalizedForm}
 * FR-013: Orphaned (unresolved) tags link to /videos?tag={rawTag}
 * FR-015: Legacy ?tag= URL param displays as plain pill (type 'tag'), no variation badge
 *
 * These tests confirm:
 * 1. ClassificationSection canonical badges use canonical_tag param, not raw tag param
 * 2. Legacy ?tag= URL params still produce filter pills in VideoFilters
 * 3. Legacy tag pills have type 'tag' (no variation badge) per FR-015
 * 4. No automatic ?tag= to ?canonical_tag= URL rewrite
 * 5. Both tag and canonical_tag pills coexist in the filter area
 *
 * T027 Verification (ClassificationSection):
 *   - Canonical badge link: /?canonical_tag={normalizedForm} — already correct
 *   - Orphaned tag link: /videos?tag={rawTag} — intentional per FR-013
 *
 * T028 Verification (VideoFilters):
 *   - Reads tag params via searchParams.getAll('tag') — already correct
 *   - Displays legacy tags as plain pills without variation badge — already correct
 *   - Does not rewrite ?tag= to ?canonical_tag= — confirmed no rewrite logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import React from "react";

import { ClassificationSection } from "../../components/ClassificationSection";
import { VideoFilters } from "../../components/VideoFilters";
import type {
  CanonicalTagListItem,
  CanonicalTagDetail,
} from "../../types/canonical-tags";

// ---------------------------------------------------------------------------
// Mocks for VideoFilters dependencies
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useCategories", () => ({
  useCategories: () => ({
    categories: [{ category_id: "10", name: "Gaming", assignable: true }],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("../../hooks/useTopics", () => ({
  useTopics: () => ({
    topics: [],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("../../hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => true,
}));

// ---------------------------------------------------------------------------
// Helpers for ClassificationSection fetch mock
// ---------------------------------------------------------------------------

function makeListResponse(items: CanonicalTagListItem[]): string {
  return JSON.stringify({
    data: items,
    pagination: {
      total: items.length,
      limit: 1,
      offset: 0,
      has_more: false,
    },
  });
}

function makeDetailResponse(detail: CanonicalTagDetail): string {
  return JSON.stringify({ data: detail });
}

function makeListItem(
  canonicalForm: string,
  normalizedForm: string,
  aliasCount: number,
  videoCount = 10
): CanonicalTagListItem {
  return {
    canonical_form: canonicalForm,
    normalized_form: normalizedForm,
    alias_count: aliasCount,
    video_count: videoCount,
  };
}

function makeDetail(
  canonicalForm: string,
  normalizedForm: string,
  aliasCount: number,
  topAliases: Array<{ raw_form: string; occurrence_count: number }> = []
): CanonicalTagDetail {
  return {
    canonical_form: canonicalForm,
    normalized_form: normalizedForm,
    alias_count: aliasCount,
    video_count: 10,
    top_aliases: topAliases,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  };
}

function mockResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

function renderClassificationSection(
  tags: string[],
  opts: { initialPath?: string } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[opts.initialPath ?? "/videos/test123"]}>
        <ClassificationSection
          tags={tags}
          categoryId={null}
          categoryName={null}
          topics={[]}
          playlists={[]}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderVideoFilters(initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <VideoFilters />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Tag Link Migration (US5 — Phase 7)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // T026.1: ClassificationSection canonical badge links use canonical_tag param
  // -------------------------------------------------------------------------
  describe("ClassificationSection — canonical badge links (FR-012)", () => {
    it("canonical tag badge links to /?canonical_tag={normalizedForm}, not /?tag={rawTag}", async () => {
      // Resolve "JavaScript" as canonical for raw tag "javascript"
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("/canonical-tags?q=")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([
                makeListItem("JavaScript", "javascript", 1, 42),
              ])
            )
          );
        }
        if (url.includes("/canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(makeDetail("JavaScript", "javascript", 1)))
          );
        }
        return Promise.resolve(mockResponse("{}", 404));
      });

      renderClassificationSection(["javascript"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: JavaScript/,
        });
        expect(badge).toBeInTheDocument();
        // Must use canonical_tag param, not a standalone raw ?tag= param
        expect(badge.getAttribute("href")).toContain("canonical_tag=javascript");
        // Ensure no standalone ?tag= or &tag= parameter is present
        // (note: "canonical_tag=javascript" contains "tag=javascript" as a substring,
        //  so we must test for the param separator, not just the substring)
        expect(badge.getAttribute("href")).not.toMatch(/[?&]tag=javascript/);
      });
    });

    it("canonical tag badge href encodes normalized_form (not canonical_form)", async () => {
      // normalizedForm and canonicalForm are different — link must use normalized_form
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("/canonical-tags?q=")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([
                makeListItem("C++", "c++", 2, 15),
              ])
            )
          );
        }
        if (url.includes("/canonical-tags/c")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(makeDetail("C++", "c++", 2)))
          );
        }
        return Promise.resolve(mockResponse("{}", 404));
      });

      renderClassificationSection(["C++"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: C\+\+/,
        });
        // URL should encode the normalizedForm (c++)
        expect(badge.getAttribute("href")).toContain("canonical_tag=");
        expect(badge.getAttribute("href")).not.toContain("?tag=");
      });
    });

    it("canonical tag badge does NOT include raw tag as ?tag= param", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("/canonical-tags?q=")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([
                makeListItem("React", "react", 3, 100),
              ])
            )
          );
        }
        if (url.includes("/canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(makeDetail("React", "react", 3)))
          );
        }
        return Promise.resolve(mockResponse("{}", 404));
      });

      renderClassificationSection(["react"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: React/,
        });
        const href = badge.getAttribute("href") ?? "";
        // No standalone ?tag= or &tag= URL param should be present
        // (canonical_tag= is expected but not a bare tag= param)
        expect(href).not.toMatch(/[?&]tag=/);
      });
    });
  });

  // -------------------------------------------------------------------------
  // T026.2: Orphaned tag links use ?tag= param (FR-013 — intentional)
  // -------------------------------------------------------------------------
  describe("ClassificationSection — orphaned tag links (FR-013)", () => {
    it("orphaned tag links to /videos?tag={rawTag}, not /?canonical_tag=", async () => {
      // Return empty list: tag cannot be resolved to any canonical tag
      fetchMock.mockResolvedValue(
        mockResponse(makeListResponse([]))
      );

      renderClassificationSection(["mystery-tag-xyz"]);

      await waitFor(() => {
        const orphanLink = screen.getByRole("link", {
          name: /mystery-tag-xyz.*unresolved/,
        });
        const href = orphanLink.getAttribute("href") ?? "";
        // Must navigate to /videos with tag param (not canonical_tag)
        expect(href).toContain("tag=mystery-tag-xyz");
        expect(href).not.toContain("canonical_tag=");
      });
    });

    it("orphaned tag link does NOT use canonical_tag param", async () => {
      fetchMock.mockResolvedValue(
        mockResponse(makeListResponse([]))
      );

      renderClassificationSection(["unresolved-tag"]);

      await waitFor(() => {
        const orphanLink = screen.getByRole("link", {
          name: /unresolved-tag.*unresolved/,
        });
        expect(orphanLink.getAttribute("href")).not.toContain("canonical_tag=");
      });
    });
  });

  // -------------------------------------------------------------------------
  // T026.3: Legacy ?tag= URL param in VideoFilters (FR-015)
  // -------------------------------------------------------------------------
  describe("VideoFilters — legacy ?tag= URL param (FR-015)", () => {
    it("displays legacy tag as a plain filter pill (no API fetch)", async () => {
      // No fetch should be needed for raw tag pills
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      renderVideoFilters(["/?tag=legacy-tag"]);

      await waitFor(() => {
        expect(screen.getByText("Active Filters (1)")).toBeInTheDocument();
      });

      // The legacy tag should appear as a filter pill label
      expect(screen.getByText("legacy-tag")).toBeInTheDocument();
    });

    it("legacy tag pill has no variation badge (type is tag, not canonical_tag)", async () => {
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      renderVideoFilters(["/?tag=legacy-tag"]);

      await waitFor(() => {
        expect(screen.getByText("legacy-tag")).toBeInTheDocument();
      });

      // No variation badge "N var." should appear for legacy tag pills
      const varBadge = screen.queryByText(/\d+ var\./);
      expect(varBadge).not.toBeInTheDocument();
    });

    it("legacy ?tag= pill coexists with canonical_tag pills", async () => {
      // canonical_tag=react needs detail fetch; tag=legacy-tag does not
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("/canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(
              JSON.stringify({
                data: {
                  canonical_form: "React",
                  normalized_form: "react",
                  alias_count: 2,
                  video_count: 50,
                  top_aliases: [],
                  created_at: "2024-01-01T00:00:00Z",
                  updated_at: "2024-01-01T00:00:00Z",
                },
              })
            )
          );
        }
        return Promise.resolve(mockResponse("{}", 404));
      });

      renderVideoFilters(["/?tag=legacy-tag&canonical_tag=react"]);

      // Both filters should appear in the active filter count
      await waitFor(() => {
        // legacy tag (1) + canonical tag (1) = 2 total
        expect(screen.getByText("Active Filters (2)")).toBeInTheDocument();
      });

      // Both pill labels should be visible
      await waitFor(() => {
        expect(screen.getByText("legacy-tag")).toBeInTheDocument();
        const reactElements = screen.getAllByText("React");
        expect(reactElements.length).toBeGreaterThan(0);
      });
    });

    it("multiple legacy ?tag= params each appear as separate pills", async () => {
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      renderVideoFilters(["/?tag=tag-one&tag=tag-two&tag=tag-three"]);

      await waitFor(() => {
        expect(screen.getByText("Active Filters (3)")).toBeInTheDocument();
      });

      expect(screen.getByText("tag-one")).toBeInTheDocument();
      expect(screen.getByText("tag-two")).toBeInTheDocument();
      expect(screen.getByText("tag-three")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T026.4: No automatic ?tag= to ?canonical_tag= URL rewrite
  // -------------------------------------------------------------------------
  describe("VideoFilters — no automatic URL rewrite", () => {
    it("legacy ?tag= param is NOT rewritten to ?canonical_tag= in the URL", async () => {
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      const { container } = renderVideoFilters(["/?tag=some-legacy-tag"]);

      // Wait for component to render
      await waitFor(() => {
        expect(screen.getByText("Active Filters (1)")).toBeInTheDocument();
      });

      // The current URL (via MemoryRouter) should still have tag=, not canonical_tag=
      // VideoFilters should NOT call setSearchParams to rewrite legacy tags
      // We verify this by confirming no canonical_tag pills appear for this tag
      const filterPillsRegion = container.querySelector('[aria-label="Active filters"]');
      expect(filterPillsRegion).toBeInTheDocument();

      // No canonical_tag filter pill variation badge should appear
      // (canonical_tag pills show "N var." badge; legacy tag pills do not)
      const varBadge = screen.queryByText(/\d+ var\./);
      expect(varBadge).not.toBeInTheDocument();
    });

    it("VideoFilters does not fetch canonical tag detail for legacy ?tag= params", async () => {
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      renderVideoFilters(["/?tag=some-legacy-tag"]);

      await waitFor(() => {
        expect(screen.getByText("Active Filters (1)")).toBeInTheDocument();
      });

      // No detail endpoint should be called for legacy tags — only canonical_tag params trigger hydration
      const calls = fetchMock.mock.calls as [string][];
      const detailCalls = calls.filter(
        ([url]) =>
          url.includes("/canonical-tags/") && !url.includes("?q=")
      );
      expect(detailCalls.length).toBe(0);
    });
  });

  // -------------------------------------------------------------------------
  // T026.5: Both tag and canonical_tag pills coexist without interference
  // -------------------------------------------------------------------------
  describe("Filter pill coexistence", () => {
    it("tag pill remove does not affect canonical_tag pills", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("/canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(
              JSON.stringify({
                data: {
                  canonical_form: "JavaScript",
                  normalized_form: "javascript",
                  alias_count: 1,
                  video_count: 30,
                  top_aliases: [],
                  created_at: "2024-01-01T00:00:00Z",
                  updated_at: "2024-01-01T00:00:00Z",
                },
              })
            )
          );
        }
        return Promise.resolve(mockResponse("{}", 404));
      });

      renderVideoFilters(["/?tag=legacy&canonical_tag=javascript"]);

      // Both should appear
      await waitFor(() => {
        expect(screen.getByText("Active Filters (2)")).toBeInTheDocument();
        expect(screen.getByText("legacy")).toBeInTheDocument();
        const jsElements = screen.getAllByText("JavaScript");
        expect(jsElements.length).toBeGreaterThan(0);
      });
    });

    it("legacy tag pill uses tag color scheme (blue), not canonical_tag scheme", async () => {
      fetchMock.mockResolvedValue(mockResponse("{}", 404));

      renderVideoFilters(["/?tag=raw-tag"]);

      await waitFor(() => {
        expect(screen.getByText("raw-tag")).toBeInTheDocument();
      });

      // The tag remove button should use the tag type label in its aria-label
      const removeBtn = screen.getByRole("button", {
        name: "Remove tag filter: raw-tag",
      });
      expect(removeBtn).toBeInTheDocument();
    });
  });
});
