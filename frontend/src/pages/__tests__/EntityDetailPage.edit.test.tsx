/**
 * Tests for the inline entity name/description editor (EntityNameEditor)
 * embedded in EntityDetailPage (Feature 057, T012/T023).
 *
 * EntityNameEditor is not exported separately, so it is exercised by
 * rendering EntityDetailPage with a valid entity (it renders in place of the
 * static name/description header block).
 *
 * Coverage:
 * 1. Read mode: name heading + Edit button rendered
 * 2. Edit mode: labeled Name input + Description textarea, pre-filled
 * 3. Cancel restores read view without calling the mutation
 * 4. Escape key cancels the edit
 * 5. Save sends only the changed field(s) to useUpdateEntity
 * 6. Successful save returns to read view and announces "Saved." via role="status"
 * 7. Pending state disables Save/inputs and announces "Saving…" via role="status"
 * 8. Client-side validation blocks an empty name without calling the mutation
 * 9. 409 collision error: shown inline (role="alert"), editor stays open, input preserved
 * 10. 400 error: shown inline with the server message
 * 11. Keyboard operability: Enter on the focused Edit button opens edit mode
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
  useUpdateEntity: vi.fn(),
}));

// Mock PhoneticVariantsSection / ExclusionPatternsSection to avoid them
// issuing independent useQuery calls, which would conflict with the global
// useQuery mock below.
vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));
vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));

// Mock TanStack Query useQuery so we can control the entity detail fetch.
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos, useUpdateEntity } from "../../hooks/useEntityMentions";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const ENTITY_ID = "entity-uuid-edit-001";

const mockEntity = {
  entity_id: ENTITY_ID,
  canonical_name: "Openai",
  entity_type: "organization",
  description: "An AI lab.",
  status: "active",
  mention_count: 12,
  video_count: 4,
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

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

function makeSuccessQuery(data: typeof mockEntity): ReturnType<typeof useQuery> {
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

/** Builds a minimal-but-typed useUpdateEntity mutation return value. */
function makeUpdateEntityMock(
  mutate: ReturnType<typeof vi.fn>,
  isPending = false
): ReturnType<typeof useUpdateEntity> {
  return {
    mutate,
    mutateAsync: vi.fn(),
    isPending,
    isError: false,
    error: null,
    isSuccess: false,
    isIdle: !isPending,
    status: isPending ? "pending" : "idle",
    data: undefined,
    variables: undefined,
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateEntity>;
}

function renderPage(entityId = ENTITY_ID) {
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
  vi.mocked(useQuery).mockReturnValue(makeSuccessQuery(mockEntity));
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
  vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(vi.fn()));
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityNameEditor (inside EntityDetailPage)", () => {
  describe("Test 1 — Read mode", () => {
    it("renders the entity name as a heading", () => {
      renderPage();
      expect(
        screen.getByRole("heading", { name: "Openai", level: 1 })
      ).toBeInTheDocument();
    });

    it("renders a keyboard-operable Edit button labelled with the entity name", () => {
      renderPage();
      const button = screen.getByRole("button", {
        name: /edit name and description for openai/i,
      });
      expect(button).toBeInTheDocument();
      expect(button.tagName).toBe("BUTTON");
    });

    it("renders the existing description text", () => {
      renderPage();
      expect(screen.getByText("An AI lab.")).toBeInTheDocument();
    });
  });

  describe("Test 2 — Entering edit mode", () => {
    it("shows a labeled Name input pre-filled with the canonical name", async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );

      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      expect(nameInput).toHaveValue("Openai");
    });

    it("shows a labeled Description textarea pre-filled with the current description", async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );

      const descInput = screen.getByRole("textbox", { name: /^description$/i });
      expect(descInput).toHaveValue("An AI lab.");
    });

    it("shows Save and Cancel buttons", async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );

      expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
    });
  });

  describe("Test 3 — Cancel", () => {
    it("restores the read view without calling the mutation", async () => {
      const mockMutate = vi.fn();
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.type(nameInput, "OpenAI");

      await user.click(screen.getByRole("button", { name: /^cancel$/i }));

      expect(
        screen.getByRole("heading", { name: "Openai", level: 1 })
      ).toBeInTheDocument();
      expect(mockMutate).not.toHaveBeenCalled();
    });
  });

  describe("Test 4 — Escape cancels", () => {
    it("Escape key restores the read view", async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      expect(screen.getByRole("textbox", { name: /^name$/i })).toBeInTheDocument();

      await user.keyboard("{Escape}");

      expect(
        screen.getByRole("heading", { name: "Openai", level: 1 })
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("textbox", { name: /^name$/i })
      ).not.toBeInTheDocument();
    });
  });

  describe("Test 5 — Save sends only changed fields", () => {
    it("sends only canonical_name when only the name changed", async () => {
      const mockMutate = vi.fn();
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.type(nameInput, "OpenAI");

      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(mockMutate).toHaveBeenCalledWith(
        { entityId: ENTITY_ID, data: { canonical_name: "OpenAI" } },
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        })
      );
    });

    it("sends only description when only the description changed", async () => {
      const mockMutate = vi.fn();
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const descInput = screen.getByRole("textbox", { name: /^description$/i });
      await user.clear(descInput);
      await user.type(descInput, "A leading AI research lab.");

      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(mockMutate).toHaveBeenCalledWith(
        {
          entityId: ENTITY_ID,
          data: { description: "A leading AI research lab." },
        },
        expect.any(Object)
      );
    });

    it("does not call the mutation and simply closes when nothing changed", async () => {
      const mockMutate = vi.fn();
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(mockMutate).not.toHaveBeenCalled();
      expect(
        screen.getByRole("heading", { name: "Openai", level: 1 })
      ).toBeInTheDocument();
    });
  });

  describe("Test 6 — Successful save", () => {
    it("returns to read view and announces success via role='status'", async () => {
      const mockMutate = vi.fn((_vars, callbacks) => {
        callbacks.onSuccess();
      });
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.type(nameInput, "OpenAI");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => {
        expect(
          screen.queryByRole("textbox", { name: /^name$/i })
        ).not.toBeInTheDocument();
      });

      const status = screen.getByRole("status");
      expect(status).toHaveAttribute("aria-live", "polite");
      expect(status).toHaveTextContent(/saved/i);
    });
  });

  describe("Test 7 — Pending state", () => {
    it("disables Save and the inputs, and announces 'Saving…' via role='status'", async () => {
      vi.mocked(useUpdateEntity).mockReturnValue(
        makeUpdateEntityMock(vi.fn(), true)
      );

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );

      const saveButton = screen.getByRole("button", { name: /saving/i });
      expect(saveButton).toBeDisabled();
      expect(saveButton).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("textbox", { name: /^name$/i })).toBeDisabled();
      expect(screen.getByRole("textbox", { name: /^description$/i })).toBeDisabled();

      const status = screen.getByRole("status");
      expect(status).toHaveAttribute("aria-live", "polite");
      expect(status).toHaveTextContent(/saving/i);
    });
  });

  describe("Test 8 — Client-side validation", () => {
    it("blocks an empty name without calling the mutation", async () => {
      const mockMutate = vi.fn();
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(mockMutate).not.toHaveBeenCalled();
      expect(screen.getByRole("alert")).toHaveTextContent(/cannot be empty/i);
      // Editor stays open.
      expect(screen.getByRole("textbox", { name: /^name$/i })).toBeInTheDocument();
    });
  });

  describe("Test 9 — 409 collision error", () => {
    it("shows an inline alert, keeps the editor open, and preserves the typed name", async () => {
      const mockMutate = vi.fn((_vars, callbacks) => {
        callbacks.onError({ type: "server", message: "Conflict", status: 409 });
      });
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.type(nameInput, "Duplicate Name");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      expect(screen.getByRole("alert")).toHaveTextContent(
        /already has that name/i
      );
      // Editor remains open with the user's input preserved (FR-022).
      expect(screen.getByRole("textbox", { name: /^name$/i })).toHaveValue(
        "Duplicate Name"
      );
    });
  });

  describe("Test 10 — 400 validation error from server", () => {
    it("shows the server-provided message inline", async () => {
      const mockMutate = vi.fn((_vars, callbacks) => {
        callbacks.onError({
          type: "server",
          message: "Name must not normalize to an empty value.",
          status: 400,
        });
      });
      vi.mocked(useUpdateEntity).mockReturnValue(makeUpdateEntityMock(mockMutate));

      const user = userEvent.setup();
      renderPage();

      await user.click(
        screen.getByRole("button", { name: /edit name and description/i })
      );
      const nameInput = screen.getByRole("textbox", { name: /^name$/i });
      await user.clear(nameInput);
      await user.type(nameInput, "***");
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Name must not normalize to an empty value.")
        ).toBeInTheDocument();
      });
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  describe("Test 11 — Keyboard operability", () => {
    it("Enter on the focused Edit button opens edit mode", async () => {
      const user = userEvent.setup();
      renderPage();

      const editButton = screen.getByRole("button", {
        name: /edit name and description/i,
      });
      editButton.focus();
      await user.keyboard("{Enter}");

      expect(screen.getByRole("textbox", { name: /^name$/i })).toBeInTheDocument();
    });
  });
});
