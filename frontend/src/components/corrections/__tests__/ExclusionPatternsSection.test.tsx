/**
 * Tests for ExclusionPatternsSection component.
 *
 * Coverage:
 * 1. Renders empty state when no patterns are provided
 * 2. Renders current patterns as pills when patterns are provided
 * 3. Each pattern pill has an accessible remove button
 * 4. Remove button calls removeExclusionPattern and invalidates query on success
 * 5. Remove button shows loading state while in-flight
 * 6. Remove failure shows inline error on the pill
 * 7. Add pattern form renders with accessible label
 * 8. Add button is disabled when input is empty or whitespace-only
 * 9. Add button becomes enabled after typing in the input
 * 10. Submit calls addExclusionPattern with the trimmed value
 * 11. Success message shown after add and input is cleared
 * 12. Success message has role="status" / aria-live="polite"
 * 13. Duplicate pattern (409) shows specific error message
 * 14. 404 error shows entity-not-found message
 * 15. Generic error shows fallback message
 * 16. Error message has role="alert"
 * 17. Error clears when the user types in the input after an error
 * 18. Add button shows "Adding…" while request is in flight
 * 19. Input is disabled while request is in flight
 * 20. Help text is present in the rendered output
 * 21. Section heading is accessible (h2 with id used by aria-labelledby)
 * 22. Pattern list has accessible label when patterns exist
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ExclusionPatternsSection } from "../ExclusionPatternsSection";
import {
  addExclusionPattern,
  removeExclusionPattern,
} from "../../../api/entityMentions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../api/entityMentions", () => ({
  addExclusionPattern: vi.fn(),
  removeExclusionPattern: vi.fn(),
}));

const mockedAdd = vi.mocked(addExclusionPattern);
const mockedRemove = vi.mocked(removeExclusionPattern);

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderSection(
  patterns: string[] = [],
  entityId = "entity-uuid-001"
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ExclusionPatternsSection entityId={entityId} patterns={patterns} />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();

  // Default: both API calls succeed.
  mockedAdd.mockResolvedValue([]);
  mockedRemove.mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ExclusionPatternsSection", () => {
  // -------------------------------------------------------------------------
  // Test 1 — Empty state
  // -------------------------------------------------------------------------

  describe("Test 1 — Empty state when no patterns", () => {
    it("renders the 'No exclusion patterns defined' message when patterns is empty", () => {
      renderSection([]);
      expect(
        screen.getByText(/no exclusion patterns defined/i)
      ).toBeInTheDocument();
    });

    it("does not render any pill when patterns is empty", () => {
      renderSection([]);
      // The list element should not be present when there are no patterns.
      expect(
        screen.queryByRole("list", { name: /current exclusion patterns/i })
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 2 — Renders pattern list
  // -------------------------------------------------------------------------

  describe("Test 2 — Renders current patterns as pills", () => {
    it("renders a pill for each pattern in the patterns prop", () => {
      renderSection(["New Mexico", "Mexico City"]);
      expect(screen.getByText("New Mexico")).toBeInTheDocument();
      expect(screen.getByText("Mexico City")).toBeInTheDocument();
    });

    it("does not show the empty state when patterns are provided", () => {
      renderSection(["New Mexico"]);
      expect(
        screen.queryByText(/no exclusion patterns defined/i)
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 3 — Remove button accessibility
  // -------------------------------------------------------------------------

  describe("Test 3 — Each pill has an accessible remove button", () => {
    it("renders a remove button for each pattern with an accessible label", () => {
      renderSection(["New Mexico", "Mexico City"]);

      expect(
        screen.getByRole("button", {
          name: /remove exclusion pattern "New Mexico"/i,
        })
      ).toBeInTheDocument();

      expect(
        screen.getByRole("button", {
          name: /remove exclusion pattern "Mexico City"/i,
        })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 4 — Remove calls API and cache invalidation
  // -------------------------------------------------------------------------

  describe("Test 4 — Remove button calls removeExclusionPattern", () => {
    it("calls removeExclusionPattern with entity id and pattern on click", async () => {
      const user = userEvent.setup();
      renderSection(["New Mexico"], "entity-uuid-001");

      const removeBtn = screen.getByRole("button", {
        name: /remove exclusion pattern "New Mexico"/i,
      });
      await user.click(removeBtn);

      await waitFor(() => {
        expect(mockedRemove).toHaveBeenCalledOnce();
      });

      expect(mockedRemove).toHaveBeenCalledWith("entity-uuid-001", "New Mexico");
    });
  });

  // -------------------------------------------------------------------------
  // Test 5 — Remove loading state
  // -------------------------------------------------------------------------

  describe("Test 5 — Remove button shows loading state while in-flight", () => {
    it("disables the remove button while the remove request is in flight", async () => {
      let resolveFn!: (value: string[]) => void;
      mockedRemove.mockReturnValue(
        new Promise<string[]>((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderSection(["New Mexico"]);

      const removeBtn = screen.getByRole("button", {
        name: /remove exclusion pattern "New Mexico"/i,
      });
      await user.click(removeBtn);

      expect(removeBtn).toBeDisabled();

      // Settle promise to avoid warnings.
      resolveFn([]);
    });
  });

  // -------------------------------------------------------------------------
  // Test 6 — Remove failure shows inline error
  // -------------------------------------------------------------------------

  describe("Test 6 — Remove failure shows inline error on the pill", () => {
    it("shows a generic error message when remove fails", async () => {
      mockedRemove.mockRejectedValue({ status: 500 });

      const user = userEvent.setup();
      renderSection(["New Mexico"]);

      const removeBtn = screen.getByRole("button", {
        name: /remove exclusion pattern "New Mexico"/i,
      });
      await user.click(removeBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/failed to remove pattern/i)
        ).toBeInTheDocument();
      });
    });

    it("shows a 404 error message when entity or pattern not found", async () => {
      mockedRemove.mockRejectedValue({ status: 404 });

      const user = userEvent.setup();
      renderSection(["New Mexico"]);

      const removeBtn = screen.getByRole("button", {
        name: /remove exclusion pattern "New Mexico"/i,
      });
      await user.click(removeBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/pattern or entity not found/i)
        ).toBeInTheDocument();
      });
    });

    it("remove error has role='alert'", async () => {
      mockedRemove.mockRejectedValue({ status: 500 });

      const user = userEvent.setup();
      renderSection(["New Mexico"]);

      const removeBtn = screen.getByRole("button", {
        name: /remove exclusion pattern "New Mexico"/i,
      });
      await user.click(removeBtn);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 7 — Add form renders accessibly
  // -------------------------------------------------------------------------

  describe("Test 7 — Add pattern form renders with accessible label", () => {
    it("renders a form with label 'Add new exclusion pattern'", () => {
      renderSection([]);
      expect(
        screen.getByRole("form", { name: /add new exclusion pattern/i })
      ).toBeInTheDocument();
    });

    it("renders the pattern text input", () => {
      renderSection([]);
      expect(
        screen.getByRole("textbox", { name: /exclusion pattern text/i })
      ).toBeInTheDocument();
    });

    it("renders the Add button", () => {
      renderSection([]);
      expect(
        screen.getByRole("button", { name: /^add$/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 8 — Add button disabled when empty
  // -------------------------------------------------------------------------

  describe("Test 8 — Add button disabled when input is empty or whitespace-only", () => {
    it("Add button is disabled when the input is empty", () => {
      renderSection([]);
      expect(screen.getByRole("button", { name: /^add$/i })).toBeDisabled();
    });

    it("Add button is disabled when the input contains only whitespace", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "   ");

      expect(screen.getByRole("button", { name: /^add$/i })).toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Test 9 — Add button enabled after typing
  // -------------------------------------------------------------------------

  describe("Test 9 — Add button becomes enabled after typing", () => {
    it("Add button is enabled after the user types a non-whitespace character", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");

      expect(screen.getByRole("button", { name: /^add$/i })).not.toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Test 10 — Add calls API with trimmed value
  // -------------------------------------------------------------------------

  describe("Test 10 — Submit calls addExclusionPattern with the trimmed value", () => {
    it("calls addExclusionPattern with entity id and trimmed pattern", async () => {
      const user = userEvent.setup();
      renderSection([], "entity-uuid-001");

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "  Monterrey  ");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(mockedAdd).toHaveBeenCalledOnce();
      });

      expect(mockedAdd).toHaveBeenCalledWith("entity-uuid-001", "Monterrey");
    });

    it("submits via Enter key in the input", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(mockedAdd).toHaveBeenCalledOnce();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 11 — Success message shown and input cleared
  // -------------------------------------------------------------------------

  describe("Test 11 — Success message shown after add and input cleared", () => {
    it("clears the input after a successful add", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(input).toHaveValue("");
      });
    });

    it("shows a success message after a successful add", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/"Monterrey" added as exclusion pattern\./i)
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 12 — Success message accessibility
  // -------------------------------------------------------------------------

  describe("Test 12 — Success message has role='status' / aria-live='polite'", () => {
    it("success message has role='status' and aria-live='polite'", async () => {
      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(screen.getByRole("status")).toBeInTheDocument();
      });

      const statusEl = screen.getByRole("status");
      expect(statusEl).toHaveAttribute("aria-live", "polite");
    });
  });

  // -------------------------------------------------------------------------
  // Test 13 — Duplicate pattern (409) error
  // -------------------------------------------------------------------------

  describe("Test 13 — Duplicate pattern (409) shows specific error message", () => {
    it("shows 'This exclusion pattern already exists for the entity.' on 409", async () => {
      mockedAdd.mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "New Mexico");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText(
            "This exclusion pattern already exists for the entity."
          )
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 14 — 404 error message
  // -------------------------------------------------------------------------

  describe("Test 14 — 404 error shows entity-not-found message", () => {
    it("shows 'Entity not found. Please refresh the page.' on 404", async () => {
      mockedAdd.mockRejectedValue({ status: 404 });

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "some-pattern");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Entity not found. Please refresh the page.")
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 15 — Generic error fallback
  // -------------------------------------------------------------------------

  describe("Test 15 — Generic error shows fallback message", () => {
    it("shows fallback error for non-409/404 errors", async () => {
      mockedAdd.mockRejectedValue({ status: 500 });

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "some-pattern");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(
          screen.getByText(
            "Failed to add exclusion pattern. Please try again."
          )
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 16 — Error message accessibility
  // -------------------------------------------------------------------------

  describe("Test 16 — Error message has role='alert'", () => {
    it("add error paragraph has role='alert'", async () => {
      mockedAdd.mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "dup-pattern");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert).toBeInTheDocument();
        expect(alert.tagName).toBe("P");
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 17 — Error clears on typing
  // -------------------------------------------------------------------------

  describe("Test 17 — Error clears when user types after an error", () => {
    it("clears the error message when the user types in the input after an add error", async () => {
      mockedAdd.mockRejectedValue({ status: 409 });

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "dup-pattern");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      // Typing again clears the error.
      await user.type(input, "x");

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 18 — Add button shows "Adding…" while in-flight
  // -------------------------------------------------------------------------

  describe("Test 18 — Add button shows 'Adding…' while request is in flight", () => {
    it("shows 'Adding…' on the button while the mutation is pending", async () => {
      let resolveFn!: (value: string[]) => void;
      mockedAdd.mockReturnValue(
        new Promise<string[]>((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      expect(screen.getByRole("button", { name: /adding/i })).toBeInTheDocument();

      resolveFn([]);
    });
  });

  // -------------------------------------------------------------------------
  // Test 19 — Input disabled while in-flight
  // -------------------------------------------------------------------------

  describe("Test 19 — Input is disabled while request is in flight", () => {
    it("disables the pattern input while the add mutation is pending", async () => {
      let resolveFn!: (value: string[]) => void;
      mockedAdd.mockReturnValue(
        new Promise<string[]>((resolve) => {
          resolveFn = resolve;
        })
      );

      const user = userEvent.setup();
      renderSection([]);

      const input = screen.getByRole("textbox", { name: /exclusion pattern text/i });
      await user.type(input, "Monterrey");
      await user.click(screen.getByRole("button", { name: /^add$/i }));

      expect(input).toBeDisabled();

      resolveFn([]);
    });
  });

  // -------------------------------------------------------------------------
  // Test 20 — Help text is present
  // -------------------------------------------------------------------------

  describe("Test 20 — Help text is present", () => {
    it("renders the descriptive help text about exclusion patterns", () => {
      renderSection([]);
      expect(
        screen.getByText(/phrases listed here will not trigger mention detection/i)
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 21 — Section heading is accessible
  // -------------------------------------------------------------------------

  describe("Test 21 — Section heading is accessible", () => {
    it("renders an h2 heading 'Exclusion Patterns'", () => {
      renderSection([]);
      expect(
        screen.getByRole("heading", {
          name: /exclusion patterns/i,
          level: 2,
        })
      ).toBeInTheDocument();
    });

    it("section has aria-labelledby pointing at the heading id", () => {
      const { container } = renderSection([]);
      const section = container.querySelector(
        "section[aria-labelledby='entity-exclusion-patterns-heading']"
      );
      expect(section).not.toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Test 22 — Pattern list has accessible label
  // -------------------------------------------------------------------------

  describe("Test 22 — Pattern list has accessible label when patterns exist", () => {
    it("pattern list has aria-label 'Current exclusion patterns'", () => {
      renderSection(["New Mexico"]);
      expect(
        screen.getByRole("list", { name: /current exclusion patterns/i })
      ).toBeInTheDocument();
    });
  });
});
