/**
 * Tests for SearchResult Component.
 *
 * Coverage:
 * - Deep Link URLs (T009): title/timestamp links include lang/seg/t params,
 *   correctly floored start_time, identical hrefs on both links.
 * - Rendering, highlighting, accessibility: video title/channel/segment
 *   text/match count, "Unknown Channel" fallback (EC-007), timestamp
 *   formatting (FR-003), query-term highlighting, upload date, keyboard
 *   navigation, context expansion, long text and special-character handling.
 *
 * Merged from two divergent copies (#309 Phase 3 consolidation): this file
 * (Deep Link URL suite) absorbed `tests/components/SearchResult.test.tsx`
 * (general rendering/highlighting/accessibility suite) — the two covered
 * entirely disjoint concerns, so this is a straight union with no dropped
 * cases.
 *
 * The source suite's `mockSegment` literal lived under `tests/`, which
 * `tsconfig.json` excludes from `tsc --noEmit` (see #159), and was missing
 * the required `availability_status` field. It is rebuilt here via
 * `createTestSegment(...)` (this file's existing factory, which already
 * supplies that field) instead of a bare object literal.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SearchResult } from "../SearchResult";
import type { SearchResultSegment } from "../../types/search";

/**
 * Test factory to generate SearchResultSegment test data.
 */
function createTestSegment(overrides: Partial<SearchResultSegment> = {}): SearchResultSegment {
  return {
    segment_id: 42,
    video_id: "test-video-123",
    video_title: "Test Video Title",
    channel_title: "Test Channel",
    language_code: "en-US",
    text: "This is test transcript text with a match.",
    start_time: 125.5,
    end_time: 130.0,
    context_before: "Context before the match.",
    context_after: "Context after the match.",
    match_count: 1,
    video_upload_date: "2024-01-15T00:00:00Z",
    availability_status: "available",
    ...overrides,
  };
}

/**
 * Helper to render SearchResult with MemoryRouter. Returns a configured
 * `user` for interaction tests (tab/click/hover/keyboard).
 */
function renderSearchResult(segment: SearchResultSegment, queryTerms: string[] = ["test"]) {
  const result = render(
    <MemoryRouter>
      <SearchResult segment={segment} queryTerms={queryTerms} />
    </MemoryRouter>
  );
  return {
    ...result,
    user: userEvent.setup(),
  };
}

