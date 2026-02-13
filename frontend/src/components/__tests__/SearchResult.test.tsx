/**
 * Tests for SearchResult Component - Deep Link URLs
 *
 * Tests coverage (T009):
 * - Title link includes all deep link params (lang, seg, t)
 * - Timestamp link includes all deep link params
 * - Deep link params use correct values from SearchResultSegment
 * - Time parameter (t) correctly floors decimal start_time values
 * - Both links navigate to the same URL pattern
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
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
    ...overrides,
  };
}

/**
 * Helper to render SearchResult with MemoryRouter.
 */
function renderSearchResult(segment: SearchResultSegment, queryTerms: string[] = ["test"]) {
  return render(
    <MemoryRouter>
      <SearchResult segment={segment} queryTerms={queryTerms} />
    </MemoryRouter>
  );
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
