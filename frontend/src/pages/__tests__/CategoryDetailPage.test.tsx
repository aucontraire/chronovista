/**
 * Tests for CategoryDetailPage (Feature 086).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { CategoryDetailPage } from "../CategoryDetailPage";

const detailMock = vi.fn();
const membersMock = vi.fn();

vi.mock("../../hooks/useCategoryDetail", () => ({
  useCategoryDetail: (...args: unknown[]) => detailMock(...args),
}));
vi.mock("../../hooks/useCategoryEntities", () => ({
  useCategoryEntities: (...args: unknown[]) => membersMock(...args),
}));

function detailState(overrides: Record<string, unknown> = {}) {
  return {
    category: {
      id: "cat-1",
      name: "Category A",
      global_size: 40,
      is_broad: false,
      member_count: 2,
      wikipedia_url: "https://wiki.example/Category:Category_A",
    },
    isLoading: false,
    isError: false,
    isNotFound: false,
    error: null,
    retry: vi.fn(),
    ...overrides,
  };
}

function membersState(overrides: Record<string, unknown> = {}) {
  return {
    entities: [
      { entity_id: "e-1", entity_type: "person", canonical_name: "Entity Alpha" },
      { entity_id: "e-2", entity_type: "organization", canonical_name: "Entity Beta" },
    ],
    total: 2,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    retry: vi.fn(),
    loadMoreRef: { current: null },
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/wikipedia-categories/cat-1"]}>
      <Routes>
        <Route
          path="wikipedia-categories/:categoryId"
          element={<CategoryDetailPage />}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("CategoryDetailPage (Feature 086)", () => {
  beforeEach(() => {
    detailMock.mockReset();
    membersMock.mockReset();
    detailMock.mockReturnValue(detailState());
    membersMock.mockReturnValue(membersState());
  });

  it("passes the route id to both hooks", () => {
    renderPage();
    expect(detailMock).toHaveBeenCalledWith("cat-1");
    expect(membersMock).toHaveBeenCalledWith("cat-1");
  });

  it("shows the header with name and active member count", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { level: 1, name: "Category A" })
    ).toBeInTheDocument();
    expect(screen.getByTestId("category-count")).toHaveTextContent(
      "2 entities in your library"
    );
    expect(screen.queryByTestId("category-broad-note")).not.toBeInTheDocument();
  });

  it("links out to the Wikipedia category page in a new tab", () => {
    renderPage();
    const link = screen.getByRole("link", {
      name: "View this category on Wikipedia (opens in a new tab)",
    });
    expect(link).toHaveAttribute(
      "href",
      "https://wiki.example/Category:Category_A"
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("singularises a member count of one", () => {
    detailMock.mockReturnValue(
      detailState({
        category: {
          id: "cat-1",
          name: "Category A",
          global_size: null,
          is_broad: false,
          member_count: 1,
          wikipedia_url: "https://wiki.example/Category:Category_A",
        },
      })
    );
    renderPage();
    expect(screen.getByTestId("category-count")).toHaveTextContent("1 entity");
  });

  it("shows the broad-grouping note only when is_broad", () => {
    detailMock.mockReturnValue(
      detailState({
        category: {
          id: "cat-1",
          name: "Category A",
          global_size: 9000,
          is_broad: true,
          member_count: 2,
          wikipedia_url: "https://wiki.example/Category:Category_A",
        },
      })
    );
    renderPage();
    expect(screen.getByTestId("category-broad-note")).toHaveTextContent(
      /broad grouping/i
    );
  });

  it("frames membership as fact, not a hedged signal", () => {
    const { container } = renderPage();
    expect(
      screen.getByRole("heading", { name: "Entities in this category" })
    ).toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/related|maybe|might|signal/i);
  });

  it("links each member to its entity page", () => {
    renderPage();
    expect(screen.getByRole("link", { name: /Entity Alpha/ })).toHaveAttribute(
      "href",
      "/entities/e-1"
    );
    expect(screen.getByRole("link", { name: /Entity Beta/ })).toHaveAttribute(
      "href",
      "/entities/e-2"
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("exposes a skip link and a focusable main landmark", () => {
    renderPage();
    expect(
      screen.getByRole("link", { name: "Skip to content" })
    ).toHaveAttribute("href", "#category-main-content");
    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  describe("states", () => {
    it("shows a loading status while the category loads", () => {
      detailMock.mockReturnValue(detailState({ category: undefined, isLoading: true }));
      renderPage();
      expect(screen.getByRole("status", { name: "Loading entities" })).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("shows a not-found state on 404, distinct from an error", () => {
      detailMock.mockReturnValue(
        detailState({
          category: undefined,
          isError: true,
          isNotFound: true,
          error: { type: "unknown", message: "Not found", status: 404 },
        })
      );
      renderPage();
      expect(screen.getByTestId("category-not-found")).toHaveTextContent(
        "Category not found"
      );
      expect(screen.queryByText("Could not load category")).not.toBeInTheDocument();
    });

    it("shows a retryable error when the category fails for another reason", () => {
      const retry = vi.fn();
      detailMock.mockReturnValue(
        detailState({
          category: undefined,
          isError: true,
          error: { type: "server", message: "boom", status: 500 },
          retry,
        })
      );
      renderPage();
      expect(screen.getByText("Could not load category")).toBeInTheDocument();
      expect(screen.queryByTestId("category-not-found")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /try again/i }));
      expect(retry).toHaveBeenCalled();
    });

    it("shows a loading status while members load, keeping the header", () => {
      membersMock.mockReturnValue(membersState({ entities: [], isLoading: true }));
      renderPage();
      expect(screen.getByRole("heading", { level: 1, name: "Category A" })).toBeInTheDocument();
      expect(screen.getByRole("status", { name: "Loading entities" })).toBeInTheDocument();
      expect(screen.queryByTestId("category-empty")).not.toBeInTheDocument();
    });

    it("shows a non-blocking, recoverable members error with the header intact", () => {
      const retry = vi.fn();
      membersMock.mockReturnValue(
        membersState({ entities: [], isError: true, retry })
      );
      renderPage();
      expect(screen.getByRole("heading", { level: 1, name: "Category A" })).toBeInTheDocument();
      expect(screen.getByTestId("category-members-error")).toBeInTheDocument();
      expect(screen.queryByTestId("category-empty")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(retry).toHaveBeenCalled();
    });

    it("shows an empty state, not an error, when there are no members", () => {
      membersMock.mockReturnValue(membersState({ entities: [], total: 0 }));
      renderPage();
      expect(screen.getByTestId("category-empty")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByTestId("category-all-loaded")).not.toBeInTheDocument();
    });
  });

  describe("incremental loading", () => {
    it("renders the sentinel and no all-loaded message while more remain", () => {
      membersMock.mockReturnValue(membersState({ hasNextPage: true }));
      const { container } = renderPage();
      expect(container.querySelector('div[aria-hidden="true"].h-4')).not.toBeNull();
      expect(screen.queryByTestId("category-all-loaded")).not.toBeInTheDocument();
    });

    it("announces fetching the next page", () => {
      membersMock.mockReturnValue(
        membersState({ hasNextPage: true, isFetchingNextPage: true })
      );
      renderPage();
      expect(screen.getByText("Loading more entities...")).toBeInTheDocument();
    });

    it("shows an all-loaded message once the last page is in", () => {
      renderPage();
      expect(screen.getByTestId("category-all-loaded")).toHaveTextContent(
        "All 2 entities loaded"
      );
    });
  });
});
