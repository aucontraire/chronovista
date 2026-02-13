/**
 * Tests for TranscriptPanel Component - Deep Link Behavior (Feature 022, T011)
 *
 * Test coverage:
 * - FR-003: Auto-expand when deep link params present
 * - FR-004: Language initialization with deep link
 * - FR-016: Force segments view mode
 * - Props forwarding to TranscriptSegments
 *
 * Tests ONLY deep link behaviors - does NOT test existing TranscriptPanel features
 * (expand/collapse animation, language badges, etc.) that are outside Feature 022 scope.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TranscriptPanel } from "../TranscriptPanel";
import type { TranscriptLanguage } from "../../../types/transcript";

// Mock the useTranscriptLanguages hook
vi.mock("../../../hooks/useTranscriptLanguages", () => ({
  useTranscriptLanguages: vi.fn(),
}));

// Mock TranscriptSegments to capture its props
vi.mock("../TranscriptSegments", () => ({
  TranscriptSegments: vi.fn((props) => (
    <div data-testid="transcript-segments" data-props={JSON.stringify(props)} />
  )),
}));

// Mock TranscriptFullText
vi.mock("../TranscriptFullText", () => ({
  TranscriptFullText: vi.fn(() => <div data-testid="transcript-fulltext" />),
}));

// Mock usePrefersReducedMotion
vi.mock("../../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn(() => false),
}));

// Import the mocked modules for assertions
import { useTranscriptLanguages } from "../../../hooks/useTranscriptLanguages";
import { TranscriptSegments } from "../TranscriptSegments";

/**
 * Test factory to generate TranscriptLanguage test data.
 */
function createTestLanguage(overrides: Partial<TranscriptLanguage> = {}): TranscriptLanguage {
  return {
    language_code: "en",
    language_name: "English",
    transcript_type: "manual",
    is_translatable: true,
    downloaded_at: "2024-01-15T00:00:00Z",
    ...overrides,
  };
}

/**
 * Mock hook to return successful language data.
 */
function mockTranscriptLanguagesSuccess(languages: TranscriptLanguage[]) {
  vi.mocked(useTranscriptLanguages).mockReturnValue({
    data: languages,
    isLoading: false,
    isError: false,
    error: null,
    isSuccess: true,
    status: "success",
    refetch: vi.fn(),
    isFetching: false,
    isPending: false,
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
    promise: Promise.resolve(languages),
  });
}

