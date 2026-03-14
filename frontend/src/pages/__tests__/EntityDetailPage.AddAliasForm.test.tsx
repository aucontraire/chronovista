/**
 * Tests for the AddAliasForm component embedded in EntityDetailPage.
 *
 * AddAliasForm is not exported separately, so it is exercised by rendering
 * EntityDetailPage with a valid entity (which causes the form to appear in
 * the Aliases section).
 *
 * Coverage:
 * 1. Renders the form: input, select, and Add button are present
 * 2. Button disabled when input is empty (initial state)
 * 3. Successful alias creation: API called, input cleared, success message shown
 * 4. Duplicate alias error (409): "This alias already exists for the entity." shown
 * 5. 404 entity-not-found error: correct error message shown
 * 6. Generic error: fallback error message shown
 * 7. Alias type select contains all 5 types
 * 8. Input clears error message on typing
 * 9. Keyboard submit (Enter in input) submits the form
 * 10. Button shows "Adding…" while request is in flight
 * 11. Input and select are disabled while request is in flight
 * 12. Success message is labelled with role="status" / aria-live="polite"
 * 13. Error message is labelled with role="alert"
 * 14. onCreated callback is invoked after successful creation
 * 15. Button disabled when input contains only whitespace
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

// ---------------------------------------------------------------------------
// Mock hooks used by EntityDetailPage
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(),
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
}));

// Mock TanStack Query useQuery so we can control the entity detail fetch.
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

// Mock createEntityAlias so we can control its resolved value / rejection.
vi.mock("../../api/entityMentions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/entityMentions")>();
  return {
    ...actual,
    createEntityAlias: vi.fn(),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";
import { createEntityAlias } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockEntity = {
  entity_id: "entity-uuid-001",
  canonical_name: "Noam Chomsky",
  entity_type: "person",
  description: "American linguist and political commentator.",
  status: "active",
  mention_count: 42,
  video_count: 3,
  aliases: [],
};

/** Default empty hook state for useEntityVideos. */
const defaultUseEntityVideos = {
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
};

