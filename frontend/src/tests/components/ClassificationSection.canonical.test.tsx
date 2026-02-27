/**
 * Tests for ClassificationSection canonical tag display.
 *
 * Verifies:
 * - T021: Tags grouped by canonical form with single badge per group
 * - R7: "Also:" alias line excludes canonical_form from aliases
 * - FR-012: alias_count=1 hides "Also:" line
 * - FR-013: Orphaned tags rendered in "Unresolved Tags" subsection
 * - FR-024: aria-label format for canonical badge
 * - NFR-007: Mobile layout flex-wrap gap-2 min-h-[44px]
 * - AS-6: Skeleton loading during resolution
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import { ClassificationSection } from "../../components/ClassificationSection";
import type { CanonicalTagListItem, CanonicalTagDetail } from "../../types/canonical-tags";

// ---------------------------------------------------------------------------
// Helpers: mock fetch responses
// ---------------------------------------------------------------------------

function makeListResponse(items: CanonicalTagListItem[]) {
  return JSON.stringify({
    data: items,
    pagination: { total: items.length, limit: 1, offset: 0, has_more: false },
  });
}

function makeDetailResponse(detail: CanonicalTagDetail) {
  return JSON.stringify({ data: detail });
}

function buildListItem(
  canonicalForm: string,
  normalizedForm: string,
  aliasCount: number,
  videoCount = 10
): CanonicalTagListItem {
  return { canonical_form: canonicalForm, normalized_form: normalizedForm, alias_count: aliasCount, video_count: videoCount };
}

function buildDetail(
  canonicalForm: string,
  normalizedForm: string,
  aliasCount: number,
  topAliases: Array<{ raw_form: string; occurrence_count: number }>
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

/** Build a mock Response object */
function mockResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderComponent(
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

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("ClassificationSection — canonical tag display", () => {
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
  // Zero-tag state (T025)
  // -------------------------------------------------------------------------
  describe("Zero-tag state (T025)", () => {
    it('shows "None" in muted style when tags array is empty', () => {
      renderComponent([]);

      const tagsHeading = screen.getByRole("heading", { name: "Tags" });
      const subsection = tagsHeading.closest("div")!;
      expect(within(subsection).getByText("None")).toBeInTheDocument();
    });

    it("makes no fetch calls when tags is empty", () => {
      renderComponent([]);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not render Unresolved Tags subsection when no tags", () => {
      renderComponent([]);
      expect(
        screen.queryByRole("heading", { name: "Unresolved Tags" })
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Skeleton loading (AS-6)
  // -------------------------------------------------------------------------
  describe("Skeleton loading during resolution (AS-6)", () => {
    it("renders skeleton placeholders while tags are loading", () => {
      // fetch never resolves — stays in loading state
      fetchMock.mockReturnValue(new Promise(() => {}));

      const { container } = renderComponent(["JavaScript", "React", "TypeScript"]);

      const skeletons = container.querySelectorAll('[data-testid="tag-skeleton"]');
      expect(skeletons.length).toBeGreaterThan(0);
      expect(skeletons.length).toBeLessThanOrEqual(10);
    });

    it("caps skeleton count at 10 for large tag arrays", () => {
      fetchMock.mockReturnValue(new Promise(() => {}));

      const manyTags = Array.from({ length: 15 }, (_, i) => `tag-${i}`);
      const { container } = renderComponent(manyTags);

      const skeletons = container.querySelectorAll('[data-testid="tag-skeleton"]');
      expect(skeletons.length).toBeLessThanOrEqual(10);
    });
  });

  // -------------------------------------------------------------------------
  // Canonical tag grouping (T022, T023)
  // -------------------------------------------------------------------------
  describe("Canonical tag groups (T022, T023)", () => {
    it("renders a single badge for a resolved tag", async () => {
      // Resolve "JavaScript" → canonical "JavaScript"
      // Also mock detail fetch (useCanonicalTagDetail) → no detail needed
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=JavaScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([
                buildListItem("JavaScript", "javascript", 3, 25),
              ])
            )
          );
        }
        if (url.includes("canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("JavaScript", "javascript", 3, [
                  { raw_form: "JavaScript", occurrence_count: 20 },
                  { raw_form: "js", occurrence_count: 5 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["JavaScript"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: JavaScript/,
          })
        ).toBeInTheDocument();
      });
    });

    it("groups multiple raw tags that map to the same canonical form", async () => {
      // Both "JavaScript" and "javascript" → same canonical "JavaScript"
      fetchMock.mockImplementation((url: string) => {
        if (
          url.includes("canonical-tags?q=JavaScript") ||
          url.includes("canonical-tags?q=javascript")
        ) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([
                buildListItem("JavaScript", "javascript", 3, 25),
              ])
            )
          );
        }
        if (url.includes("canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("JavaScript", "javascript", 3, [
                  { raw_form: "JavaScript", occurrence_count: 20 },
                  { raw_form: "js", occurrence_count: 5 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["JavaScript", "javascript"]);

      await waitFor(() => {
        const badges = screen.getAllByRole("link", {
          name: /Filter videos by canonical tag: JavaScript/,
        });
        // Should only show ONE badge for the canonical group
        expect(badges).toHaveLength(1);
      });
    });
  });

  // -------------------------------------------------------------------------
  // Alias display per R7 and FR-012
  // -------------------------------------------------------------------------
  describe("Alias display (R7, FR-012)", () => {
    it("renders 'Also:' line with aliases excluding canonical_form itself (R7)", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=JavaScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("JavaScript", "javascript", 3, 25)])
            )
          );
        }
        if (url.includes("canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("JavaScript", "javascript", 3, [
                  { raw_form: "JavaScript", occurrence_count: 20 },
                  { raw_form: "js", occurrence_count: 10 },
                  { raw_form: "JS", occurrence_count: 5 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["JavaScript"]);

      await waitFor(() => {
        const alsoP = screen.getByText(/Also:/);
        // canonical_form "JavaScript" should NOT be in alias list
        expect(alsoP.closest("p")?.textContent).not.toMatch(/JavaScript,/);
        // but "js" or "JS" should appear
        expect(alsoP.closest("p")?.textContent).toContain("js");
      });
    });

    it("hides 'Also:' line when alias_count is 1 (FR-012)", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=SomeTag")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("SomeTag", "sometag", 1, 5)])
            )
          );
        }
        if (url.includes("canonical-tags/sometag")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("SomeTag", "sometag", 1, [
                  { raw_form: "SomeTag", occurrence_count: 5 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["SomeTag"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: SomeTag/,
          })
        ).toBeInTheDocument();
      });

      expect(screen.queryByText(/Also:/)).not.toBeInTheDocument();
    });

    it("hides 'Also:' line when all aliases equal canonical_form (R7)", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=React")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("React", "react", 2, 15)])
            )
          );
        }
        if (url.includes("canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("React", "react", 2, [
                  // Only alias IS the canonical_form itself — filtered out by R7
                  { raw_form: "React", occurrence_count: 15 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["React"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: React/,
          })
        ).toBeInTheDocument();
      });

      expect(screen.queryByText(/Also:/)).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // aria-label per FR-024
  // -------------------------------------------------------------------------
  describe("Badge aria-label (FR-024)", () => {
    it("includes alias_count - 1 variations in aria-label", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=JavaScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("JavaScript", "javascript", 4, 100)])
            )
          );
        }
        if (url.includes("canonical-tags/javascript")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("JavaScript", "javascript", 4, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["JavaScript"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: JavaScript/,
        });
        expect(badge.getAttribute("aria-label")).toContain("3 variations");
      });
    });

    it("omits variation clause when alias_count is 1", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=Solo")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("Solo", "solo", 1, 5)])
            )
          );
        }
        if (url.includes("canonical-tags/solo")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("Solo", "solo", 1, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["Solo"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: Solo/,
        });
        expect(badge.getAttribute("aria-label")).not.toContain("variation");
      });
    });

    it("includes video_count in aria-label", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=Python")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("Python", "python", 2, 42)])
            )
          );
        }
        if (url.includes("canonical-tags/python")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("Python", "python", 2, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["Python"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: Python/,
        });
        expect(badge.getAttribute("aria-label")).toContain("42 videos");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Badge navigation
  // -------------------------------------------------------------------------
  describe("Badge click navigation", () => {
    it("badge links to /?canonical_tag={normalizedForm}", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=React")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("React", "react", 2, 20)])
            )
          );
        }
        if (url.includes("canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("React", "react", 2, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["React"]);

      await waitFor(() => {
        const badge = screen.getByRole("link", {
          name: /Filter videos by canonical tag: React/,
        });
        expect(badge.getAttribute("href")).toContain("canonical_tag=react");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Unresolved tags subsection (T024, FR-013)
  // -------------------------------------------------------------------------
  describe("Unresolved Tags subsection (T024, FR-013)", () => {
    it("renders 'Unresolved Tags' subsection when orphaned tags exist", async () => {
      // Returns empty list → orphaned
      fetchMock.mockResolvedValue(
        mockResponse(makeListResponse([]))
      );

      renderComponent(["orphaned-tag"]);

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Unresolved Tags" })
        ).toBeInTheDocument();
      });
    });

    it("orphaned tag aria-label includes '(unresolved)'", async () => {
      fetchMock.mockResolvedValue(mockResponse(makeListResponse([])));

      renderComponent(["mystery-tag"]);

      await waitFor(() => {
        const orphanLink = screen.getByRole("link", {
          name: /\(unresolved\)/,
        });
        expect(orphanLink).toBeInTheDocument();
        expect(orphanLink.getAttribute("aria-label")).toContain("mystery-tag");
      });
    });

    it("orphaned tag links via ?tag={rawTag}", async () => {
      fetchMock.mockResolvedValue(mockResponse(makeListResponse([])));

      renderComponent(["mystery-tag"]);

      await waitFor(() => {
        const orphanLink = screen.getByRole("link", {
          name: /mystery-tag.*unresolved/,
        });
        expect(orphanLink.getAttribute("href")).toContain("tag=mystery-tag");
      });
    });

    it("uses slate/italic styling for orphaned tags (FR-013)", async () => {
      fetchMock.mockResolvedValue(mockResponse(makeListResponse([])));

      const { container } = renderComponent(["orphaned"]);

      await waitFor(() => {
        const orphanLink = container.querySelector(
          '[aria-label*="(unresolved)"]'
        );
        expect(orphanLink).toBeInTheDocument();
        expect(orphanLink).toHaveClass("italic");
        expect(orphanLink).toHaveStyle({ backgroundColor: "#F1F5F9" });
      });
    });

    it("renders aria-describedby hidden explanation text", async () => {
      fetchMock.mockResolvedValue(mockResponse(makeListResponse([])));

      const { container } = renderComponent(["some-tag"]);

      // First wait for the Unresolved Tags heading to appear
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Unresolved Tags" })
        ).toBeInTheDocument();
      });

      // Then check for the hidden description element
      const hiddenDesc = container.querySelector('[id*="unresolved"]');
      expect(hiddenDesc).toBeInTheDocument();
      expect(hiddenDesc).toHaveClass("sr-only");
      expect(hiddenDesc?.textContent).toContain(
        "These tags have not yet been mapped to a canonical group"
      );
    });

    it("does NOT render Unresolved Tags when all tags are resolved", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=React")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("React", "react", 2, 20)])
            )
          );
        }
        if (url.includes("canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("React", "react", 2, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      renderComponent(["React"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: React/,
          })
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByRole("heading", { name: "Unresolved Tags" })
      ).not.toBeInTheDocument();
    });

    it("shows only Unresolved Tags subsection when all tags are orphaned", async () => {
      fetchMock.mockResolvedValue(mockResponse(makeListResponse([])));

      renderComponent(["a", "b", "c"]);

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Unresolved Tags" })
        ).toBeInTheDocument();
      });

      // No canonical tag badges
      expect(
        screen.queryByRole("link", { name: /Filter videos by canonical tag/ })
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Mobile layout (NFR-007)
  // -------------------------------------------------------------------------
  describe("Mobile layout (NFR-007)", () => {
    it("tag container has flex flex-wrap gap-2 classes", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=React")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("React", "react", 2, 20)])
            )
          );
        }
        if (url.includes("canonical-tags/react")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("React", "react", 2, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      const { container } = renderComponent(["React"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: React/,
          })
        ).toBeInTheDocument();
      });

      const tagsContainer = container.querySelector(".flex.flex-wrap.gap-2");
      expect(tagsContainer).toBeInTheDocument();
    });

    it("canonical badge container has min-h-[44px] for touch target (NFR-007)", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=TypeScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("TypeScript", "typescript", 2, 30)])
            )
          );
        }
        if (url.includes("canonical-tags/typescript")) {
          return Promise.resolve(
            mockResponse(makeDetailResponse(buildDetail("TypeScript", "typescript", 2, [])))
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      const { container } = renderComponent(["TypeScript"]);

      await waitFor(() => {
        expect(
          screen.getByRole("link", {
            name: /Filter videos by canonical tag: TypeScript/,
          })
        ).toBeInTheDocument();
      });

      // The group container div should have min-h-[44px]
      const minHContainer = container.querySelector("[class*='min-h-']");
      expect(minHContainer).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accessibility: Also line (FR-012)
  // -------------------------------------------------------------------------
  describe("Alias line accessibility (FR-012)", () => {
    it("'Also:' span is aria-hidden", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=TypeScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("TypeScript", "typescript", 3, 50)])
            )
          );
        }
        if (url.includes("canonical-tags/typescript")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("TypeScript", "typescript", 3, [
                  { raw_form: "TypeScript", occurrence_count: 40 },
                  { raw_form: "ts", occurrence_count: 10 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      const { container } = renderComponent(["TypeScript"]);

      await waitFor(() => {
        expect(screen.getByText(/Also:/)).toBeInTheDocument();
      });

      const alsoSpan = container.querySelector('[aria-hidden="true"]');
      expect(alsoSpan).toBeInTheDocument();
      expect(alsoSpan?.textContent).toBe("Also: ");
    });

    it("'Also:' paragraph has aria-label with joined aliases", async () => {
      fetchMock.mockImplementation((url: string) => {
        if (url.includes("canonical-tags?q=TypeScript")) {
          return Promise.resolve(
            mockResponse(
              makeListResponse([buildListItem("TypeScript", "typescript", 3, 50)])
            )
          );
        }
        if (url.includes("canonical-tags/typescript")) {
          return Promise.resolve(
            mockResponse(
              makeDetailResponse(
                buildDetail("TypeScript", "typescript", 3, [
                  { raw_form: "TypeScript", occurrence_count: 40 },
                  { raw_form: "ts", occurrence_count: 10 },
                ])
              )
            )
          );
        }
        return Promise.resolve(mockResponse(makeListResponse([]), 200));
      });

      const { container } = renderComponent(["TypeScript"]);

      await waitFor(() => {
        const alsoP = container.querySelector("p[aria-label*='Aliases']");
        expect(alsoP).toBeInTheDocument();
        expect(alsoP?.getAttribute("aria-label")).toContain("ts");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Existing sections preserved (regression)
  // -------------------------------------------------------------------------
  describe("Existing sections preserved (regression)", () => {
    it("Category section still renders", () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ClassificationSection
              tags={[]}
              categoryId="28"
              categoryName="Science & Technology"
              topics={[]}
              playlists={[]}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("Science & Technology")).toBeInTheDocument();
    });

    it("Topics section still renders", () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ClassificationSection
              tags={[]}
              categoryId={null}
              categoryName={null}
              topics={[
                {
                  topic_id: "/m/04rlf",
                  name: "Music",
                  parent_path: "Arts",
                },
              ]}
              playlists={[]}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(
        screen.getByRole("link", { name: /topic: Music/ })
      ).toBeInTheDocument();
    });
  });
});
