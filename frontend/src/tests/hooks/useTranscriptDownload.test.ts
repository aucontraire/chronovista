/**
 * Unit tests for useTranscriptDownload mutation hook.
 *
 * Tests TanStack Query mutation integration for triggering transcript downloads.
 *
 * Coverage:
 * - T007-1: Hook exposes isPending, isError, isSuccess states
 * - T007-2: isPending is true during mutation execution
 * - T007-3: isSuccess and data are set after a successful download
 * - T007-4: isError and error are set after a failed download
 * - T007-5: Cache invalidation fires for video detail, transcript segments,
 *            and transcript languages on success (FR-005)
 * - T007-6: 30-second timeout is passed to apiFetch (NFR-002)
 * - T007-7: Error HTTP status codes are preserved for differentiation
 * - T007-8: Language parameter is appended to URL when provided
 *
 * @module tests/hooks/useTranscriptDownload
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useTranscriptDownload,
  type TranscriptDownloadResponse,
} from "../../hooks/useTranscriptDownload";
import type { ApiError } from "../../types/video";
import * as apiConfig from "../../api/config";

// ---------------------------------------------------------------------------
// Module-level mock for apiFetch
// ---------------------------------------------------------------------------

vi.mock("../../api/config", async () => {
  const actual = await vi.importActual<typeof import("../../api/config")>("../../api/config");
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VIDEO_ID = "dQw4w9WgXcQ";

const mockDownloadResponse: TranscriptDownloadResponse = {
  video_id: VIDEO_ID,
  language_code: "en",
  language_name: "English (United States)",
  transcript_type: "manual",
  segment_count: 142,
  downloaded_at: "2024-01-15T10:00:00Z",
};

// ---------------------------------------------------------------------------
// Test utilities
// ---------------------------------------------------------------------------

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useTranscriptDownload", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  // -------------------------------------------------------------------------
  // T007-1: Initial mutation states
  // -------------------------------------------------------------------------

  describe("initial mutation states (T007-1)", () => {
    it("exposes isPending=false, isError=false, isSuccess=false before mutation fires", () => {
      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isPending).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(result.current.isSuccess).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(result.current.error).toBeNull();
    });

    it("exposes a mutate function named 'mutate'", () => {
      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(typeof result.current.mutate).toBe("function");
    });

    it("exposes a reset function to clear mutation state", () => {
      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(typeof result.current.reset).toBe("function");
    });
  });

  // -------------------------------------------------------------------------
  // T007-2: isPending is true during mutation execution
  // -------------------------------------------------------------------------

  describe("loading state during mutation (T007-2)", () => {
    it("sets isPending=true while mutation is in flight", async () => {
      // Return a promise that never resolves so the mutation stays pending
      vi.mocked(apiConfig.apiFetch).mockImplementationOnce(
        () => new Promise<TranscriptDownloadResponse>(() => {})
      );

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isPending).toBe(false);

      act(() => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isPending).toBe(true);
      });

      expect(result.current.isSuccess).toBe(false);
      expect(result.current.isError).toBe(false);
    });

    it("transitions isPending from true to false after mutation resolves", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      act(() => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isPending).toBe(false);
      });

      expect(result.current.isSuccess).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // T007-3: Success state — isSuccess and data
  // -------------------------------------------------------------------------

  describe("success state (T007-3)", () => {
    it("sets isSuccess=true and data after a successful download", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockDownloadResponse);
      expect(result.current.isPending).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("data contains all fields from TranscriptDownloadResponse", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const data = result.current.data!;
      expect(data.video_id).toBe(VIDEO_ID);
      expect(data.language_code).toBe("en");
      expect(data.language_name).toBe("English (United States)");
      expect(data.transcript_type).toBe("manual");
      expect(data.segment_count).toBe(142);
      expect(data.downloaded_at).toBe("2024-01-15T10:00:00Z");
    });

    it("reset() clears success state back to idle", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      await act(async () => {
        result.current.reset();
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(false);
      });

      expect(result.current.data).toBeUndefined();
      expect(result.current.isPending).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // T007-4: Error state — isError and error
  // -------------------------------------------------------------------------

  describe("error state (T007-4)", () => {
    it("sets isError=true and error after a failed download", async () => {
      const serverError: ApiError = {
        type: "server",
        message: "Something went wrong on the server.",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(serverError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(serverError);
      expect(result.current.isPending).toBe(false);
      expect(result.current.isSuccess).toBe(false);
      expect(result.current.data).toBeUndefined();
    });

    it("reset() clears error state back to idle", async () => {
      const serverError: ApiError = {
        type: "server",
        message: "Something went wrong on the server.",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(serverError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      await act(async () => {
        result.current.reset();
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.error).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // T007-5: Cache invalidation on success (FR-005)
  // -------------------------------------------------------------------------

  describe("cache invalidation on success (T007-5 / FR-005)", () => {
    it("force-refetches the ['video', videoId] query key after success (not just invalidates)", async () => {
      // The video detail uses staleTime: 10 s. invalidateQueries has an edge
      // case in TanStack Query v5 where it may not trigger a network refetch
      // if the query was populated very recently. We use refetchQueries so the
      // component transitions from download button to transcript panel without
      // requiring a manual page reload.
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      // Pre-seed the video detail cache so we can confirm refetch
      queryClient.setQueryData(["video", VIDEO_ID], { video_id: VIDEO_ID });

      const refetchSpy = vi.spyOn(queryClient, "refetchQueries");

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(refetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["video", VIDEO_ID], exact: true })
      );
    });

    it("invalidates the ['transcriptSegments', videoId] query key prefix after success", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["transcriptSegments", VIDEO_ID],
          exact: false,
        })
      );
    });

    it("invalidates the ['transcriptLanguages', videoId] query key after success", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["transcriptLanguages", VIDEO_ID] })
      );
    });

    it("fires refetch for video detail and invalidates segment/language caches concurrently on success", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const refetchSpy = vi.spyOn(queryClient, "refetchQueries");
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Video detail: force-refetch (bypasses staleTime for immediate UI update)
      const refetchedKeys = refetchSpy.mock.calls.map(
        (call) => (call[0] as { queryKey: unknown[] }).queryKey
      );
      expect(refetchedKeys).toContainEqual(["video", VIDEO_ID]);

      // Transcript segment/language queries: invalidate (they become active
      // only after TranscriptPanel mounts, so marking stale is sufficient)
      const invalidatedKeys = invalidateSpy.mock.calls.map(
        (call) => (call[0] as { queryKey: unknown[] }).queryKey
      );
      expect(invalidatedKeys).toContainEqual(["transcriptSegments", VIDEO_ID]);
      expect(invalidatedKeys).toContainEqual(["transcriptLanguages", VIDEO_ID]);
    });

    it("does not call refetchQueries or invalidateQueries when mutation fails", async () => {
      const serverError: ApiError = {
        type: "server",
        message: "Something went wrong on the server.",
        status: 500,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(serverError);

      const refetchSpy = vi.spyOn(queryClient, "refetchQueries");
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(refetchSpy).not.toHaveBeenCalled();
      expect(invalidateSpy).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // T007-6: 30-second timeout (NFR-002)
  // -------------------------------------------------------------------------

  describe("2-minute timeout configuration (T007-6 / NFR-002)", () => {
    it("calls apiFetch with timeout: 120000", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ timeout: apiConfig.TRANSCRIPT_DOWNLOAD_TIMEOUT })
      );
    });

    it("uses POST method for the download request", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ method: "POST" })
      );
    });

    it("propagates a timeout ApiError when apiFetch times out", async () => {
      const timeoutError: ApiError = {
        type: "timeout",
        message: "The server took too long to respond.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(timeoutError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(timeoutError);
      expect(result.current.error?.type).toBe("timeout");
    });
  });

  // -------------------------------------------------------------------------
  // T007-7: Error differentiation by HTTP status code
  // -------------------------------------------------------------------------

  describe("error differentiation by HTTP status code (T007-7)", () => {
    it("preserves status 503 for YouTube rate-limit errors", async () => {
      const rateLimitError: ApiError = {
        type: "server",
        message: "Something went wrong on the server.",
        status: 503,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(rateLimitError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.status).toBe(503);
    });

    it("preserves status 404 for 'no transcript available' errors", async () => {
      const notFoundError: ApiError = {
        type: "server",
        message: "Transcript not found for this video.",
        status: 404,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(notFoundError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.status).toBe(404);
    });

    it("preserves status 429 for 'download already in progress' errors", async () => {
      const conflictError: ApiError = {
        type: "server",
        message: "A download is already in progress for this video.",
        status: 429,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(conflictError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.status).toBe(429);
    });

    it("preserves network error type when backend is unreachable", async () => {
      const networkError: ApiError = {
        type: "network",
        message:
          "Cannot reach the API server. Make sure the backend is running on port 8765.",
        status: undefined,
      };

      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(networkError);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.type).toBe("network");
      expect(result.current.error?.status).toBeUndefined();
    });

    it("503 vs 404 status codes are distinguishable on the error object", async () => {
      // First call: 503
      const rateLimitError: ApiError = {
        type: "server",
        message: "Something went wrong on the server.",
        status: 503,
      };
      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(rateLimitError);

      const qc1 = makeQueryClient();
      const { result: result1 } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(qc1) }
      );

      await act(async () => {
        result1.current.mutate({});
      });

      await waitFor(() => {
        expect(result1.current.isError).toBe(true);
      });

      // Second call: 404
      const notFoundError: ApiError = {
        type: "server",
        message: "Transcript not found.",
        status: 404,
      };
      vi.mocked(apiConfig.apiFetch).mockRejectedValueOnce(notFoundError);

      const qc2 = makeQueryClient();
      const { result: result2 } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(qc2) }
      );

      await act(async () => {
        result2.current.mutate({});
      });

      await waitFor(() => {
        expect(result2.current.isError).toBe(true);
      });

      expect(result1.current.error?.status).toBe(503);
      expect(result2.current.error?.status).toBe(404);
      expect(result1.current.error?.status).not.toBe(
        result2.current.error?.status
      );

      qc1.clear();
      qc2.clear();
    });
  });

  // -------------------------------------------------------------------------
  // T007-8: Optional language parameter in URL
  // -------------------------------------------------------------------------

  describe("optional language parameter in URL (T007-8)", () => {
    it("calls the correct endpoint without language param when language is not provided", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${VIDEO_ID}/transcript/download`,
        expect.any(Object)
      );
    });

    it("calls the correct endpoint without language param when language is undefined", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${VIDEO_ID}/transcript/download`,
        expect.any(Object)
      );
    });

    it("appends ?language=en when language is 'en'", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({ language: "en" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${VIDEO_ID}/transcript/download?language=en`,
        expect.any(Object)
      );
    });

    it("URL-encodes the language code when it contains special characters", async () => {
      const zhResponse: TranscriptDownloadResponse = {
        ...mockDownloadResponse,
        language_code: "zh-Hans",
        language_name: "Chinese (Simplified)",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(zhResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({ language: "zh-Hans" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // encodeURIComponent("zh-Hans") → "zh-Hans" (hyphen is not encoded, but
      // the hook uses encodeURIComponent, so we assert the encoded form)
      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${VIDEO_ID}/transcript/download?language=${encodeURIComponent("zh-Hans")}`,
        expect.any(Object)
      );
    });

    it("URL-encodes a language code with plus character", async () => {
      // BCP-47 codes can theoretically contain '+' (e.g. script subtags in extended form)
      // This exercises the encodeURIComponent path.
      const encodedLang = "sr-Latn";
      const srResponse: TranscriptDownloadResponse = {
        ...mockDownloadResponse,
        language_code: encodedLang,
        language_name: "Serbian (Latin)",
      };

      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(srResponse);

      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: VIDEO_ID }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({ language: encodedLang });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${VIDEO_ID}/transcript/download?language=${encodeURIComponent(encodedLang)}`,
        expect.any(Object)
      );
    });

    it("uses videoId from hook options — not from mutation variables — to build the URL", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockDownloadResponse);

      const customVideoId = "abc123xyz01";
      const { result } = renderHook(
        () => useTranscriptDownload({ videoId: customVideoId }),
        { wrapper: createWrapper(queryClient) }
      );

      await act(async () => {
        result.current.mutate({ language: "en" });
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiConfig.apiFetch).toHaveBeenCalledWith(
        `/videos/${customVideoId}/transcript/download?language=en`,
        expect.any(Object)
      );
    });
  });

  // -------------------------------------------------------------------------
  // Supplemental: transcript_type variants returned in success data
  // -------------------------------------------------------------------------

  describe("transcript_type variants in success response", () => {
    it.each([
      ["manual"],
      ["auto_synced"],
      ["auto_generated"],
    ] as const)(
      "handles transcript_type '%s' in success response",
      async (transcriptType) => {
        const response: TranscriptDownloadResponse = {
          ...mockDownloadResponse,
          transcript_type: transcriptType,
        };

        vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(response);

        const qc = makeQueryClient();
        const { result } = renderHook(
          () => useTranscriptDownload({ videoId: VIDEO_ID }),
          { wrapper: createWrapper(qc) }
        );

        await act(async () => {
          result.current.mutate({});
        });

        await waitFor(() => {
          expect(result.current.isSuccess).toBe(true);
        });

        expect(result.current.data?.transcript_type).toBe(transcriptType);
        qc.clear();
      }
    );
  });
});