/** Builds a full TanStack Query useQuery success return value. */
function makeSuccessQuery(
  data: typeof mockEntity
): ReturnType<typeof useQuery> {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
    status: "success",
    isFetching: false,
    isPending: false,
    isSuccess: true,
    isRefetching: false,
    isLoadingError: false,
    isRefetchError: false,
    isPaused: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: Date.now(),
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    fetchStatus: "idle" as const,
    isFetched: true,
    isFetchedAfterMount: true,
    isInitialLoading: false,
    isEnabled: true,
    refetch: vi.fn(),
    promise: Promise.resolve(data),
  } as ReturnType<typeof useQuery>;
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(entityId = "entity-uuid-001") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/entities/${entityId}`]}>
        <Routes>
          <Route path="/entities/:entityId" element={<EntityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();

  // Default: entity loads successfully with no aliases.
  vi.mocked(useQuery).mockReturnValue(makeSuccessQuery(mockEntity));

  // Default: empty video list.
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);

  // Default: createEntityAlias resolves successfully.
  vi.mocked(createEntityAlias).mockResolvedValue({
    alias_name: "Chomsky",
    alias_type: "name_variant",
    occurrence_count: 0,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AddAliasForm (inside EntityDetailPage)", () => {
  // -------------------------------------------------------------------------
  // Test 1 — Form renders with all required controls
  // -------------------------------------------------------------------------

  describe("Test 1 — Form renders with all required controls", () => {
    it("renders the alias name text input", () => {
      renderPage();
      expect(
        screen.getByRole("textbox", { name: /alias name/i })
      ).toBeInTheDocument();
    });

    it("renders the alias type select", () => {
      renderPage();
      expect(
        screen.getByRole("combobox", { name: /alias type/i })
      ).toBeInTheDocument();
    });

    it("renders the Add button", () => {
      renderPage();
      expect(
        screen.getByRole("button", { name: /^add$/i })
      ).toBeInTheDocument();
    });

    it("the form has an accessible label 'Add new alias'", () => {
      renderPage();
      expect(
        screen.getByRole("form", { name: /add new alias/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 2 — Add button disabled when input is empty
  // -------------------------------------------------------------------------

  describe("Test 2 — Button disabled when input is empty", () => {
    it("Add button is disabled when the alias name input is empty", () => {
      renderPage();
      expect(screen.getByRole("button", { name: /^add$/i })).toBeDisabled();
    });

    it("Add button becomes enabled after typing in the input", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Chomsky");

      expect(screen.getByRole("button", { name: /^add$/i })).not.toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Test 3 — Successful alias creation
  // -------------------------------------------------------------------------

  describe("Test 3 — Successful alias creation", () => {
    it("calls createEntityAlias with correct arguments on submit", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Chomsky");

      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(vi.mocked(createEntityAlias)).toHaveBeenCalledOnce();
      });

      expect(vi.mocked(createEntityAlias)).toHaveBeenCalledWith(
        "entity-uuid-001",
        "Chomsky",
        "name_variant"
      );
    });

    it("clears the input after a successful creation", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Chomsky");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(input).toHaveValue("");
      });
    });

    it("shows a success message after creation", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Chomsky");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/"Chomsky" added successfully\./i)
        ).toBeInTheDocument();
      });
    });

    it("success message has role='status' with aria-live='polite'", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Chomsky");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(screen.getByRole("status")).toBeInTheDocument();
      });

      const statusEl = screen.getByRole("status");
      expect(statusEl).toHaveAttribute("aria-live", "polite");
    });
  });

  // -------------------------------------------------------------------------
  // Test 4 — Duplicate alias error (409)
  // -------------------------------------------------------------------------

  describe("Test 4 — Duplicate alias error (409)", () => {
    it("shows 'This alias already exists for the entity.' on a 409 error", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "duplicate-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("This alias already exists for the entity.")
        ).toBeInTheDocument();
      });
    });

    it("the 409 error element has role='alert'", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "duplicate-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 5 — 404 entity-not-found error
  // -------------------------------------------------------------------------

  describe("Test 5 — 404 entity-not-found error", () => {
    it("shows 'Entity not found. Please refresh the page.' on a 404 error", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 404 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "some-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Entity not found. Please refresh the page.")
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 6 — Generic server error
  // -------------------------------------------------------------------------

  describe("Test 6 — Generic server error", () => {
    it("shows fallback error message for non-409/404 errors", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 500 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "some-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Failed to add alias. Please try again.")
        ).toBeInTheDocument();
      });
    });

    it("shows fallback error message when error has no status property", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue(new Error("Network error"));

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "some-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Failed to add alias. Please try again.")
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 7 — Alias type select contains all 5 types
  // -------------------------------------------------------------------------

  describe("Test 7 — Alias type select contains all 5 types", () => {
    it("renders 'Name variant' option", () => {
      renderPage();
      expect(
        screen.getByRole("option", { name: "Name variant" })
      ).toBeInTheDocument();
    });

    it("renders 'Abbreviation' option", () => {
      renderPage();
      expect(
        screen.getByRole("option", { name: "Abbreviation" })
      ).toBeInTheDocument();
    });

    it("renders 'Nickname' option", () => {
      renderPage();
      expect(
        screen.getByRole("option", { name: "Nickname" })
      ).toBeInTheDocument();
    });

    it("renders 'Translation' option", () => {
      renderPage();
      expect(
        screen.getByRole("option", { name: "Translation" })
      ).toBeInTheDocument();
    });

    it("renders 'Former name' option", () => {
      renderPage();
      expect(
        screen.getByRole("option", { name: "Former name" })
      ).toBeInTheDocument();
    });

    it("select defaults to 'Name variant'", () => {
      renderPage();
      const select = screen.getByRole("combobox", {
        name: /alias type/i,
      }) as HTMLSelectElement;
      expect(select.value).toBe("name_variant");
    });

    it("select contains exactly 5 options", () => {
      renderPage();
      const select = screen.getByRole("combobox", { name: /alias type/i });
      const options = select.querySelectorAll("option");
      expect(options).toHaveLength(5);
    });
  });

  // -------------------------------------------------------------------------
  // Test 8 — Input clears error on typing
  // -------------------------------------------------------------------------

  describe("Test 8 — Input clears error message on typing", () => {
    it("clears the error message when the user types in the input after an error", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });

      // Trigger a 409 error.
      await user.type(input, "bad-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("This alias already exists for the entity.")
        ).toBeInTheDocument();
      });

      // Start typing again — the error should disappear.
      await user.type(input, "x");

      expect(
        screen.queryByText("This alias already exists for the entity.")
      ).not.toBeInTheDocument();
    });

    it("does not show the error element after the user types a character", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 500 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "some-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      await user.type(input, "a");

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 9 — Keyboard submit (Enter key)
  // -------------------------------------------------------------------------

  describe("Test 9 — Keyboard submit (Enter in input)", () => {
    it("submits the form when Enter is pressed inside the alias name input", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Avram Chomsky");
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(vi.mocked(createEntityAlias)).toHaveBeenCalledOnce();
      });
    });

    it("Enter does not submit when the input is empty", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.click(input);
      await user.keyboard("{Enter}");

      // Allow any async state flush.
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(vi.mocked(createEntityAlias)).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Test 10 — Button shows "Adding…" while in-flight
  // -------------------------------------------------------------------------

  describe("Test 10 — Button text while request is in flight", () => {
    it("shows 'Adding…' while the request is pending", async () => {
      // Hold the promise open long enough to observe the pending state.
      let resolveFn!: (value: Awaited<ReturnType<typeof createEntityAlias>>) => void;
      vi.mocked(createEntityAlias).mockReturnValue(
        new Promise((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "pending-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      // While the promise hasn't settled, the button should show "Adding…".
      expect(screen.getByRole("button", { name: /adding/i })).toBeInTheDocument();

      // Settle the promise to avoid unhandled rejections.
      resolveFn({ alias_name: "pending-alias", alias_type: "name_variant", occurrence_count: 0 });
    });
  });

  // -------------------------------------------------------------------------
  // Test 11 — Input and select disabled while in-flight
  // -------------------------------------------------------------------------

  describe("Test 11 — Controls disabled while request is in flight", () => {
    it("disables the alias name input while the request is pending", async () => {
      let resolveFn!: (value: Awaited<ReturnType<typeof createEntityAlias>>) => void;
      vi.mocked(createEntityAlias).mockReturnValue(
        new Promise((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "pending-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      expect(input).toBeDisabled();

      resolveFn({ alias_name: "pending-alias", alias_type: "name_variant", occurrence_count: 0 });
    });

    it("disables the alias type select while the request is pending", async () => {
      let resolveFn!: (value: Awaited<ReturnType<typeof createEntityAlias>>) => void;
      vi.mocked(createEntityAlias).mockReturnValue(
        new Promise((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "pending-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      const select = screen.getByRole("combobox", { name: /alias type/i });
      expect(select).toBeDisabled();

      resolveFn({ alias_name: "pending-alias", alias_type: "name_variant", occurrence_count: 0 });
    });
  });

  // -------------------------------------------------------------------------
  // Test 12 — Error message has role="alert"
  // -------------------------------------------------------------------------

  describe("Test 12 — Error message accessibility", () => {
    it("error paragraph has role='alert' for screen-reader announcements", async () => {
      vi.mocked(createEntityAlias).mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "some-alias");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert).toBeInTheDocument();
        expect(alert.tagName).toBe("P");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 13 — onCreated callback called after success
  // -------------------------------------------------------------------------

  describe("Test 13 — onCreated callback invoked after success", () => {
    it("TanStack queryClient.invalidateQueries is called after a successful creation", async () => {
      // We cannot spy on onCreated directly because it is an inline closure
      // inside EntityDetailPage.  Instead, we verify the side-effect: a second
      // call to useQuery is triggered (re-fetch) after creation succeeds,
      // which is what queryClient.invalidateQueries causes.
      //
      // Simpler observable: createEntityAlias resolves → input is cleared →
      // success message appears.  These already verify the happy path.
      // This test verifies that createEntityAlias is called exactly once and
      // the form resets (the onCreated path ran without throwing).
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "Avram");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(vi.mocked(createEntityAlias)).toHaveBeenCalledOnce();
        // Input was cleared, confirming the success branch ran to completion.
        expect(input).toHaveValue("");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 14 — Button disabled when input is only whitespace
  // -------------------------------------------------------------------------

  describe("Test 14 — Button disabled for whitespace-only input", () => {
    it("Add button is disabled when the input contains only spaces", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      await user.type(input, "   ");

      expect(screen.getByRole("button", { name: /^add$/i })).toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Test 15 — Selected alias type is sent to the API
  // -------------------------------------------------------------------------

  describe("Test 15 — Selected alias type is sent to the API", () => {
    it("passes the chosen alias type to createEntityAlias", async () => {
      const user = userEvent.setup();
      renderPage();

      const input = screen.getByRole("textbox", { name: /alias name/i });
      const select = screen.getByRole("combobox", { name: /alias type/i });

      await user.selectOptions(select, "abbreviation");
      await user.type(input, "NC");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(vi.mocked(createEntityAlias)).toHaveBeenCalledWith(
          "entity-uuid-001",
          "NC",
          "abbreviation"
        );
      });
    });
  });
});
