/**
 * Unit tests for TextHighlighter component.
 *
 * Tests text splitting, mark element rendering, active match styling,
 * empty query rendering, and multiple matches.
 *
 * @module tests/components/transcript/TextHighlighter
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { TextHighlighter } from "../../../components/transcript/TextHighlighter";
import type { TranscriptSearchMatch } from "../../../hooks/useTranscriptSearch";

/**
 * Helper to build a TranscriptSearchMatch.
 */
function makeMatch(
  segmentIndex: number,
  startOffset: number,
  length: number
): TranscriptSearchMatch {
  return { segmentIndex, startOffset, length };
}

describe("TextHighlighter", () => {
  describe("no matches renders plain text", () => {
    it("renders full text without any marks when matches is empty", () => {
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[]}
        />
      );

      expect(container.textContent).toBe("Hello world");
      expect(container.querySelectorAll("mark")).toHaveLength(0);
    });

    it("renders plain text when no matches belong to this segment", () => {
      // A match exists but for a different segment
      const otherSegmentMatch = makeMatch(5, 0, 4);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[otherSegmentMatch]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[otherSegmentMatch]}
        />
      );

      expect(container.textContent).toBe("Hello world");
      expect(container.querySelectorAll("mark")).toHaveLength(0);
    });
  });

  describe("text splits correctly at match positions", () => {
    it("splits text into before, match, and after portions", () => {
      const match = makeMatch(0, 6, 5); // "world" at position 6 in "Hello world"
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      expect(container.textContent).toBe("Hello world");

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(1);
      expect(marks[0]?.textContent).toBe("world");
    });

    it("handles match at the very beginning of text", () => {
      const match = makeMatch(0, 0, 5); // "Hello" at start
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(1);
      expect(marks[0]?.textContent).toBe("Hello");
      // Should be "Hello" (mark) + " world" (span)
      expect(container.textContent).toBe("Hello world");
    });

    it("handles match at the very end of text", () => {
      const match = makeMatch(0, 6, 5); // "world" at end of "Hello world"
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(1);
      expect(marks[0]?.textContent).toBe("world");
    });
  });

  describe("mark elements render with correct styling", () => {
    it("renders non-active match with amber-200 background classes", () => {
      const match = makeMatch(0, 6, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1} // Not active
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark).toBeInTheDocument();
      // Non-active: amber-200 background, bold, underline
      expect(mark?.className).toContain("bg-amber-200");
      expect(mark?.className).toContain("font-bold");
      expect(mark?.className).toContain("underline");
    });

    it("non-active match does NOT have ring classes", () => {
      const match = makeMatch(0, 6, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark?.className).not.toContain("ring-2");
      expect(mark?.className).not.toContain("bg-amber-400");
    });
  });

  describe("active match gets distinct style", () => {
    it("renders active match with amber-400 background and ring", () => {
      const match = makeMatch(0, 6, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={0} // This match IS active
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark).toBeInTheDocument();
      // Active: amber-400 background + ring
      expect(mark?.className).toContain("bg-amber-400");
      expect(mark?.className).toContain("ring-2");
      expect(mark?.className).toContain("font-bold");
      expect(mark?.className).toContain("underline");
    });

    it("active match has aria-current='true'", () => {
      const match = makeMatch(0, 0, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark).toHaveAttribute("aria-current", "true");
    });

    it("non-active match does NOT have aria-current", () => {
      const match = makeMatch(0, 6, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark).not.toHaveAttribute("aria-current");
    });

    it("highlights correct match as active when there are multiple", () => {
      // "test test test" — match at 0, 5, 10
      const match0 = makeMatch(0, 0, 4);
      const match1 = makeMatch(0, 5, 4);
      const match2 = makeMatch(0, 10, 4);
      const allMatches = [match0, match1, match2];

      const { container } = render(
        <TextHighlighter
          text="test test test"
          matches={allMatches}
          segmentIndex={0}
          activeMatchIndex={1} // Second match is active
          allMatches={allMatches}
        />
      );

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(3);

      // Second mark (index 1) should be active
      expect(marks[0]?.className).not.toContain("bg-amber-400");
      expect(marks[1]?.className).toContain("bg-amber-400");
      expect(marks[2]?.className).not.toContain("bg-amber-400");
    });
  });

  describe("multiple matches in same text", () => {
    it("renders all matches as mark elements", () => {
      const match0 = makeMatch(0, 0, 4);  // first "test"
      const match1 = makeMatch(0, 5, 4);  // second "test"
      const match2 = makeMatch(0, 10, 4); // third "test"
      const allMatches = [match0, match1, match2];

      const { container } = render(
        <TextHighlighter
          text="test test test"
          matches={allMatches}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={allMatches}
        />
      );

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(3);
      marks.forEach((mark) => {
        expect(mark.textContent).toBe("test");
      });
    });

    it("preserves text between matches", () => {
      const match0 = makeMatch(0, 0, 3);  // "abc"
      const match1 = makeMatch(0, 8, 3);  // "abc" (second)
      const allMatches = [match0, match1];

      const { container } = render(
        <TextHighlighter
          text="abc defg abc"
          matches={allMatches}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={allMatches}
        />
      );

      // Total text should be preserved
      expect(container.textContent).toBe("abc defg abc");

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(2);
    });
  });

  describe("active match across multiple segments", () => {
    it("does not mark as active a match from this segment when active index belongs to different segment", () => {
      const matchSeg0 = makeMatch(0, 6, 5);
      const matchSeg1 = makeMatch(1, 0, 5);
      const allMatches = [matchSeg0, matchSeg1];

      // Rendering segment 0, active index is 1 (which is in segment 1)
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={allMatches}
          segmentIndex={0}
          activeMatchIndex={1}
          allMatches={allMatches}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark?.className).toContain("bg-amber-200");
      expect(mark?.className).not.toContain("bg-amber-400");
    });
  });

  describe("accessibility — not color alone (NFR-003)", () => {
    it("active match uses bold AND underline in addition to background color", () => {
      const match = makeMatch(0, 0, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      // Must have BOTH bold AND underline — not just color
      expect(mark?.className).toContain("font-bold");
      expect(mark?.className).toContain("underline");
    });

    it("non-active match uses bold AND underline in addition to background color", () => {
      const match = makeMatch(0, 0, 5);
      const { container } = render(
        <TextHighlighter
          text="Hello world"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={-1}
          allMatches={[match]}
        />
      );

      const mark = container.querySelector("mark");
      expect(mark?.className).toContain("font-bold");
      expect(mark?.className).toContain("underline");
    });
  });

  describe("edge cases", () => {
    it("handles empty text string", () => {
      const { container } = render(
        <TextHighlighter
          text=""
          matches={[]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[]}
        />
      );

      expect(container.textContent).toBe("");
      expect(container.querySelectorAll("mark")).toHaveLength(0);
    });

    it("preserves full text content with marks", () => {
      const match = makeMatch(0, 7, 7); // "testing" in "Welcome testing here"
      const { container } = render(
        <TextHighlighter
          text="Welcome testing here"
          matches={[match]}
          segmentIndex={0}
          activeMatchIndex={0}
          allMatches={[match]}
        />
      );

      expect(container.textContent).toBe("Welcome testing here");
    });
  });
});
