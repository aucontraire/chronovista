/**
 * Tests for HomePage — canonical tag URL param integration (US3/T018).
 *
 * Verifies:
 * - canonical_tag URL params are read via searchParams.getAll('canonical_tag')
 * - canonicalTags array is passed to useVideos
 * - Legacy `tag` URL params continue to be read and passed as `tags`
 * - Multiple canonical_tag params produce a multi-element canonicalTags array
 *
 * @module tests/pages/HomePage.canonical
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { HomePage } from "../../pages/HomePage";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock child hooks so we don't need real API responses
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

vi.mock("../../hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => true,
}));

// useVideos is the key mock — we capture what it was called with
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

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("HomePage — canonical tag URL params (US3/T018)", () => {
  let useVideosMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.clearAllMocks();
    useVideosMock = vi.mocked(
      (await import("../../hooks/useVideos")).useVideos
    );
  });

  // -------------------------------------------------------------------------
  // Reading canonical_tag URL params
  // -------------------------------------------------------------------------

  describe("reading canonical_tag URL params", () => {
    it("passes empty canonicalTags to useVideos when no canonical_tag param is present", () => {
      renderWithProviders(<HomePage />, { initialEntries: ["/"] });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: [],
        })
      );
    });

    it("reads a single canonical_tag param and passes it to useVideos", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=javascript"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["javascript"],
        })
      );
    });

    it("reads multiple canonical_tag params and passes them all to useVideos", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=javascript&canonical_tag=typescript&canonical_tag=react"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["javascript", "typescript", "react"],
        })
      );
    });

    it("handles canonical_tag param with encoded characters", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=c%2B%2B"],
      });

      // URLSearchParams decodes percent-encoded values on read
      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["c++"],
        })
      );
    });
  });

  // -------------------------------------------------------------------------
  // Legacy tag param backward compatibility
  // -------------------------------------------------------------------------

  describe("legacy tag param backward compatibility", () => {
    it("reads legacy tag params and passes them as tags to useVideos", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?tag=music&tag=gaming"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: ["music", "gaming"],
        })
      );
    });

    it("passes both tags and canonicalTags when both are present in URL", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?tag=legacy&canonical_tag=canonical-form"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: ["legacy"],
          canonicalTags: ["canonical-form"],
        })
      );
    });

    it("passes empty tags array when no tag param is in URL", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=music"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: [],
          canonicalTags: ["music"],
        })
      );
    });
  });

  // -------------------------------------------------------------------------
  // Combined filter state
  // -------------------------------------------------------------------------

  describe("combined URL filter state passed to useVideos", () => {
    it("reads all filter params together and passes them correctly", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: [
          "/?canonical_tag=javascript&tag=legacy&category=10&topic_id=%2Fm%2F04rlf",
        ],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["javascript"],
          tags: ["legacy"],
          category: "10",
          topicIds: ["/m/04rlf"],
        })
      );
    });

    it("canonicalTags does not interfere with include_unavailable param", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=music&include_unavailable=true"],
      });

      expect(useVideosMock).toHaveBeenCalledWith(
        expect.objectContaining({
          canonicalTags: ["music"],
          includeUnavailable: true,
        })
      );
    });
  });

  // -------------------------------------------------------------------------
  // Rendering smoke test
  // -------------------------------------------------------------------------

  describe("page rendering with canonical_tag param", () => {
    it("renders the Videos h2 heading regardless of canonical_tag params", () => {
      renderWithProviders(<HomePage />, {
        initialEntries: ["/?canonical_tag=javascript"],
      });

      // Use level: 2 to target the page title h2 specifically
      expect(screen.getByRole("heading", { name: "Videos", level: 2 })).toBeInTheDocument();
    });
  });
});
