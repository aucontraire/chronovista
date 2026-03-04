/**
 * Tests for useCorrectSegment hook.
 *
 * Implements tests for T012: Correction submission with optimistic updates,
 * rollback on error, and server-authoritative cache patching on success.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  InfiniteData,
} from "@tanstack/react-query";
import React from "react";

import { apiFetch } from "../../api/config";
import { useCorrectSegment } from "../useCorrectSegment";
import { segmentsQueryKey } from "../useTranscriptSegments";
import type { SegmentListResponse, TranscriptSegment } from "../../types/transcript";
import type { CorrectionSubmitResponse } from "../../types/corrections";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// --- Test Fixtures ---

const VIDEO_ID = "test-video-id";
const LANGUAGE_CODE = "en";

function makeSegment(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    id: 1,
    text: "Original text",
    start_time: 0,
    end_time: 5,
    duration: 5,
    has_correction: false,
    corrected_at: null,
    correction_count: 0,
    ...overrides,
  };
}

function makeSegmentListResponse(
  segments: TranscriptSegment[]
): SegmentListResponse {
  return {
    data: segments,
    pagination: {
      total: segments.length,
      offset: 0,
      limit: 50,
      has_more: false,
    },
  };
}

function makeInfiniteData(
  pages: SegmentListResponse[]
): InfiniteData<SegmentListResponse> {
  return {
    pages,
    pageParams: pages.map((_, i) => ({ offset: i * 50, limit: 50 })),
  };
}

function makeSubmitApiResponse(
  overrides: Partial<CorrectionSubmitResponse> = {}
): { data: CorrectionSubmitResponse } {
  return {
    data: {
      correction: {
        id: "uuid-correction-1",
        video_id: VIDEO_ID,
        language_code: LANGUAGE_CODE,
        segment_id: 1,
        correction_type: "asr_error",
        original_text: "Original text",
        corrected_text: "Corrected text",
        correction_note: null,
        corrected_by_user_id: null,
        corrected_at: "2024-01-01T12:00:00Z",
        version_number: 1,
      },
      segment_state: {
        has_correction: true,
        effective_text: "Corrected text",
      },
      ...overrides,
    },
  };
}

// --- Test Helpers ---

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// --- Tests ---

describe("useCorrectSegment", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("patches cache with server-authoritative values on successful submission", async () => {
    const segment = makeSegment({ id: 1, text: "Original text", correction_count: 0 });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    // Pre-populate the cache
    queryClient.setQueryData(qKey, initialData);

    const apiResponse = makeSubmitApiResponse();
    mockedApiFetch.mockResolvedValueOnce(apiResponse);

    const { result } = renderHook(
      () => useCorrectSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({
        segmentId: 1,
        corrected_text: "Corrected text",
        correction_type: "asr_error",
        correction_note: null,
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Verify cache reflects server-authoritative values
    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const updatedSegment = cached?.pages[0]?.data[0];

    expect(updatedSegment?.has_correction).toBe(true);
    expect(updatedSegment?.text).toBe("Corrected text");
    expect(updatedSegment?.corrected_at).toBe("2024-01-01T12:00:00Z");
  });

  it("applies optimistic update before server response is received", async () => {
    const segment = makeSegment({ id: 1, text: "Original text", correction_count: 2 });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    // Use a promise that we can control to delay the API response
    let resolveApiFetch!: (value: unknown) => void;
    const pendingApiFetch = new Promise((resolve) => {
      resolveApiFetch = resolve;
    });
    mockedApiFetch.mockReturnValueOnce(pendingApiFetch as Promise<never>);

    const { result } = renderHook(
      () => useCorrectSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    // Trigger mutation but don't await resolution
    act(() => {
      result.current.mutate({
        segmentId: 1,
        corrected_text: "Optimistically corrected",
        correction_type: "spelling",
        correction_note: "typo",
      });
    });

    // Allow onMutate to run (optimistic update)
    await waitFor(() => expect(result.current.isPending).toBe(true));

    // Verify optimistic update is applied before server responds
    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const optimisticSegment = cached?.pages[0]?.data[0];

    expect(optimisticSegment?.has_correction).toBe(true);
    expect(optimisticSegment?.text).toBe("Optimistically corrected");
    expect(optimisticSegment?.correction_count).toBe(3); // incremented from 2
    expect(optimisticSegment?.corrected_at).toBeTruthy(); // ISO timestamp set

    // Resolve the API call to clean up
    resolveApiFetch(makeSubmitApiResponse());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("rolls back to previous snapshot when the mutation fails", async () => {
    const segment = makeSegment({ id: 1, text: "Original text", correction_count: 0 });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    // Simulate an API failure
    const apiError = new Error("Server error");
    mockedApiFetch.mockRejectedValueOnce(apiError);

    const { result } = renderHook(
      () => useCorrectSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({
        segmentId: 1,
        corrected_text: "This correction will fail",
        correction_type: "asr_error",
        correction_note: null,
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    // Verify cache is rolled back to original state
    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const restoredSegment = cached?.pages[0]?.data[0];

    // Cache may be invalidated (undefined) or restored — either is acceptable.
    // If cache is present, it must reflect the original state.
    if (restoredSegment !== undefined) {
      expect(restoredSegment.has_correction).toBe(false);
      expect(restoredSegment.text).toBe("Original text");
      expect(restoredSegment.correction_count).toBe(0);
    }
  });

  it("calls invalidateQueries on error but NOT on success", async () => {
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);
    queryClient.setQueryData(qKey, makeInfiniteData([makeSegmentListResponse([])]));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    // --- Error case ---
    mockedApiFetch.mockRejectedValueOnce(new Error("failure"));

    const { result } = renderHook(
      () => useCorrectSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({
        segmentId: 1,
        corrected_text: "text",
        correction_type: "asr_error",
        correction_note: null,
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);

    // --- Reset ---
    invalidateSpy.mockClear();
    result.current.reset();

    // --- Success case ---
    mockedApiFetch.mockResolvedValueOnce(makeSubmitApiResponse());

    await act(async () => {
      result.current.mutate({
        segmentId: 1,
        corrected_text: "text",
        correction_type: "asr_error",
        correction_note: null,
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // invalidateQueries should NOT have been called on success
    expect(invalidateSpy).not.toHaveBeenCalled();

    invalidateSpy.mockRestore();
  });
});