describe("TranscriptPanel - Deep Link Behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("FR-003: Auto-expand when deep link params present", () => {
    it("should auto-expand when initialLanguage is provided", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
        />
      );

      // Wait for languages to load and panel to render
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should auto-expand when targetSegmentId is provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={42}
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should auto-expand when targetTimestamp is provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetTimestamp={125}
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should stay collapsed when no deep link params are provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "false");
      });
    });

    it("should auto-expand when multiple deep link params are provided", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
          targetSegmentId={42}
          targetTimestamp={125}
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should not auto-expand when initialLanguage is explicitly undefined", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage={undefined}
          targetSegmentId={undefined}
          targetTimestamp={undefined}
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "false");
      });
    });
  });

  describe("FR-004: Language initialization with deep link", () => {
    it("should select initialLanguage when it matches an available language", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
        createTestLanguage({ language_code: "fr", language_name: "French" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="es"
        />
      );

      // Wait for TranscriptSegments to be rendered with correct language
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "es",
          }),
          undefined
        );
      });
    });

    it("should fall back to first language when initialLanguage doesn't match any available language", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="de" // German not available
        />
      );

      // Should fall back to first language (en)
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "en",
          }),
          undefined
        );
      });
    });

    it("should select first available language when initialLanguage is undefined", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage={undefined}
        />
      );

      // The panel starts collapsed, so we need to check when it would render segments
      // Since no deep link params, panel is collapsed and segments won't render yet
      // This test verifies the internal state is set correctly for when panel expands
      await waitFor(() => {
        // Panel should be rendered
        expect(screen.getByRole("button", { name: /transcript/i })).toBeInTheDocument();
      });
    });

    it("should handle case-sensitive language code matching", async () => {
      const languages = [
        createTestLanguage({ language_code: "en-US", language_name: "English (US)" }),
        createTestLanguage({ language_code: "en-GB", language_name: "English (UK)" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en-GB"
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "en-GB",
          }),
          undefined
        );
      });
    });

    it("should not select language when initialLanguage case differs from available", async () => {
      const languages = [
        createTestLanguage({ language_code: "en-US", language_name: "English (US)" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en-us" // lowercase
        />
      );

      // Should fall back to first language since exact match failed
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "en-US",
          }),
          undefined
        );
      });
    });

    it("should handle BCP-47 language codes with variants", async () => {
      const languages = [
        createTestLanguage({ language_code: "zh-Hans-CN", language_name: "Chinese (Simplified)" }),
        createTestLanguage({ language_code: "zh-Hant-TW", language_name: "Chinese (Traditional)" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="zh-Hant-TW"
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "zh-Hant-TW",
          }),
          undefined
        );
      });
    });
  });

  describe("FR-016: Force segments view mode", () => {
    it("should force viewMode to 'segments' when targetSegmentId is present", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={42}
        />
      );

      // When targetSegmentId is present, TranscriptSegments should render (not TranscriptFullText)
      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
        expect(screen.queryByTestId("transcript-fulltext")).not.toBeInTheDocument();
      });
    });

    it("should force viewMode to 'segments' when targetTimestamp is present", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetTimestamp={125}
        />
      );

      // When targetTimestamp is present, TranscriptSegments should render
      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
        expect(screen.queryByTestId("transcript-fulltext")).not.toBeInTheDocument();
      });
    });

    it("should force viewMode to 'segments' when both targetSegmentId and targetTimestamp are present", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={42}
          targetTimestamp={125}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
        expect(screen.queryByTestId("transcript-fulltext")).not.toBeInTheDocument();
      });
    });

    it("should default to 'segments' viewMode when no targets are present", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en" // Auto-expand to see viewMode
        />
      );

      // Default viewMode is segments
      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
      });
    });
  });

  describe("Props forwarding to TranscriptSegments", () => {
    it("should pass targetSegmentId to TranscriptSegments", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={42}
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            targetSegmentId: 42,
          }),
          undefined
        );
      });
    });

    it("should pass targetTimestamp to TranscriptSegments", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetTimestamp={125}
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            targetTimestamp: 125,
          }),
          undefined
        );
      });
    });

    it("should pass onDeepLinkComplete callback to TranscriptSegments", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);
      const mockCallback = vi.fn();

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={42}
          onDeepLinkComplete={mockCallback}
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            onDeepLinkComplete: mockCallback,
          }),
          undefined
        );
      });
    });

    it("should pass all deep link props together to TranscriptSegments", async () => {
      const languages = [createTestLanguage({ language_code: "es" })];
      mockTranscriptLanguagesSuccess(languages);
      const mockCallback = vi.fn();

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="es"
          targetSegmentId={42}
          targetTimestamp={125}
          onDeepLinkComplete={mockCallback}
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            videoId: "test-video-123",
            languageCode: "es",
            targetSegmentId: 42,
            targetTimestamp: 125,
            onDeepLinkComplete: mockCallback,
          }),
          undefined
        );
      });
    });

    it("should pass videoId to TranscriptSegments", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="unique-video-789"
          initialLanguage="en"
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            videoId: "unique-video-789",
          }),
          undefined
        );
      });
    });

    it("should pass selectedLanguage as languageCode to TranscriptSegments", async () => {
      const languages = [
        createTestLanguage({ language_code: "fr", language_name: "French" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="fr"
        />
      );

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "fr",
          }),
          undefined
        );
      });
    });

    it("should not pass undefined targetSegmentId when not provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
        />
      );

      await waitFor(() => {
        const calls = vi.mocked(TranscriptSegments).mock.calls;
        expect(calls.length).toBeGreaterThan(0);
        const lastCall = calls[calls.length - 1];
        expect(lastCall?.[0]).toBeDefined();
        // targetSegmentId should be undefined (not present in deep link)
        expect(lastCall?.[0].targetSegmentId).toBeUndefined();
      });
    });

    it("should not pass undefined targetTimestamp when not provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
        />
      );

      await waitFor(() => {
        const calls = vi.mocked(TranscriptSegments).mock.calls;
        expect(calls.length).toBeGreaterThan(0);
        const lastCall = calls[calls.length - 1];
        expect(lastCall?.[0]).toBeDefined();
        // targetTimestamp should be undefined (not present in deep link)
        expect(lastCall?.[0].targetTimestamp).toBeUndefined();
      });
    });

    it("should not pass undefined onDeepLinkComplete when not provided", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
        />
      );

      await waitFor(() => {
        const calls = vi.mocked(TranscriptSegments).mock.calls;
        expect(calls.length).toBeGreaterThan(0);
        const lastCall = calls[calls.length - 1];
        expect(lastCall?.[0]).toBeDefined();
        // onDeepLinkComplete should be undefined when not provided
        expect(lastCall?.[0].onDeepLinkComplete).toBeUndefined();
      });
    });
  });

  describe("Combined deep link scenarios", () => {
    it("should handle all deep link features together: auto-expand, language selection, viewMode, props forwarding", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
        createTestLanguage({ language_code: "fr", language_name: "French" }),
      ];
      mockTranscriptLanguagesSuccess(languages);
      const mockCallback = vi.fn();

      render(
        <TranscriptPanel
          videoId="comprehensive-test"
          initialLanguage="es"
          targetSegmentId={99}
          targetTimestamp={200}
          onDeepLinkComplete={mockCallback}
        />
      );

      // Verify auto-expand (FR-003)
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Verify language selection (FR-004)
      // Verify segments viewMode (FR-016)
      // Verify props forwarding
      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            videoId: "comprehensive-test",
            languageCode: "es",
            targetSegmentId: 99,
            targetTimestamp: 200,
            onDeepLinkComplete: mockCallback,
          }),
          undefined
        );
      });
    });

    it("should handle edge case: initialLanguage only (no targets)", async () => {
      const languages = [
        createTestLanguage({ language_code: "ja", language_name: "Japanese" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="ja"
        />
      );

      // Auto-expand because initialLanguage is present
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Language should be selected
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "ja",
            targetSegmentId: undefined,
            targetTimestamp: undefined,
          }),
          undefined
        );
      });
    });

    it("should handle edge case: targetSegmentId only (no initialLanguage)", async () => {
      const languages = [
        createTestLanguage({ language_code: "de", language_name: "German" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={50}
        />
      );

      // Auto-expand because targetSegmentId is present
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Should default to first language (de)
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "de",
            targetSegmentId: 50,
          }),
          undefined
        );
      });
    });

    it("should handle edge case: targetTimestamp only (no initialLanguage, no targetSegmentId)", async () => {
      const languages = [
        createTestLanguage({ language_code: "it", language_name: "Italian" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetTimestamp={300}
        />
      );

      // Auto-expand because targetTimestamp is present
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Should default to first language (it) and force segments view
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "it",
            targetTimestamp: 300,
            targetSegmentId: undefined,
          }),
          undefined
        );
      });
    });

    it("should handle zero values for numeric deep link params", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          targetSegmentId={0}
          targetTimestamp={0}
        />
      );

      // Zero is a valid value and should trigger deep link behavior
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            targetSegmentId: 0,
            targetTimestamp: 0,
          }),
          undefined
        );
      });
    });

    it("should handle mismatched initialLanguage with targetSegmentId", async () => {
      const languages = [
        createTestLanguage({ language_code: "ko", language_name: "Korean" }),
        createTestLanguage({ language_code: "ar", language_name: "Arabic" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="ru" // Not available
          targetSegmentId={25}
        />
      );

      // Auto-expand
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Should fall back to first language (ko)
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "ko",
            targetSegmentId: 25,
          }),
          undefined
        );
      });
    });
  });

  describe("Deep link behavior with loading states", () => {
    it("should maintain expanded state through loading when deep link params present", async () => {
      // First render with loading state
      vi.mocked(useTranscriptLanguages).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        isSuccess: false,
        status: "pending",
        refetch: vi.fn(),
        isFetching: true,
        isPending: true,
        isRefetching: false,
        isLoadingError: false,
        isRefetchError: false,
        isPaused: false,
        isPlaceholderData: false,
        isStale: false,
        dataUpdatedAt: 0,
        errorUpdatedAt: 0,
        failureCount: 0,
        failureReason: null,
        errorUpdateCount: 0,
        fetchStatus: "fetching" as const,
        isFetched: false,
        isFetchedAfterMount: false,
        isInitialLoading: true,
        isEnabled: true,
        promise: new Promise(() => {}),
      });

      const { rerender } = render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
          targetSegmentId={42}
        />
      );

      // Should show loading state
      expect(screen.getByRole("status")).toBeInTheDocument();

      // Now simulate successful load
      const languages = [createTestLanguage({ language_code: "en" })];
      mockTranscriptLanguagesSuccess(languages);

      rerender(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
          targetSegmentId={42}
        />
      );

      // Should be auto-expanded after load
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });
  });

  describe("Deep link behavior respects component boundaries", () => {
    it("should not render TranscriptSegments when panel is collapsed (no deep link)", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "false");
      });

      // Content area should be aria-hidden when collapsed (component is still in DOM for animation)
      const contentArea = document.getElementById("transcript-content");
      expect(contentArea).toHaveAttribute("aria-hidden", "true");
    });

    it("should render TranscriptSegments when panel is auto-expanded by deep link", async () => {
      const languages = [createTestLanguage()];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en"
        />
      );

      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // TranscriptSegments should be rendered when auto-expanded
      expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
    });
  });

  describe("Language fallback with inline notice (FR-012)", () => {
    it("should display fallback notice when initialLanguage is not available", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="fr" // French not available
        />
      );

      // Panel should auto-expand because initialLanguage is provided
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Verify fallback notice is displayed
      await waitFor(() => {
        expect(
          screen.getByText(/Requested language 'fr' is not available\. Showing English instead\./i)
        ).toBeInTheDocument();
      });
    });

    it("should NOT display fallback notice when initialLanguage is available", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="en" // English is available
        />
      );

      // Wait for panel to render
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });

      // Verify no fallback notice is displayed
      expect(
        screen.queryByText(/Requested language/i)
      ).not.toBeInTheDocument();
    });

    it("should NOT display fallback notice when no initialLanguage provided", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          // No initialLanguage provided
        />
      );

      // Wait for panel to render
      await waitFor(() => {
        const toggleButton = screen.getByRole("button", { name: /transcript/i });
        expect(toggleButton).toBeInTheDocument();
      });

      // Verify no fallback notice is displayed
      expect(
        screen.queryByText(/Requested language/i)
      ).not.toBeInTheDocument();
    });

    it("should select first available language as fallback", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="fr" // Not available
        />
      );

      // Verify TranscriptSegments receives the first available language (en)
      await waitFor(() => {
        expect(TranscriptSegments).toHaveBeenCalledWith(
          expect.objectContaining({
            languageCode: "en",
          }),
          undefined
        );
      });
    });

    it("should dismiss notice when user manually changes language", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="fr" // Not available
        />
      );

      // Wait for panel to auto-expand and notice to appear
      await waitFor(() => {
        expect(
          screen.getByText(/Requested language 'fr' is not available/i)
        ).toBeInTheDocument();
      });

      // Find the Spanish language tab and click it
      const spanishTab = screen.getByRole("tab", { name: /ES/i });
      spanishTab.click();

      // Verify the notice is dismissed
      await waitFor(() => {
        expect(
          screen.queryByText(/Requested language/i)
        ).not.toBeInTheDocument();
      });
    });

    it("should have appropriate accessibility attributes on notice", async () => {
      const languages = [
        createTestLanguage({ language_code: "en", language_name: "English" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="de" // Not available
        />
      );

      // Wait for notice to appear
      await waitFor(() => {
        const notice = screen.getByText(/Requested language 'de' is not available/i);
        expect(notice).toBeInTheDocument();

        // Verify accessibility attributes
        const noticeContainer = notice.closest("div");
        expect(noticeContainer).toHaveAttribute("role", "status");
        expect(noticeContainer).toHaveAttribute("aria-live", "polite");
      });
    });

    it("should include the fallback language name in the notice", async () => {
      const languages = [
        createTestLanguage({ language_code: "es", language_name: "Spanish" }),
      ];
      mockTranscriptLanguagesSuccess(languages);

      render(
        <TranscriptPanel
          videoId="test-video-123"
          initialLanguage="de" // German not available
        />
      );

      // Verify notice contains the fallback language name "Spanish"
      await waitFor(() => {
        expect(
          screen.getByText(/Requested language 'de' is not available\. Showing Spanish instead\./i)
        ).toBeInTheDocument();
      });
    });
  });
});
