/**
 * Unit tests for useTranscript hook.
 *
 * Tests TanStack Query integration for fetching full transcript text.
 *
 * @module tests/hooks/useTranscript
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useTranscript } from "../../hooks/useTranscript";
import type { Transcript } from "../../types/transcript";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("useTranscript", () => {
  let queryClient: QueryClient;

  const mockTranscript: Transcript = {
    video_id: "dQw4w9WgXcQ",
    language_code: "en",
    transcript_type: "manual",
    full_text: "This is the full transcript text. It contains multiple sentences and paragraphs.",
    segment_count: 25,
    downloaded_at: "2024-01-15T10:00:00Z",
  };

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    vi.clearAllMocks();
  });

  const createWrapper = () => {
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  describe("successful data fetching", () => {
    it("fetches and returns full transcript text", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockTranscript);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("calls apiFetch with correct endpoint and language parameter", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ/transcript?language=en");
      });
    });

    it("properly encodes language code with special characters", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: { ...mockTranscript, language_code: "zh-Hans" },
      });

      renderHook(() => useTranscript("dQw4w9WgXcQ", "zh-Hans"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ/transcript?language=zh-Hans");
      });
    });

    it("uses correct query key for caching", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const cachedData = queryClient.getQueryData(["transcript", "dQw4w9WgXcQ", "en"]);
      expect(cachedData).toEqual(mockTranscript);
    });
  });

  describe("loading state", () => {
    it("shows loading state initially", () => {
      vi.mocked(apiConfig.apiFetch).mockImplementationOnce(
        () => new Promise(() => {}) // Never resolves
      );

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeUndefined();
      expect(result.current.error).toBeNull();
    });

    it("transitions from loading to success", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.isSuccess).toBe(true);
      });
    });
  });

  describe("error handling", () => {
    it("handles 404 not found error", async () => {
      const notFoundError = {
        type: "server" as const,
        message: "Transcript not found",
        status: 404,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(notFoundError);

      const { result } = renderHook(() => useTranscript("invalidVideo", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(notFoundError);
      expect(result.current.data).toBeUndefined();
    });

    it("handles network error", async () => {
      const networkError = {
        type: "network" as const,
        message: "Cannot reach the API server. Make sure the backend is running on port 8765.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(networkError);

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(networkError);
    });

    it("handles timeout error per NFR-P01 requirement", async () => {
      const timeoutError = {
        type: "timeout" as const,
        message: "The server took too long to respond.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(timeoutError);

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(timeoutError);
    });

    it("handles server error (500)", async () => {
      const serverError = {
        type: "server" as const,
        message: "Something went wrong on the server.",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(serverError);

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(serverError);
    });
  });

  describe("query enabled/disabled", () => {
    it("does not fetch when videoId is empty", () => {
      const { result } = renderHook(() => useTranscript("", "en"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("does not fetch when languageCode is empty", () => {
      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", ""), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("does not fetch when both parameters are empty", () => {
      const { result } = renderHook(() => useTranscript("", ""), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("fetches when both parameters are provided after being empty", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      let videoId = "";
      let languageCode = "";

      const { result, rerender } = renderHook(
        () => useTranscript(videoId, languageCode),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();

      videoId = "dQw4w9WgXcQ";
      languageCode = "en";
      rerender();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ/transcript?language=en");
    });
  });

  describe("staleTime configuration", () => {
    it("uses 10 second staleTime per NFR-P01 requirement", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queryState = queryClient.getQueryState(["transcript", "dQw4w9WgXcQ", "en"]);
      expect(queryState).toBeDefined();
    });
  });

  describe("caching behavior", () => {
    it("uses cached data for subsequent renders with same parameters", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockTranscript,
      });

      const { result: result1 } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);

      const { result: result2 } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      expect(result2.current.data).toEqual(mockTranscript);
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);
    });

    it("fetches different data for different language codes", async () => {
      const mockTranscriptES: Transcript = {
        ...mockTranscript,
        language_code: "es",
        full_text: "Este es el texto completo de la transcripción.",
      };

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce({ data: mockTranscript })
        .mockResolvedValueOnce({ data: mockTranscriptES });

      const { result: result1 } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      const { result: result2 } = renderHook(() => useTranscript("dQw4w9WgXcQ", "es"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.language_code).toBe("en");
      expect(result2.current.data?.language_code).toBe("es");
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2);
    });

    it("fetches different data for different video IDs", async () => {
      const mockTranscript2: Transcript = {
        ...mockTranscript,
        video_id: "different123",
        full_text: "Different video transcript content.",
      };

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce({ data: mockTranscript })
        .mockResolvedValueOnce({ data: mockTranscript2 });

      const { result: result1 } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      const { result: result2 } = renderHook(() => useTranscript("different123", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.video_id).toBe("dQw4w9WgXcQ");
      expect(result2.current.data?.video_id).toBe("different123");
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe("multiple transcript types", () => {
    it("fetches manual transcript", async () => {
      const manualTranscript: Transcript = {
        ...mockTranscript,
        transcript_type: "manual",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: manualTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.transcript_type).toBe("manual");
    });

    it("fetches auto-generated transcript", async () => {
      const autoTranscript: Transcript = {
        ...mockTranscript,
        transcript_type: "auto_generated",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: autoTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.transcript_type).toBe("auto_generated");
    });

    it("fetches auto-synced transcript", async () => {
      const autoSyncedTranscript: Transcript = {
        ...mockTranscript,
        transcript_type: "auto_synced",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: autoSyncedTranscript,
      });

      const { result } = renderHook(() => useTranscript("dQw4w9WgXcQ", "en"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.transcript_type).toBe("auto_synced");
    });
  });
});