describe("SearchResult - Deep Link URLs", () => {
  describe("Title Link", () => {
    it("should include all deep link params: lang, seg, t", () => {
      const segment = createTestSegment({
        video_id: "test-video-123",
        language_code: "en-US",
        segment_id: 42,
        start_time: 125.5,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("lang=en-US");
      expect(href).toContain("seg=42");
      expect(href).toContain("t=125");
    });

    it("should match pattern /videos/{video_id}?lang={language_code}&seg={segment_id}&t={floored_start_time}", () => {
      const segment = createTestSegment({
        video_id: "test-video-123",
        language_code: "en-US",
        segment_id: 42,
        start_time: 125.5,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Math.floor(125.5) = 125
      expect(href).toBe("/videos/test-video-123?lang=en-US&seg=42&t=125");
    });

    it("should correctly floor decimal start_time (125.9 → 125)", () => {
      const segment = createTestSegment({
        video_id: "abc123",
        language_code: "es-MX",
        segment_id: 100,
        start_time: 125.9,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toBe("/videos/abc123?lang=es-MX&seg=100&t=125");
    });

    it("should handle start_time with no fractional part (60.0 → 60)", () => {
      const segment = createTestSegment({
        video_id: "xyz789",
        language_code: "fr-FR",
        segment_id: 10,
        start_time: 60.0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toBe("/videos/xyz789?lang=fr-FR&seg=10&t=60");
    });

    it("should handle start_time = 0", () => {
      const segment = createTestSegment({
        video_id: "start-vid",
        language_code: "en",
        segment_id: 1,
        start_time: 0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toBe("/videos/start-vid?lang=en&seg=1&t=0");
    });

    it("should handle large start_time values (3661.7 → 3661)", () => {
      const segment = createTestSegment({
        video_id: "long-vid",
        language_code: "ja-JP",
        segment_id: 250,
        start_time: 3661.7, // 1 hour, 1 minute, 1.7 seconds
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toBe("/videos/long-vid?lang=ja-JP&seg=250&t=3661");
    });
  });

  describe("Timestamp Link", () => {
    it("should include all deep link params: lang, seg, t", () => {
      const segment = createTestSegment({
        video_id: "test-video-456",
        language_code: "de-DE",
        segment_id: 99,
        start_time: 200.3,
      });

      renderSearchResult(segment);

      const timestampLink = screen.getByLabelText(/Jump to/i);
      const href = (timestampLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("lang=de-DE");
      expect(href).toContain("seg=99");
      expect(href).toContain("t=200");
    });

    it("should match the same URL pattern as title link", () => {
      const segment = createTestSegment({
        video_id: "same-url-test",
        language_code: "pt-BR",
        segment_id: 55,
        start_time: 88.8,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const timestampLink = screen.getByLabelText(/Jump to/i);

      const titleHref = (titleLink as HTMLAnchorElement).getAttribute("href");
      const timestampHref = (timestampLink as HTMLAnchorElement).getAttribute("href");

      // Both links should have the exact same href
      expect(titleHref).toBe(timestampHref);
    });

    it("should correctly floor decimal start_time (300.99 → 300)", () => {
      const segment = createTestSegment({
        video_id: "precise-time",
        language_code: "ko-KR",
        segment_id: 77,
        start_time: 300.99,
      });

      renderSearchResult(segment);

      const timestampLink = screen.getByLabelText(/Jump to/i);
      const href = (timestampLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toBe("/videos/precise-time?lang=ko-KR&seg=77&t=300");
    });

    it("should use aria-label for accessibility", () => {
      const segment = createTestSegment({
        start_time: 125.5,
        end_time: 130.0,
      });

      renderSearchResult(segment);

      // The timestamp link should have an aria-label that includes "Jump to"
      const timestampLink = screen.getByLabelText(/Jump to.*in video/i);
      expect(timestampLink).toBeInTheDocument();
    });
  });

  describe("Parameter Values from SearchResultSegment", () => {
    it("should use segment_id from SearchResultSegment", () => {
      const segment = createTestSegment({
        segment_id: 9999,
        video_id: "seg-test",
        language_code: "en",
        start_time: 10.0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("seg=9999");
    });

    it("should use language_code from SearchResultSegment", () => {
      const segment = createTestSegment({
        video_id: "lang-test",
        language_code: "zh-CN",
        segment_id: 1,
        start_time: 5.0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("lang=zh-CN");
    });

    it("should use video_id from SearchResultSegment", () => {
      const segment = createTestSegment({
        video_id: "unique-vid-789",
        language_code: "en",
        segment_id: 1,
        start_time: 0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("/videos/unique-vid-789");
    });

    it("should use start_time from SearchResultSegment", () => {
      const segment = createTestSegment({
        video_id: "time-test",
        language_code: "en",
        segment_id: 1,
        start_time: 456.123,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Math.floor(456.123) = 456
      expect(href).toContain("t=456");
    });

    it("should handle language code variations (BCP-47 format)", () => {
      const testCases = [
        { language_code: "en", expected: "lang=en" },
        { language_code: "en-US", expected: "lang=en-US" },
        { language_code: "es-MX", expected: "lang=es-MX" },
        { language_code: "zh-Hans-CN", expected: "lang=zh-Hans-CN" }, // Complex BCP-47
      ];

      testCases.forEach(({ language_code, expected }) => {
        const segment = createTestSegment({
          video_id: "multi-lang",
          language_code,
          segment_id: 1,
          start_time: 0,
        });

        const { unmount } = renderSearchResult(segment);

        const titleLink = screen.getByRole("link", { name: /test video title/i });
        const href = (titleLink as HTMLAnchorElement).getAttribute("href");

        expect(href).toContain(expected);
        unmount();
      });
    });
  });

  describe("Math.floor behavior for time parameter", () => {
    it("should floor 0.1 to 0", () => {
      const segment = createTestSegment({ start_time: 0.1 });
      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("t=0");
    });

    it("should floor 0.9 to 0", () => {
      const segment = createTestSegment({ start_time: 0.9 });
      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("t=0");
    });

    it("should floor 59.999 to 59", () => {
      const segment = createTestSegment({ start_time: 59.999 });
      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      expect(href).toContain("t=59");
    });

    it("should handle negative start_time (edge case, though unlikely)", () => {
      const segment = createTestSegment({ start_time: -5.7 });
      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Math.floor(-5.7) = -6
      expect(href).toContain("t=-6");
    });
  });

  describe("URL construction", () => {
    it("should construct URL with all parameters in correct order", () => {
      const segment = createTestSegment({
        video_id: "order-test",
        language_code: "it-IT",
        segment_id: 333,
        start_time: 777.5,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Verify exact URL structure
      expect(href).toBe("/videos/order-test?lang=it-IT&seg=333&t=777");
    });

    it("should not include extra parameters", () => {
      const segment = createTestSegment();
      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Should only have lang, seg, and t parameters
      const url = new URL(href!, "http://test.com");
      const params = Array.from(url.searchParams.keys());

      expect(params).toHaveLength(3);
      expect(params).toContain("lang");
      expect(params).toContain("seg");
      expect(params).toContain("t");
    });

    it("should not encode language code with standard characters", () => {
      const segment = createTestSegment({
        language_code: "en-US",
        video_id: "encode-test",
        segment_id: 1,
        start_time: 0,
      });

      renderSearchResult(segment);

      const titleLink = screen.getByRole("link", { name: /test video title/i });
      const href = (titleLink as HTMLAnchorElement).getAttribute("href");

      // Language code should not be URL encoded
      expect(href).toContain("lang=en-US");
      expect(href).not.toContain("lang=en%2DUS");
    });
  });

  describe("Both links point to same URL", () => {
    it("should have title link and timestamp link with identical hrefs", () => {
      const testCases = [
        { video_id: "test1", language_code: "en", segment_id: 1, start_time: 0 },
        { video_id: "test2", language_code: "es-MX", segment_id: 50, start_time: 125.5 },
        { video_id: "test3", language_code: "ja-JP", segment_id: 999, start_time: 3600.8 },
      ];

      testCases.forEach((testCase) => {
        const segment = createTestSegment(testCase);
        const { unmount } = renderSearchResult(segment);

        const titleLink = screen.getByRole("link", { name: /test video title/i });
        const timestampLink = screen.getByLabelText(/Jump to/i);

        const titleHref = (titleLink as HTMLAnchorElement).getAttribute("href");
        const timestampHref = (timestampLink as HTMLAnchorElement).getAttribute("href");

        expect(titleHref).toBe(timestampHref);
        unmount();
      });
    });
  });

  describe("Integration with formatTimestamp", () => {
    it("should render timestamp range in link text", () => {
      const segment = createTestSegment({
        start_time: 125.5,
        end_time: 130.0,
      });

      renderSearchResult(segment);

      // The timestamp link should display the formatted time range
      const timestampLink = screen.getByLabelText(/Jump to/i);

      // formatTimestamp should format these as "2:05 - 2:10" (or similar)
      expect(timestampLink).toBeInTheDocument();
      expect(timestampLink.textContent).toContain(":");
    });

    it("should use floored start_time in URL regardless of formatted display", () => {
      const segment = createTestSegment({
        start_time: 125.9,
        end_time: 132.1,
      });

      renderSearchResult(segment);

      const timestampLink = screen.getByLabelText(/Jump to/i);
      const href = (timestampLink as HTMLAnchorElement).getAttribute("href");

      // URL should use floored start_time
      expect(href).toContain("t=125");

      // Display text will be formatted (we're not testing formatTimestamp here)
      expect(timestampLink.textContent).toBeTruthy();
    });
  });
});

describe("SearchResult - Rendering, Highlighting, Accessibility", () => {
  const mockSegment: SearchResultSegment = createTestSegment({
    segment_id: 1,
    video_id: "abc123def45",
    video_title: "Introduction to Machine Learning",
    channel_title: "Tech Education Hub",
    language_code: "en",
    text: "In this video, we will explore machine learning algorithms and their applications.",
    start_time: 154.5,
    end_time: 192.8,
    context_before: "Welcome to this comprehensive tutorial.",
    context_after: "Let us begin with supervised learning.",
    match_count: 2,
    video_upload_date: "2024-01-15T12:00:00Z",
  });

  const mockQueryTerms = ["machine", "learning"];

  describe("Basic Rendering", () => {
    it("should render video title", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      expect(screen.getByText("Introduction to Machine Learning")).toBeInTheDocument();
    });

    it("should render channel name", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      expect(screen.getByText("Tech Education Hub")).toBeInTheDocument();
    });

    it("should render segment text", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      // Text is split by highlighting, so use partial match
      expect(screen.getByText(/In this video, we will explore/)).toBeInTheDocument();
      expect(screen.getByText(/algorithms and their applications/)).toBeInTheDocument();
    });

    it("should render match count", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      expect(screen.getByText(/2.*match/i)).toBeInTheDocument();
    });
  });

  describe("Channel Name Handling (EC-007)", () => {
    it('should show "Unknown Channel" when channel_title is null', () => {
      const segmentWithoutChannel: SearchResultSegment = {
        ...mockSegment,
        channel_title: null,
      };

      renderSearchResult(segmentWithoutChannel, mockQueryTerms);

      expect(screen.getByText("Unknown Channel")).toBeInTheDocument();
    });

    it("should show channel name when channel_title is provided", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      expect(screen.getByText("Tech Education Hub")).toBeInTheDocument();
      expect(screen.queryByText("Unknown Channel")).not.toBeInTheDocument();
    });
  });

  describe("Timestamp Formatting (FR-003)", () => {
    it("should render formatted timestamp range in MM:SS format", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      // 154.5 seconds = 2:34, 192.8 seconds = 3:12
      expect(screen.getByText(/2:34.*3:12/)).toBeInTheDocument();
    });

    it("should handle timestamps less than 1 minute", () => {
      const segmentWithShortTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 15.0,
        end_time: 45.5,
      };

      renderSearchResult(segmentWithShortTime, mockQueryTerms);

      // 15 seconds = 0:15, 45.5 seconds = 0:45
      expect(screen.getByText(/0:15.*0:45/)).toBeInTheDocument();
    });

    it("should handle timestamps over 1 hour", () => {
      const segmentWithLongTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 3665.0,
        end_time: 3720.5,
      };

      renderSearchResult(segmentWithLongTime, mockQueryTerms);

      // 3665 seconds = 1:01:05, 3720.5 seconds = 1:02:00
      expect(screen.getByText(/1:01:05.*1:02:00/)).toBeInTheDocument();
    });

    it("should pad seconds with leading zero when needed", () => {
      const segmentWithPaddedTime: SearchResultSegment = {
        ...mockSegment,
        start_time: 125.0,
        end_time: 130.5,
      };

      renderSearchResult(segmentWithPaddedTime, mockQueryTerms);

      // 125 seconds = 2:05, 130.5 seconds = 2:10
      expect(screen.getByText(/2:05.*2:10/)).toBeInTheDocument();
    });

    it("should handle zero timestamp", () => {
      const segmentFromStart: SearchResultSegment = {
        ...mockSegment,
        start_time: 0.0,
        end_time: 10.5,
      };

      renderSearchResult(segmentFromStart, mockQueryTerms);

      // 0 seconds = 0:00, 10.5 seconds = 0:10
      expect(screen.getByText(/0:00.*0:10/)).toBeInTheDocument();
    });
  });

  describe("Query Term Highlighting", () => {
    it("should highlight query terms in segment text", () => {
      const { container } = renderSearchResult(mockSegment, mockQueryTerms);

      const marks = container.querySelectorAll("mark");
      expect(marks.length).toBeGreaterThan(0);

      // Should highlight both "machine" and "learning"
      const highlightedTexts = Array.from(marks).map((mark) => mark.textContent?.toLowerCase());
      expect(highlightedTexts).toContain("machine");
      expect(highlightedTexts).toContain("learning");
    });

    it("should highlight terms case-insensitively", () => {
      const segmentWithMixedCase: SearchResultSegment = {
        ...mockSegment,
        text: "MACHINE learning is important. Machine LEARNING algorithms are powerful.",
      };

      const { container } = renderSearchResult(segmentWithMixedCase, ["machine", "learning"]);

      const marks = container.querySelectorAll("mark");
      expect(marks.length).toBe(4); // 2 occurrences of "machine", 2 of "learning"
    });

    it("should not highlight when queryTerms is empty", () => {
      const { container } = renderSearchResult(mockSegment, []);

      const marks = container.querySelectorAll("mark");
      expect(marks).toHaveLength(0);
    });

    it("should preserve original text casing in highlights", () => {
      const { container } = renderSearchResult(mockSegment, mockQueryTerms);

      const marks = container.querySelectorAll("mark");
      const machineHighlight = Array.from(marks).find(
        (mark) => mark.textContent?.toLowerCase() === "machine"
      );

      expect(machineHighlight).toHaveTextContent("machine"); // Lowercase in original
    });
  });

  describe("Upload Date Rendering", () => {
    it("should render formatted upload date", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      // Should show date in readable format (e.g., "Jan 15, 2024")
      expect(screen.getByText(/Jan.*15.*2024/i)).toBeInTheDocument();
    });

    it("should handle different date formats", () => {
      const segmentWithDifferentDate: SearchResultSegment = {
        ...mockSegment,
        video_upload_date: "2023-12-31T23:59:59Z",
      };

      renderSearchResult(segmentWithDifferentDate, mockQueryTerms);

      expect(screen.getByText(/Dec.*31.*2023/i)).toBeInTheDocument();
    });
  });

  describe("Video Link Navigation (FR-005, FR-006)", () => {
    describe("Video Title Link (FR-006)", () => {
      it("should link video title to video detail page", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        const link = screen.getByRole("link", { name: /Introduction to Machine Learning/i });
        expect(link).toHaveAttribute("href", "/videos/abc123def45?lang=en&seg=1&t=154");
      });

      it("should have proper href attribute for video title link", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        const link = screen.getByRole("link", { name: /Introduction to Machine Learning/i });
        expect(link).toHaveAttribute("href");
        expect(link.getAttribute("href")).toMatch(/^\/videos\/[a-zA-Z0-9_-]+/);
      });

      it("should make video title keyboard accessible with Tab", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        const link = screen.getByRole("link", { name: /Introduction to Machine Learning/i });

        // Tab to the link
        await user.tab();

        expect(link).toHaveFocus();
      });

      it("should activate video title link with Enter key", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        const link = screen.getByRole("link", { name: /Introduction to Machine Learning/i });

        // Tab to the link and press Enter
        await user.tab();

        // Verify link is focused before pressing Enter
        expect(link).toHaveFocus();

        // Pressing Enter on a focused link would navigate (browser behavior)
        // We just verify the link is accessible via keyboard
        await user.keyboard("{Enter}");
      });
    });

    describe("Timestamp Link Navigation (FR-005)", () => {
      it("should navigate to video detail with timestamp parameter", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        // Look for timestamp link (the timestamp text should be clickable)
        const timestampLinks = screen.getAllByRole("link");
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute("href")?.includes("t=")
        );

        expect(timestampLink).toBeDefined();
        expect(timestampLink).toHaveAttribute("href", expect.stringContaining("t=154"));
      });

      it("should include correct seconds in timestamp link", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        // start_time is 154.5 seconds, should be floored to 154
        const timestampLinks = screen.getAllByRole("link");
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute("href")?.includes("t=")
        );

        expect(timestampLink).toHaveAttribute("href", "/videos/abc123def45?lang=en&seg=1&t=154");
      });

      it("should floor fractional seconds in timestamp parameter", () => {
        const segmentWithFractional: SearchResultSegment = {
          ...mockSegment,
          start_time: 89.7,
        };

        renderSearchResult(segmentWithFractional, mockQueryTerms);

        const timestampLinks = screen.getAllByRole("link");
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute("href")?.includes("t=")
        );

        expect(timestampLink).toHaveAttribute("href", expect.stringContaining("t=89"));
      });

      it("should handle zero timestamp in link", () => {
        const segmentAtStart: SearchResultSegment = {
          ...mockSegment,
          start_time: 0.0,
        };

        renderSearchResult(segmentAtStart, mockQueryTerms);

        const timestampLinks = screen.getAllByRole("link");
        const timestampLink = timestampLinks.find((link) =>
          link.getAttribute("href")?.includes("t=")
        );

        expect(timestampLink).toHaveAttribute("href", "/videos/abc123def45?lang=en&seg=1&t=0");
      });

      it("should be keyboard accessible via Tab", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        // Tab through all links - timestamp link should be focusable
        await user.tab(); // First link (video title)
        await user.tab(); // Second link (timestamp)

        const timestampLink = screen.getByRole("link", { name: /Jump to/ });

        expect(timestampLink).toHaveFocus();
      });

      it("should activate timestamp link with Enter key", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        // Tab to timestamp link
        await user.tab(); // Video title
        await user.tab(); // Timestamp link

        const timestampLink = screen.getByRole("link", { name: /Jump to/ });

        expect(timestampLink).toHaveFocus();

        // Press Enter to activate (would navigate in browser)
        await user.keyboard("{Enter}");
      });

      it("should have proper href attribute structure", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        const timestampLink = screen.getByRole("link", { name: /Jump to/ });

        const href = timestampLink?.getAttribute("href");
        expect(href).toMatch(/^\/videos\/[a-zA-Z0-9_-]+\?lang=[a-z-]+&seg=\d+&t=\d+$/);
      });

      it("should have accessible label for timestamp link", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        const timestampLink = screen.getByRole("link", { name: /Jump to/ });

        // Link should have accessible name from aria-label
        expect(timestampLink).toHaveAccessibleName();
        expect(timestampLink).toHaveAccessibleName(/Jump to.*in video/);
      });
    });

    describe("Link Accessibility", () => {
      it("should have all links keyboard navigable in order", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        const allLinks = screen.getAllByRole("link");

        // First tab should focus video title link
        await user.tab();
        expect(allLinks[0]).toHaveFocus();

        // Second tab should focus timestamp link
        await user.tab();
        expect(allLinks[1]).toHaveFocus();
      });

      it("should support keyboard navigation in reverse (Shift+Tab)", async () => {
        const { user } = renderSearchResult(mockSegment, mockQueryTerms);

        const allLinks = screen.getAllByRole("link");

        // Tab forward to second link
        await user.tab();
        await user.tab();
        expect(allLinks[1]).toHaveFocus();

        // Shift+Tab should go back to first link
        await user.tab({ shift: true });
        expect(allLinks[0]).toHaveFocus();
      });

      it("should have proper ARIA attributes on all links", () => {
        renderSearchResult(mockSegment, mockQueryTerms);

        const allLinks = screen.getAllByRole("link");

        allLinks.forEach((link) => {
          expect(link).toHaveAccessibleName();
          expect(link).toHaveAttribute("href");
        });
      });
    });
  });

  describe("Context Rendering", () => {
    it("should render context expander when context is available", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      // Context expander button should be visible
      expect(screen.getByRole("button", { name: /expand additional context/i })).toBeInTheDocument();
    });

    it("should show context_before when expander is clicked", async () => {
      const { user } = renderSearchResult(mockSegment, mockQueryTerms);

      const expandButton = screen.getByRole("button", { name: /expand additional context/i });
      await user.click(expandButton);

      expect(screen.getByText(/Welcome to this comprehensive tutorial/)).toBeInTheDocument();
    });

    it("should show context_after when expander is clicked", async () => {
      const { user } = renderSearchResult(mockSegment, mockQueryTerms);

      const expandButton = screen.getByRole("button", { name: /expand additional context/i });
      await user.click(expandButton);

      expect(screen.getByText(/Let us begin with supervised learning/)).toBeInTheDocument();
    });

    it("should handle null context_before gracefully", () => {
      const segmentWithoutContextBefore: SearchResultSegment = {
        ...mockSegment,
        context_before: null,
      };

      const { container } = renderSearchResult(segmentWithoutContextBefore, mockQueryTerms);

      // Should not crash and should still show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should still be visible (because context_after exists)
      expect(screen.getByRole("button", { name: /expand additional context/i })).toBeInTheDocument();
    });

    it("should handle null context_after gracefully", () => {
      const segmentWithoutContextAfter: SearchResultSegment = {
        ...mockSegment,
        context_after: null,
      };

      const { container } = renderSearchResult(segmentWithoutContextAfter, mockQueryTerms);

      // Should not crash and should still show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should still be visible (because context_before exists)
      expect(screen.getByRole("button", { name: /expand additional context/i })).toBeInTheDocument();
    });

    it("should handle both context_before and context_after being null", () => {
      const segmentWithoutContext: SearchResultSegment = {
        ...mockSegment,
        context_before: null,
        context_after: null,
      };

      const { container } = renderSearchResult(segmentWithoutContext, mockQueryTerms);

      // Should only show main text (with highlights)
      expect(container.textContent).toMatch(/In this video.*machine.*learning.*algorithms/);

      // Context expander should NOT be visible (no context available)
      expect(screen.queryByRole("button", { name: /expand additional context/i })).not.toBeInTheDocument();
    });
  });

  describe("Match Count Display", () => {
    it('should use singular "match" when count is 1', () => {
      const segmentWithOneMatch: SearchResultSegment = {
        ...mockSegment,
        match_count: 1,
      };

      renderSearchResult(segmentWithOneMatch, mockQueryTerms);

      // Match count badge only shows when > 1, so single match should not be visible
      expect(screen.queryByText("1 match")).not.toBeInTheDocument();
      expect(screen.queryByText("1 matches")).not.toBeInTheDocument();
    });

    it('should use plural "matches" when count is greater than 1', () => {
      const segmentWithMultipleMatches: SearchResultSegment = {
        ...mockSegment,
        match_count: 5,
      };

      renderSearchResult(segmentWithMultipleMatches, mockQueryTerms);

      expect(screen.getByText(/5 matches/i)).toBeInTheDocument();
    });

    it("should handle zero matches", () => {
      const segmentWithZeroMatches: SearchResultSegment = {
        ...mockSegment,
        match_count: 0,
      };

      renderSearchResult(segmentWithZeroMatches, mockQueryTerms);

      // Match count badge only shows when > 1, so zero should not be visible
      expect(screen.queryByText(/0 matches/i)).not.toBeInTheDocument();
    });
  });

  describe("Language Code Display", () => {
    it("should display language code badge", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      expect(screen.getByText("en")).toBeInTheDocument();
    });

    it("should display different language codes", () => {
      const spanishSegment: SearchResultSegment = {
        ...mockSegment,
        language_code: "es",
      };

      renderSearchResult(spanishSegment, mockQueryTerms);

      expect(screen.getByText("es")).toBeInTheDocument();
    });

    it("should display regional language codes", () => {
      const regionalSegment: SearchResultSegment = {
        ...mockSegment,
        language_code: "es-MX",
      };

      renderSearchResult(regionalSegment, mockQueryTerms);

      expect(screen.getByText("es-MX")).toBeInTheDocument();
    });
  });

  describe("Accessibility (ARIA Attributes)", () => {
    it("should have proper ARIA label for video link", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      const links = screen.getAllByRole("link");
      // All links should have accessible names
      links.forEach((link) => {
        expect(link).toHaveAccessibleName();
      });
    });

    it("should have semantic HTML structure", () => {
      const { container } = renderSearchResult(mockSegment, mockQueryTerms);

      // Should use article or similar semantic element
      const article = container.querySelector("article");
      expect(article).toBeInTheDocument();
    });

    it("should have accessible timestamp information", () => {
      renderSearchResult(mockSegment, mockQueryTerms);

      // Timestamp should be accessible to screen readers
      const timestamp = screen.getByText(/2:34.*3:12/);
      expect(timestamp).toBeInTheDocument();
    });
  });

  describe("Long Text Handling", () => {
    it("should handle very long segment text", () => {
      const segmentWithLongText: SearchResultSegment = {
        ...mockSegment,
        text: "A".repeat(1000) + " machine learning " + "B".repeat(1000),
      };

      renderSearchResult(segmentWithLongText, mockQueryTerms);

      // Should render without crashing
      expect(screen.getByText(/machine learning/i)).toBeInTheDocument();
    });

    it("should handle very long video titles", () => {
      const segmentWithLongTitle: SearchResultSegment = {
        ...mockSegment,
        video_title:
          "This is an extremely long video title that should be handled gracefully by the component without breaking the layout or causing accessibility issues",
      };

      renderSearchResult(segmentWithLongTitle, mockQueryTerms);

      expect(
        screen.getByText(/This is an extremely long video title/)
      ).toBeInTheDocument();
    });

    it("should handle very long channel names", () => {
      const segmentWithLongChannel: SearchResultSegment = {
        ...mockSegment,
        channel_title:
          "This is an extremely long channel name that should also be handled gracefully",
      };

      renderSearchResult(segmentWithLongChannel, mockQueryTerms);

      expect(
        screen.getByText(/This is an extremely long channel name/)
      ).toBeInTheDocument();
    });
  });

  describe("Special Characters", () => {
    it("should handle special characters in segment text", () => {
      const segmentWithSpecialChars: SearchResultSegment = {
        ...mockSegment,
        text: "Learn C++ & Python (2024) - $100 course! Machine learning basics.",
      };

      const { container } = renderSearchResult(segmentWithSpecialChars, mockQueryTerms);

      // Text is split by highlights, check for parts separately
      expect(container.textContent).toMatch(/Learn C\+\+ & Python/);
      expect(container.textContent).toMatch(/basics/);
    });

    it("should handle emoji in segment text", () => {
      const segmentWithEmoji: SearchResultSegment = {
        ...mockSegment,
        text: "🚀 Machine learning tutorial 🎓 Learn algorithms 💻",
      };

      const { container } = renderSearchResult(segmentWithEmoji, mockQueryTerms);

      // Text is split by highlights, check using container
      expect(container.textContent).toMatch(/🚀/);
      expect(container.textContent).toMatch(/🎓/);
      expect(container.textContent).toMatch(/💻/);
    });

    it("should handle multi-byte Unicode characters", () => {
      const segmentWithUnicode: SearchResultSegment = {
        ...mockSegment,
        text: "Machine learning 機械学習 apprentissage automatique",
      };

      const { container } = renderSearchResult(segmentWithUnicode, mockQueryTerms);

      // Text is split by highlights, check using container
      expect(container.textContent).toMatch(/機械学習/);
      expect(container.textContent).toMatch(/apprentissage automatique/);
    });
  });

  describe("Hover States", () => {
    it("should be hoverable", async () => {
      const { user } = renderSearchResult(mockSegment, mockQueryTerms);

      const links = screen.getAllByRole("link");
      const firstLink = links[0];
      if (!firstLink) {
        throw new Error("Expected at least one link to be rendered");
      }

      await user.hover(firstLink);

      // Visual hover state would be tested with visual regression
      expect(firstLink).toBeInTheDocument();
    });
  });

  describe("Multiple Query Terms", () => {
    it("should highlight all query terms", () => {
      const segmentWithMultipleTerms: SearchResultSegment = {
        ...mockSegment,
        text: "Python programming with TensorFlow for deep learning and neural networks.",
      };

      const { container } = renderSearchResult(segmentWithMultipleTerms, [
        "python",
        "learning",
        "neural",
      ]);

      const marks = container.querySelectorAll("mark");
      expect(marks.length).toBe(3);

      const highlightedTexts = Array.from(marks).map((mark) =>
        mark.textContent?.toLowerCase()
      );
      expect(highlightedTexts).toContain("python");
      expect(highlightedTexts).toContain("learning");
      expect(highlightedTexts).toContain("neural");
    });
  });
});
