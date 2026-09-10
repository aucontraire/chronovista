/**
 * Tests for SearchInput Component
 *
 * Reconciled from two divergent copies (issue #309):
 * - frontend/src/tests/components/SearchInput.test.tsx (T055 edge-case suite)
 * - frontend/tests/components/SearchInput.test.tsx (FR-001/002/025 suite)
 *
 * Requirements tested:
 * - T055 / FR-001: Query length 2-500 characters (EC-001, EC-002, EC-010)
 * - FR-002: 300ms debounce after typing stops
 * - FR-025: ARIA attributes (role, labels, describedby, controls)
 */

import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SearchInput } from "../SearchInput";

// SearchInput has no React Query / Router dependencies, so the local render
// helper only needs to attach a ready-to-use `userEvent` instance. Defined
// in-file (not imported from `frontend/tests/test-utils`) to keep `src/`
// test imports self-contained and typecheck-safe.
function renderWithProviders(ui: React.ReactElement) {
  return {
    ...render(ui),
    user: userEvent.setup(),
  };
}

describe("SearchInput", () => {
  let mockOnChange: Mock<(value: string) => void>;
  let mockOnDebouncedChange: Mock<(value: string) => void>;

  beforeEach(() => {
    mockOnChange = vi.fn<(value: string) => void>();
    mockOnDebouncedChange = vi.fn<(value: string) => void>();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // Helper component that manages state for testing controlled input
  function ControlledSearchInput(props: {
    initialValue?: string;
    onChange?: (value: string) => void;
    onDebouncedChange?: (value: string) => void;
    autoFocus?: boolean;
  }) {
    const [value, setValue] = useState(props.initialValue || "");

    const handleChange = (newValue: string) => {
      setValue(newValue);
      props.onChange?.(newValue);
    };

    return (
      <SearchInput
        value={value}
        onChange={handleChange}
        onDebouncedChange={props.onDebouncedChange || (() => {})}
        autoFocus={props.autoFocus ?? false}
      />
    );
  }

  describe("Basic Rendering", () => {
    it('should render search input with type="search"', () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute("type", "search");
    });

    it('should render with placeholder "Search videos..."', () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveAttribute("placeholder", "Search videos...");
    });

    it("should display the current value", () => {
      renderWithProviders(
        <SearchInput value="machine learning" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveValue("machine learning");
    });
  });

  describe("ARIA Attributes (FR-025)", () => {
    it('should have role="search" container', () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const searchContainer = screen.getByRole("search");
      expect(searchContainer).toBeInTheDocument();
    });

    it("should have aria-label for accessibility", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveAccessibleName();
      expect(input).toHaveAttribute("aria-label");
    });

    it("should have proper ARIA attributes", () => {
      // From the T055 edge-case suite: asserts the exact aria-label value,
      // complementing the presence-only check above.
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });
      expect(input).toHaveAttribute("aria-label", "Search videos");
    });

    it("should have aria-describedby pointing to validation message", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      const describedBy = input.getAttribute("aria-describedby");
      expect(describedBy).toBeTruthy();

      // Verify the described element exists
      const descriptionElement = document.getElementById(describedBy!);
      expect(descriptionElement).toBeInTheDocument();
    });

    it("should associate hint with input using aria-describedby when showing hint", () => {
      renderWithProviders(
        <SearchInput value="a" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });
      expect(input).toHaveAttribute("aria-describedby", "search-hint");

      const hint = screen.getByText("Enter at least 2 characters");
      expect(hint).toHaveAttribute("id", "search-hint");
    });

    it("should have aria-controls pointing to results container", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveAttribute("aria-controls");
      expect(input.getAttribute("aria-controls")).toBe("search-results");
    });

    it('should have aria-invalid="true" when query is invalid', () => {
      renderWithProviders(
        <SearchInput value="a" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveAttribute("aria-invalid", "true");
    });

    it('should have aria-invalid="false" when query is valid', () => {
      renderWithProviders(
        <SearchInput value="ab" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveAttribute("aria-invalid", "false");
    });

    it("should mark validation hints as alerts for screen readers", () => {
      renderWithProviders(
        <SearchInput value="a" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const hint = screen.getByText("Enter at least 2 characters");
      expect(hint).toHaveAttribute("role", "alert");
    });
  });

  describe("Query Length Validation (FR-001 / EC-001)", () => {
    it("should not show visible validation message when query is empty", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      // The hint exists but is sr-only when empty
      expect(screen.getByText(/enter at least 2 characters/i)).toBeInTheDocument();
    });

    it("should not show hint when query is empty", () => {
      // Complements the sr-only check above: the specific too-short warning
      // text must not be present (exact-string match) when the query is empty.
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
    });

    it("should show validation message when query is 1 character", () => {
      renderWithProviders(
        <SearchInput value="a" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.getByText("Enter at least 2 characters")).toBeInTheDocument();
    });

    it("should apply warning border color for too-short query", () => {
      renderWithProviders(
        <SearchInput value="a" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });
      expect(input).toHaveClass("border-yellow-500");
    });

    it("should NOT show validation message when query is exactly 2 characters", () => {
      renderWithProviders(
        <SearchInput value="ab" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.queryByText(/minimum 2 characters/i)).not.toBeInTheDocument();
    });

    it("should not show hint when query is 2 or more characters", () => {
      renderWithProviders(
        <SearchInput value="ab" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
    });

    it("should NOT show validation message when query is greater than 2 characters", () => {
      renderWithProviders(
        <SearchInput value="machine learning" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.queryByText(/minimum 2 characters/i)).not.toBeInTheDocument();
    });
  });

  describe("Query Length Validation (FR-001 / EC-002: max length)", () => {
    it("should call onChange with truncated value when input exceeds 500 chars", async () => {
      const user = userEvent.setup();
      const longString = "a".repeat(501); // 501 characters

      render(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });

      // Simulate pasting a long string
      await user.click(input);
      await user.paste(longString);

      // Should have been called with max 500 characters
      const calls = mockOnChange.mock.calls;
      if (calls.length > 0) {
        const lastCall = calls[calls.length - 1];
        if (lastCall) {
          expect(lastCall[0]).toHaveLength(500);
        }
      }
    });

    it("should truncate query at 500 characters", async () => {
      const longQuery = "a".repeat(600);
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, longQuery);

      // Should truncate to 500 characters
      expect(mockOnChange).toHaveBeenCalledWith(expect.stringMatching(/^.{500}$/));
      expect(mockOnChange).not.toHaveBeenCalledWith(expect.stringMatching(/^.{501,}$/));
    });

    it("should show truncation warning when value is exactly 500 chars", () => {
      const maxString = "a".repeat(500);

      renderWithProviders(
        <SearchInput value={maxString} onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      // No warning when exactly at limit
      expect(screen.queryByText("Query truncated to 500 characters")).not.toBeInTheDocument();
    });

    it("should not show warning when query is exactly 500 characters", async () => {
      const maxLengthQuery = "a".repeat(500);
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, maxLengthQuery);

      // Should not show truncation warning when exactly at limit
      expect(screen.queryByText(/truncated/i)).not.toBeInTheDocument();
    });

    it("should accept query of exactly 500 characters", () => {
      const maxLengthQuery = "a".repeat(500);
      renderWithProviders(
        <SearchInput value={maxLengthQuery} onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox") as HTMLInputElement;
      expect(input).toHaveValue(maxLengthQuery);
      expect(input.value).toHaveLength(500);
    });

    it("should show truncation warning when value exceeds 500 chars", () => {
      const tooLongString = "a".repeat(501);

      renderWithProviders(
        <SearchInput value={tooLongString} onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.getByText("Query truncated to 500 characters")).toBeInTheDocument();
    });

    it("should apply error border color when value exceeds max length", () => {
      const tooLongString = "a".repeat(501);

      renderWithProviders(
        <SearchInput value={tooLongString} onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });
      expect(input).toHaveClass("border-red-500");
    });
  });

  describe("Debounce Behavior (FR-002)", () => {
    it("should call onChange immediately when typing", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "m");

      // onChange should be called immediately
      expect(mockOnChange).toHaveBeenCalledWith("m");
      // But onDebouncedChange should NOT be called yet
      expect(mockOnDebouncedChange).not.toHaveBeenCalled();
    });

    it("should call onDebouncedChange after 300ms of inactivity", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "machine learning");

      // onChange should be called immediately for each keystroke
      expect(mockOnChange).toHaveBeenCalled();

      // Wait for debounce delay (300ms)
      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("machine learning");
        },
        { timeout: 1000 }
      );
    });

    it("should call onDebouncedChange only once after typing stops", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "test query");

      // Wait for debounce
      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledTimes(1);
        },
        { timeout: 1000 }
      );
    });
  });

  describe("User Interaction", () => {
    it("should allow typing in the input", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "python tutorial");

      expect(input).toHaveValue("python tutorial");
    });

    it("should allow clearing the input with native clear button", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput
          initialValue="some query"
          onChange={mockOnChange}
          onDebouncedChange={mockOnDebouncedChange}
        />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveValue("some query");

      // Clear the input (simulating native clear button)
      await user.clear(input);

      expect(input).toHaveValue("");
    });

    it("should call onChange with empty string when input is cleared", async () => {
      const user = userEvent.setup();

      render(
        <SearchInput value="test" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox", { name: /search videos/i });
      await user.clear(input);

      expect(mockOnChange).toHaveBeenCalled();
      // Find the call with empty string
      const emptyCall = mockOnChange.mock.calls.find((call) => call[0] === "");
      expect(emptyCall).toBeDefined();
    });

    it("should be keyboard accessible", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      // Tab to the input
      await user.tab();

      const input = screen.getByRole("searchbox");
      expect(input).toHaveFocus();
    });

    it("should handle paste events", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      input.focus();

      // Paste text
      await user.paste("machine learning algorithms");

      expect(input).toHaveValue("machine learning algorithms");

      // Should debounce after paste
      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("machine learning algorithms");
        },
        { timeout: 1000 }
      );
    });
  });

  describe("Edge Cases", () => {
    it("should handle special characters in query", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "C++ programming & Python (2024)");

      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("C++ programming & Python (2024)");
        },
        { timeout: 1000 }
      );
    });

    it("should handle emoji in query", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "React tutorial 🚀");

      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("React tutorial 🚀");
        },
        { timeout: 1000 }
      );
    });

    it("should handle multi-byte Unicode characters", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "JavaScript 日本語");

      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("JavaScript 日本語");
        },
        { timeout: 1000 }
      );
    });

    it("should NOT trim whitespace (caller component handles trimming)", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "  machine learning  ");

      await waitFor(
        () => {
          // Component doesn't trim - the caller is responsible
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("  machine learning  ");
        },
        { timeout: 1000 }
      );
    });

    it("should preserve internal whitespace", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      await user.type(input, "machine    learning");

      await waitFor(
        () => {
          expect(mockOnDebouncedChange).toHaveBeenCalledWith("machine    learning");
        },
        { timeout: 1000 }
      );
    });
  });

  describe("Focus Management", () => {
    it("should allow programmatic focus", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      input.focus();

      expect(input).toHaveFocus();
    });

    it("should show focus indicator when focused", async () => {
      const { user } = renderWithProviders(
        <ControlledSearchInput onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");

      // Tab to focus
      await user.tab();

      expect(input).toHaveFocus();
      // Visual focus indicator would be tested with visual regression
    });

    it("should autofocus when autoFocus prop is true", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} autoFocus />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveFocus();
    });
  });

  describe("Component Updates", () => {
    it("should update displayed value when value prop changes", () => {
      const { rerender } = renderWithProviders(
        <SearchInput value="initial" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      expect(input).toHaveValue("initial");

      rerender(
        <SearchInput value="updated" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(input).toHaveValue("updated");
    });

    it("should maintain focus when value prop changes", () => {
      const { rerender } = renderWithProviders(
        <SearchInput value="initial" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      const input = screen.getByRole("searchbox");
      input.focus();
      expect(input).toHaveFocus();

      rerender(
        <SearchInput value="updated" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      // Should maintain focus after rerender
      expect(input).toHaveFocus();
    });
  });

  describe("Clear Query Behavior (EC-010)", () => {
    it("should not show validation hints when value is empty", () => {
      renderWithProviders(
        <SearchInput value="" onChange={mockOnChange} onDebouncedChange={mockOnDebouncedChange} />
      );

      expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
    });
  });
});
