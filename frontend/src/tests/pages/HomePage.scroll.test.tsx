/**
 * HomePage — scroll-to-top fires on filter CHANGE, not on every render (FR-031).
 *
 * `searchParams.getAll()` returns a fresh array on every render. Listing those
 * arrays as effect dependencies made the scroll-to-top effect run on every
 * render rather than when a filter changed — and HomePage re-renders whenever
 * the shared videos query gains a page, because its own `useVideos` call (for
 * the filter panel's total) subscribes to the same cache entry that infinite
 * scroll appends to.
 *
 * The user-visible result: scroll down far enough to load another page and the
 * page smoothly yanks itself back to the top. Reproduced at ~118,000px of
 * scroll depth before the fix.
 *
 * These tests pin both halves — it must NOT fire on a bare re-render, and it
 * must STILL fire when a filter actually changes.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HomePage } from "../../pages/HomePage";

vi.mock("../../hooks/useCategories", () => ({
  useCategories: () => ({
    categories: [],
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

vi.mock("../../hooks/useVideos", () => ({
  useVideos: vi.fn(() => ({
    videos: [],
    total: 0,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  })),
}));

function renderWithProviders(
  ui: React.ReactElement,
  { initialEntries = ["/"] } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("HomePage — scroll-to-top trigger (FR-031)", () => {
  let scrollTo: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    scrollTo = vi
      .spyOn(window, "scrollTo")
      .mockImplementation(() => undefined) as unknown as ReturnType<
      typeof vi.spyOn
    >;
  });

  afterEach(() => {
    scrollTo.mockRestore();
  });

  describe("does not fire on a re-render with unchanged filters", () => {
    it("stays put when nothing changed", () => {
      const { rerender } = renderWithProviders(<HomePage />);
      scrollTo.mockClear(); // ignore the mount call

      // A re-render is exactly what an arriving infinite-scroll page causes.
      rerender(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <HomePage />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(scrollTo).not.toHaveBeenCalled();
    });

    it("stays put with array-valued filters active", () => {
      // The array params are the ones whose identity churned: tag,
      // canonical_tag, topic_id, entity_id, exclude_entity_id.
      const url =
        "/?tag=a&canonical_tag=b&topic_id=/m/04rlf&entity_id=11111111-1111-4111-8111-111111111111&exclude_entity_id=22222222-2222-4222-8222-222222222222";
      const { rerender } = renderWithProviders(<HomePage />, {
        initialEntries: [url],
      });
      scrollTo.mockClear();

      rerender(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter initialEntries={[url]}>
            <HomePage />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(scrollTo).not.toHaveBeenCalled();
    });

    it("stays put across several consecutive re-renders", () => {
      // One page arriving is one re-render; a long scroll is many.
      const { rerender } = renderWithProviders(<HomePage />, {
        initialEntries: ["/?tag=news"],
      });
      scrollTo.mockClear();

      for (let i = 0; i < 5; i++) {
        rerender(
          <QueryClientProvider client={new QueryClient()}>
            <MemoryRouter initialEntries={["/?tag=news"]}>
              <HomePage />
            </MemoryRouter>
          </QueryClientProvider>
        );
      }

      expect(scrollTo).not.toHaveBeenCalled();
    });
  });

  describe("still fires when a filter actually changes (FR-031)", () => {
    it("scrolls to top when a filter is toggled", async () => {
      const user = userEvent.setup();
      renderWithProviders(<HomePage />);
      scrollTo.mockClear();

      await user.click(
        screen.getByRole("checkbox", { name: /Show unavailable content/i })
      );

      await waitFor(() => {
        expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
      });
    });
  });
});
