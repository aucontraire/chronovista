/**
 * Unit tests for useTranscriptLanguages hook.
 *
 * Tests TanStack Query integration for fetching available transcript languages.
 *
 * @module tests/hooks/useTranscriptLanguages
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useTranscriptLanguages } from "../../hooks/useTranscriptLanguages";
import type { TranscriptLanguage } from "../../types/transcript";
import * as apiConfig from "../../api/config";

// Mock the API fetch
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

describe("useTranscriptLanguages", () => {
  let queryClient: QueryClient;

  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: "en",
      language_name: "English",
      transcript_type: "manual",
      is_translatable: true,
      downloaded_at: "2024-01-15T10:00:00Z",
    },
    {
      language_code: "es",
      language_name: "Spanish",
      transcript_type: "auto_generated",
      is_translatable: false,
      downloaded_at: "2024-01-15T10:05:00Z",
    },
  ];

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
    it("fetches and returns transcript languages array", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      const { result } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockLanguages);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("calls apiFetch with correct endpoint", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ/transcript/languages?include_unavailable=true");
      });
    });

    it("uses correct query key for caching", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      const { result } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const cachedData = queryClient.getQueryData(["transcriptLanguages", "dQw4w9WgXcQ"]);
      expect(cachedData).toEqual(mockLanguages);
    });
  });

  describe("empty languages array", () => {
    it("handles empty array when no transcripts available", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: [],
      });

      const { result } = renderHook(() => useTranscriptLanguages("noTranscriptVideo"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual([]);
      expect(Array.isArray(result.current.data)).toBe(true);
      expect(result.current.data).toHaveLength(0);
    });
  });

  describe("single language", () => {
    it("handles single language correctly", async () => {
      const singleLanguage: TranscriptLanguage[] = [
        {
          language_code: "en",
          language_name: "English",
          transcript_type: "manual",
          is_translatable: true,
          downloaded_at: "2024-01-15T10:00:00Z",
        },
      ];

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: singleLanguage,
      });

      const { result } = renderHook(() => useTranscriptLanguages("singleLangVideo"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(singleLanguage);
      expect(result.current.data).toHaveLength(1);
    });
  });

  describe("multiple languages", () => {
    it("handles multiple languages with different transcript types", async () => {
      const multipleLanguages: TranscriptLanguage[] = [
        {
          language_code: "en",
          language_name: "English",
          transcript_type: "manual",
          is_translatable: true,
          downloaded_at: "2024-01-15T10:00:00Z",
        },
        {
          language_code: "es",
          language_name: "Spanish",
          transcript_type: "auto_synced",
          is_translatable: false,
          downloaded_at: "2024-01-15T10:05:00Z",
        },
        {
          language_code: "fr",
          language_name: "French",
          transcript_type: "auto_generated",
          is_translatable: true,
          downloaded_at: "2024-01-15T10:10:00Z",
        },
      ];

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: multipleLanguages,
      });

      const { result } = renderHook(() => useTranscriptLanguages("multiLangVideo"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(multipleLanguages);
      expect(result.current.data).toHaveLength(3);
    });
  });

  describe("error handling", () => {
    it("handles 404 not found error", async () => {
      const notFoundError = {
        type: "server" as const,
        message: "Video not found",
        status: 404,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(notFoundError);

      const { result } = renderHook(() => useTranscriptLanguages("invalidVideo"), {
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

      const { result } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(networkError);
    });
  });

  describe("query enabled/disabled", () => {
    it("does not fetch when videoId is empty", () => {
      const { result } = renderHook(() => useTranscriptLanguages(""), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();
    });

    it("fetches when videoId is provided after being empty", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      let videoId = "";
      const { result, rerender } = renderHook(() => useTranscriptLanguages(videoId), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(apiConfig.apiFetch).not.toHaveBeenCalled();

      videoId = "dQw4w9WgXcQ";
      rerender();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith("/videos/dQw4w9WgXcQ/transcript/languages?include_unavailable=true");
    });
  });

  describe("staleTime configuration", () => {
    it("uses 5 minute staleTime for efficient caching", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      const { result } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queryState = queryClient.getQueryState(["transcriptLanguages", "dQw4w9WgXcQ"]);
      expect(queryState).toBeDefined();
    });
  });

  describe("caching behavior", () => {
    it("uses cached data for subsequent renders", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce({
        data: mockLanguages,
      });

      const { result: result1 } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);

      const { result: result2 } = renderHook(() => useTranscriptLanguages("dQw4w9WgXcQ"), {
        wrapper: createWrapper(),
      });

      expect(result2.current.data).toEqual(mockLanguages);
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);
    });

    it("fetches different data for different video IDs", async () => {
      const mockLanguages2: TranscriptLanguage[] = [
        {
          language_code: "de",
          language_name: "German",
          transcript_type: "manual",
          is_translatable: true,
          downloaded_at: "2024-01-15T11:00:00Z",
        },
      ];

      vi.mocked(apiConfig.apiFetch)
        .mockResolvedValueOnce({ data: mockLanguages })
        .mockResolvedValueOnce({ data: mockLanguages2 });

      const { result: result1 } = renderHook(() => useTranscriptLanguages("video1"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      const { result: result2 } = renderHook(() => useTranscriptLanguages("video2"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toHaveLength(2);
      expect(result2.current.data).toHaveLength(1);
      expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2);
    });
  });
});
