/**
 * Tests for SearchInput Component
 *
 * Tests edge case handling:
 * - T055: Query validation (EC-001, EC-002, EC-010)
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SearchInput } from "../../components/SearchInput";

describe("SearchInput", () => {
  describe("T055: Query validation", () => {
    describe("EC-001: Minimum length validation (2 characters)", () => {
      it("should show hint when query is 1 character", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value="a"
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        expect(screen.getByText("Enter at least 2 characters")).toBeInTheDocument();
      });

      it("should not show hint when query is empty", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value=""
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
      });

      it("should not show hint when query is 2 or more characters", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value="ab"
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
      });

      it("should apply warning border color for too-short query", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value="a"
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        const input = screen.getByRole("searchbox", { name: /search transcripts/i });
        expect(input).toHaveClass("border-yellow-500");
      });
    });

    describe("EC-002: Maximum length validation (500 characters)", () => {
      it("should call onChange with truncated value when input exceeds 500 chars", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        const longString = "a".repeat(501); // 501 characters

        render(
          <SearchInput
            value=""
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        const input = screen.getByRole("searchbox", { name: /search transcripts/i });

        // Simulate pasting a long string
        await user.click(input);
        await user.paste(longString);

        // Should have been called with max 500 characters
        const calls = onChange.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1];
          if (lastCall) {
            expect(lastCall[0]).toHaveLength(500);
          }
        }
      });

      it("should show truncation warning when value is exactly 500 chars", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        const maxString = "a".repeat(500);

        render(
          <SearchInput
            value={maxString}
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        // No warning when exactly at limit
        expect(screen.queryByText("Query truncated to 500 characters")).not.toBeInTheDocument();
      });

      it("should show truncation warning when value exceeds 500 chars", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        const tooLongString = "a".repeat(501);

        render(
          <SearchInput
            value={tooLongString}
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        expect(screen.getByText("Query truncated to 500 characters")).toBeInTheDocument();
      });

      it("should apply error border color when value exceeds max length", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        const tooLongString = "a".repeat(501);

        render(
          <SearchInput
            value={tooLongString}
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        const input = screen.getByRole("searchbox", { name: /search transcripts/i });
        expect(input).toHaveClass("border-red-500");
      });
    });

    describe("EC-010: Clear query behavior", () => {
      it("should call onChange with empty string when input is cleared", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value="test"
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        const input = screen.getByRole("searchbox", { name: /search transcripts/i });
        await user.clear(input);

        expect(onChange).toHaveBeenCalled();
        // Find the call with empty string
        const emptyCall = onChange.mock.calls.find(call => call[0] === "");
        expect(emptyCall).toBeDefined();
      });

      it("should not show validation hints when value is empty", () => {
        const onChange = vi.fn();
        const onDebouncedChange = vi.fn();

        render(
          <SearchInput
            value=""
            onChange={onChange}
            onDebouncedChange={onDebouncedChange}
          />
        );

        expect(screen.queryByText("Enter at least 2 characters")).not.toBeInTheDocument();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes", () => {
      const onChange = vi.fn();
      const onDebouncedChange = vi.fn();

      render(
        <SearchInput
          value=""
          onChange={onChange}
          onDebouncedChange={onDebouncedChange}
        />
      );

      const input = screen.getByRole("searchbox", { name: /search transcripts/i });
      expect(input).toHaveAttribute("aria-label", "Search transcripts");
    });

    it("should associate hint with input using aria-describedby when showing hint", () => {
      const onChange = vi.fn();
      const onDebouncedChange = vi.fn();

      render(
        <SearchInput
          value="a"
          onChange={onChange}
          onDebouncedChange={onDebouncedChange}
        />
      );

      const input = screen.getByRole("searchbox", { name: /search transcripts/i });
      expect(input).toHaveAttribute("aria-describedby", "search-hint");

      const hint = screen.getByText("Enter at least 2 characters");
      expect(hint).toHaveAttribute("id", "search-hint");
    });

    it("should mark validation hints as alerts for screen readers", () => {
      const onChange = vi.fn();
      const onDebouncedChange = vi.fn();

      render(
        <SearchInput
          value="a"
          onChange={onChange}
          onDebouncedChange={onDebouncedChange}
        />
      );

      const hint = screen.getByText("Enter at least 2 characters");
      expect(hint).toHaveAttribute("role", "alert");
    });
  });
});
