/**
 * Tests for VideoSearchResult Component
 *
 * Tests rendering and behavior of video search results for both
 * TitleSearchResult and DescriptionSearchResult types.
 *
 * Tests coverage (from T019):
 * - Title rendering with highlighting
 * - Link to video detail page
 * - Channel title display
 * - Null channel handling
 * - Date formatting
 * - time element attributes
 * - Title search result (no snippet)
 * - Description search result (with snippet)
 * - Accessibility (article, heading, aria-hidden)
 * - Query terms passed to HighlightedText
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { VideoSearchResult } from "../../components/VideoSearchResult";
import type { TitleSearchResult, DescriptionSearchResult } from "../../types/search";

// Mock HighlightedText to verify props passed to it
vi.mock("../../components/HighlightedText", () => ({
  HighlightedText: ({ text, queryTerms }: { text: string; queryTerms: string[] }) => (
    <span data-testid="highlighted-text" data-text={text} data-query-terms={queryTerms.join(",")}>
      {text}
    </span>
  ),
}));

describe("VideoSearchResult", () => {
  describe("Title rendering", () => {
    it("should render the video title with HighlightedText component", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Machine Learning Tutorial",
        channel_title: "Tech Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["machine", "learning"]} />
        </MemoryRouter>
      );

      // Check that title text is present
      expect(screen.getByText("Machine Learning Tutorial")).toBeInTheDocument();

      // Verify HighlightedText was called with correct props
      const highlightedElements = screen.getAllByTestId("highlighted-text");
      const titleElement = highlightedElements.find(
        (el) => el.getAttribute("data-text") === "Machine Learning Tutorial"
      );
      expect(titleElement).toHaveAttribute("data-query-terms", "machine,learning");
    });

    it("should render title inside an h3 heading", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const heading = screen.getByRole("heading", { level: 3 });
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveTextContent("Test Video");
    });
  });

  describe("Link to video", () => {
    it("should link title to /videos/{video_id}", () => {
      const result: TitleSearchResult = {
        video_id: "xyz789",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const link = screen.getByRole("link", { name: /test video/i });
      expect(link).toHaveAttribute("href", "/videos/xyz789");
    });

    it("should use video_id from result for link href", () => {
      const result: TitleSearchResult = {
        video_id: "unique-id-123",
        title: "Another Video",
        channel_title: "Another Channel",
        upload_date: "2024-02-20T14:00:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("href", "/videos/unique-id-123");
    });
  });

  describe("Channel title display", () => {
    it("should display channel name when channel_title is present", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Amazing Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      expect(screen.getByText("Amazing Channel")).toBeInTheDocument();
    });

    it("should display dot separator when channel_title is present", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Find the dot separator
      const separator = container.querySelector('span[aria-hidden="true"]');
      expect(separator).toBeInTheDocument();
      expect(separator).toHaveTextContent("·");
    });
  });

  describe("Null channel handling (FR edge case)", () => {
    it("should not display channel name when channel_title is null", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: null,
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Only the date should be visible in the metadata row
      // No channel name should appear
      const metadataDiv = screen.getByText(/Jan 15, 2024/i).closest("div");
      expect(metadataDiv).toBeInTheDocument();

      // Should only have 1 child: the time element (no channel span, no separator)
      expect(metadataDiv?.children.length).toBe(1);
    });

    it("should not display dot separator when channel_title is null", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: null,
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // No separator should be present
      const separator = container.querySelector('span[aria-hidden="true"]');
      expect(separator).not.toBeInTheDocument();
    });
  });

  describe("Date formatting", () => {
    it("should format upload_date as 'Jan 15, 2024' format (en-US short month)", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      expect(screen.getByText("Jan 15, 2024")).toBeInTheDocument();
    });

    it("should format different dates correctly", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2023-12-25T12:00:00Z",
        availability_status: "available", // Use midday to avoid timezone edge cases
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Check that date is formatted correctly (allow for timezone variations)
      expect(screen.getByText(/Dec (24|25), 2023/)).toBeInTheDocument();
    });

    it("should format dates with various months correctly", () => {
      const testCases = [
        { date: "2024-02-14T12:00:00Z", expected: "Feb 14, 2024" },
        { date: "2024-07-04T12:00:00Z", expected: "Jul 4, 2024" },
        { date: "2024-11-30T12:00:00Z", expected: "Nov 30, 2024" },
      ];

      testCases.forEach(({ date, expected }) => {
        const result: TitleSearchResult = {
          video_id: "abc123",
          title: "Test Video",
          channel_title: "Test Channel",
          upload_date: date,
          availability_status: "available",
        };

        const { unmount } = render(
          <MemoryRouter>
            <VideoSearchResult result={result} queryTerms={[]} />
          </MemoryRouter>
        );

        expect(screen.getByText(expected)).toBeInTheDocument();
        unmount();
      });
    });
  });

  describe("time element", () => {
    it("should render time element with correct dateTime attribute", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const timeElement = screen.getByText("Jan 15, 2024");
      expect(timeElement.tagName).toBe("TIME");
      expect(timeElement).toHaveAttribute("dateTime", "2024-01-15T10:30:00Z");
    });

    it("should preserve ISO 8601 format in dateTime attribute", () => {
      const isoDate = "2023-06-20T14:25:33Z";
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: isoDate,
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const timeElement = screen.getByText("Jun 20, 2023");
      expect(timeElement).toHaveAttribute("dateTime", isoDate);
    });
  });

  describe("Title search result (no snippet)", () => {
    it("should NOT render snippet paragraph for TitleSearchResult", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["test"]} />
        </MemoryRouter>
      );

      // Should not have a paragraph element (snippet is rendered in <p>)
      const paragraphs = container.querySelectorAll("p");
      expect(paragraphs.length).toBe(0);
    });

    it("should only render title and metadata for TitleSearchResult", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Machine Learning Basics",
        channel_title: "AI Academy",
        upload_date: "2024-03-10T08:00:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["machine"]} />
        </MemoryRouter>
      );

      // Should have title
      expect(screen.getByText("Machine Learning Basics")).toBeInTheDocument();

      // Should have channel
      expect(screen.getByText("AI Academy")).toBeInTheDocument();

      // Should have date
      expect(screen.getByText("Mar 10, 2024")).toBeInTheDocument();

      // Should NOT have any paragraph (snippet)
      expect(screen.queryByRole("paragraph")).not.toBeInTheDocument();
    });
  });

  describe("Description search result (with snippet)", () => {
    it("should render snippet with highlighting for DescriptionSearchResult", () => {
      const result: DescriptionSearchResult = {
        video_id: "abc123",
        title: "Deep Learning Tutorial",
        channel_title: "ML University",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
        snippet: "This video covers neural networks and deep learning algorithms...",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["neural", "networks"]} />
        </MemoryRouter>
      );

      // Should render the snippet text
      expect(
        screen.getByText("This video covers neural networks and deep learning algorithms...")
      ).toBeInTheDocument();

      // Verify HighlightedText was called for snippet with correct query terms
      const highlightedElements = screen.getAllByTestId("highlighted-text");
      const snippetElement = highlightedElements.find((el) =>
        el.getAttribute("data-text")?.includes("neural networks")
      );
      expect(snippetElement).toHaveAttribute("data-query-terms", "neural,networks");
    });

    it("should render snippet inside a paragraph element", () => {
      const result: DescriptionSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
        snippet: "This is a test snippet with important information.",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const paragraph = container.querySelector("p");
      expect(paragraph).toBeInTheDocument();
      expect(paragraph).toHaveTextContent(
        "This is a test snippet with important information."
      );
    });

    it("should render both title and snippet for DescriptionSearchResult", () => {
      const result: DescriptionSearchResult = {
        video_id: "abc123",
        title: "Python Programming",
        channel_title: "Code Academy",
        upload_date: "2024-02-20T12:00:00Z",
        availability_status: "available",
        snippet: "Learn Python fundamentals in this comprehensive tutorial...",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["python"]} />
        </MemoryRouter>
      );

      // Should have title
      expect(screen.getByText("Python Programming")).toBeInTheDocument();

      // Should have snippet
      expect(
        screen.getByText("Learn Python fundamentals in this comprehensive tutorial...")
      ).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should render within an article element", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const article = container.querySelector("article");
      expect(article).toBeInTheDocument();
    });

    it("should have proper heading structure (h3)", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Accessible Video Title",
        channel_title: "Accessible Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const heading = screen.getByRole("heading", { level: 3 });
      expect(heading).toHaveTextContent("Accessible Video Title");
    });

    it("should mark dot separator as aria-hidden", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const separator = container.querySelector('span[aria-hidden="true"]');
      expect(separator).toBeInTheDocument();
      expect(separator).toHaveAttribute("aria-hidden", "true");
      expect(separator).toHaveTextContent("·");
    });

    it("should not have aria-hidden on meaningful content", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Channel name should not be aria-hidden
      const channelSpan = screen.getByText("Test Channel");
      expect(channelSpan).not.toHaveAttribute("aria-hidden");

      // Date should not be aria-hidden
      const dateElement = screen.getByText("Jan 15, 2024");
      expect(dateElement).not.toHaveAttribute("aria-hidden");
    });
  });

  describe("Query terms passed to HighlightedText", () => {
    it("should pass query terms to HighlightedText for title", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Machine Learning Fundamentals",
        channel_title: "Tech Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["machine", "learning", "ai"]} />
        </MemoryRouter>
      );

      const highlightedElements = screen.getAllByTestId("highlighted-text");
      const titleElement = highlightedElements.find(
        (el) => el.getAttribute("data-text") === "Machine Learning Fundamentals"
      );
      expect(titleElement).toHaveAttribute("data-query-terms", "machine,learning,ai");
    });

    it("should pass query terms to HighlightedText for snippet", () => {
      const result: DescriptionSearchResult = {
        video_id: "abc123",
        title: "AI Course",
        channel_title: "Tech Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
        snippet: "Comprehensive AI and machine learning tutorial",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["ai", "machine"]} />
        </MemoryRouter>
      );

      const highlightedElements = screen.getAllByTestId("highlighted-text");
      const snippetElement = highlightedElements.find((el) =>
        el.getAttribute("data-text")?.includes("Comprehensive AI")
      );
      expect(snippetElement).toHaveAttribute("data-query-terms", "ai,machine");
    });

    it("should handle empty query terms array", () => {
      const result: TitleSearchResult = {
        video_id: "abc123",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Should still render, just without highlighting
      expect(screen.getByText("Test Video")).toBeInTheDocument();

      const highlightedElement = screen.getByTestId("highlighted-text");
      expect(highlightedElement).toHaveAttribute("data-query-terms", "");
    });

    it("should pass same query terms to both title and snippet", () => {
      const result: DescriptionSearchResult = {
        video_id: "abc123",
        title: "Python Tutorial",
        channel_title: "Code School",
        upload_date: "2024-01-15T10:30:00Z",
        availability_status: "available",
        snippet: "Learn Python programming from scratch",
      };

      const queryTerms = ["python", "programming"];

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={queryTerms} />
        </MemoryRouter>
      );

      const highlightedElements = screen.getAllByTestId("highlighted-text");

      // Both title and snippet should receive the same query terms
      highlightedElements.forEach((element) => {
        expect(element).toHaveAttribute("data-query-terms", "python,programming");
      });
    });
  });

  describe("Description snippet rendering (T024)", () => {
    it("should render snippet with ellipsis when present in description result", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid123",
        title: "Advanced React Patterns",
        channel_title: "React Academy",
        upload_date: "2024-03-01T10:00:00Z",
        availability_status: "available",
        snippet: "...this is a test snippet with leading ellipsis...",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["test"]} />
        </MemoryRouter>
      );

      // Ellipsis should be rendered as part of the snippet text
      expect(
        screen.getByText("...this is a test snippet with leading ellipsis...")
      ).toBeInTheDocument();
    });

    it("should highlight query terms within snippet using HighlightedText", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid456",
        title: "TypeScript Advanced Techniques",
        channel_title: "Code Masters",
        upload_date: "2024-03-05T14:30:00Z",
        availability_status: "available",
        snippet: "Learn advanced TypeScript patterns and best practices for large applications",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["typescript", "patterns"]} />
        </MemoryRouter>
      );

      const highlightedElements = screen.getAllByTestId("highlighted-text");
      const snippetElement = highlightedElements.find((el) =>
        el.getAttribute("data-text")?.includes("advanced TypeScript patterns")
      );

      expect(snippetElement).toBeInTheDocument();
      expect(snippetElement).toHaveAttribute("data-query-terms", "typescript,patterns");
    });

    it("should NOT render snippet paragraph for title-only search results", () => {
      const titleResult: TitleSearchResult = {
        video_id: "vid789",
        title: "JavaScript Basics",
        channel_title: "Web Dev Academy",
        upload_date: "2024-03-10T09:00:00Z",
        availability_status: "available",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={titleResult} queryTerms={["javascript"]} />
        </MemoryRouter>
      );

      // Should not have any <p> element when snippet is absent
      const paragraphs = container.querySelectorAll("p");
      expect(paragraphs.length).toBe(0);

      // Should still render title and metadata
      expect(screen.getByText("JavaScript Basics")).toBeInTheDocument();
      expect(screen.getByText("Web Dev Academy")).toBeInTheDocument();
    });

    it("should render snippet with special characters and HTML entities correctly", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid999",
        title: "Special Characters in Code",
        channel_title: "Programming Tips",
        upload_date: "2024-03-15T11:00:00Z",
        availability_status: "available",
        snippet: 'Learn about <special> & "quoted" characters in programming\'s syntax',
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["special"]} />
        </MemoryRouter>
      );

      // Special characters should render correctly without HTML escaping issues
      expect(
        screen.getByText('Learn about <special> & "quoted" characters in programming\'s syntax')
      ).toBeInTheDocument();
    });

    it("should render snippet with ellipsis at both start and end", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid555",
        title: "Database Optimization",
        channel_title: "DB Masters",
        upload_date: "2024-03-20T16:00:00Z",
        availability_status: "available",
        snippet: "...middle portion of description with key information...",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["database"]} />
        </MemoryRouter>
      );

      const snippetText = screen.getByText(
        "...middle portion of description with key information..."
      );
      expect(snippetText).toBeInTheDocument();

      // Verify it's in a paragraph element
      expect(snippetText.closest("p")).toBeInTheDocument();
    });

    it("should render snippet with proper styling classes", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid666",
        title: "CSS Grid Mastery",
        channel_title: "Design School",
        upload_date: "2024-03-25T12:00:00Z",
        availability_status: "available",
        snippet: "Master CSS Grid layout with practical examples",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["css"]} />
        </MemoryRouter>
      );

      const paragraph = container.querySelector("p");
      expect(paragraph).toBeInTheDocument();

      // Check for expected Tailwind classes
      expect(paragraph).toHaveClass("mt-2");
      expect(paragraph).toHaveClass("text-sm");
      expect(paragraph).toHaveClass("text-gray-600");
      expect(paragraph).toHaveClass("dark:text-gray-300");
      expect(paragraph).toHaveClass("leading-relaxed");
    });

    it("should render empty snippet when snippet field is empty string", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid777",
        title: "Empty Description Video",
        channel_title: "Test Channel",
        upload_date: "2024-03-30T10:00:00Z",
        availability_status: "available",
        snippet: "",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={["test"]} />
        </MemoryRouter>
      );

      // Paragraph should still render even with empty snippet
      const paragraph = container.querySelector("p");
      expect(paragraph).toBeInTheDocument();
      expect(paragraph?.textContent).toBe("");
    });

    it("should render snippet with only whitespace correctly", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid888",
        title: "Whitespace Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-04-01T10:00:00Z",
        availability_status: "available",
        snippet: "   ",
      };

      const { container } = render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      const paragraph = container.querySelector("p");
      expect(paragraph).toBeInTheDocument();
      // Whitespace should be preserved as-is
      expect(paragraph?.textContent).toBe("   ");
    });

    it("should preserve line breaks and formatting in snippet", () => {
      const result: DescriptionSearchResult = {
        video_id: "vid101",
        title: "Multi-line Description",
        channel_title: "Format Test",
        upload_date: "2024-04-05T10:00:00Z",
        availability_status: "available",
        snippet: "First line\nSecond line\nThird line",
      };

      render(
        <MemoryRouter>
          <VideoSearchResult result={result} queryTerms={[]} />
        </MemoryRouter>
      );

      // Text content should include the newlines
      const snippetText = screen.getByText(/First line.*Second line.*Third line/s);
      expect(snippetText).toBeInTheDocument();
    });
  });
});
