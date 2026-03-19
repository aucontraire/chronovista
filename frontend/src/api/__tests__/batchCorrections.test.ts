/**
 * Tests for batchCorrections API client functions (Feature 046, T002).
 *
 * Coverage:
 * - fetchDiffAnalysis: URL construction with and without params, response unwrapping
 * - fetchCrossSegmentCandidates: URL construction with and without params, response unwrapping
 * - AbortSignal forwarding for cancellation
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import {
  fetchDiffAnalysis,
  fetchCrossSegmentCandidates,
} from "../batchCorrections";
import type { DiffErrorPattern, CrossSegmentCandidate } from "../../types/corrections";

vi.mock("../config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DIFF_PATTERN: DiffErrorPattern = {
  error_token: "cliamte",
  canonical_form: "climate",
  frequency: 12,
  remaining_matches: 8,
  entity_id: null,
  entity_name: null,
};

const CROSS_SEGMENT: CrossSegmentCandidate = {
  segment_n_id: 101,
  segment_n_text: "the coun",
  segment_n1_id: 102,
  segment_n1_text: "try side",
  proposed_correction: "the countryside",
  source_pattern: "coun|try side",
  confidence: 0.87,
  is_partially_corrected: false,
  video_id: "abc123",
  discovery_source: "correction_pattern",
};

// ---------------------------------------------------------------------------
// fetchDiffAnalysis
// ---------------------------------------------------------------------------

describe("fetchDiffAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with bare URL when no params provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [DIFF_PATTERN] });

    const result = await fetchDiffAnalysis();

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis",
      {}
    );
    expect(result).toEqual([DIFF_PATTERN]);
  });

  it("appends min_occurrences query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchDiffAnalysis({ minOccurrences: 3 });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis?min_occurrences=3",
      {}
    );
  });

  it("appends limit query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchDiffAnalysis({ limit: 25 });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis?limit=25",
      {}
    );
  });

  it("appends show_completed=true when showCompleted is true", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchDiffAnalysis({ showCompleted: true });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis?show_completed=true",
      {}
    );
  });

  it("appends show_completed=false when showCompleted is false", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchDiffAnalysis({ showCompleted: false });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis?show_completed=false",
      {}
    );
  });

  it("appends entity_name query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchDiffAnalysis({ entityName: "Alexandria Ocasio-Cortez" });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis?entity_name=Alexandria+Ocasio-Cortez",
      {}
    );
  });

  it("combines all params into a single query string", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [DIFF_PATTERN] });

    const result = await fetchDiffAnalysis({
      minOccurrences: 2,
      limit: 10,
      showCompleted: false,
      entityName: "climate",
    });

    const [[url]] = mockedApiFetch.mock.calls as [[string, object]];
    expect(url).toContain("min_occurrences=2");
    expect(url).toContain("limit=10");
    expect(url).toContain("show_completed=false");
    expect(url).toContain("entity_name=climate");
    expect(url).toMatch(/^\/corrections\/batch\/diff-analysis\?/);
    expect(result).toEqual([DIFF_PATTERN]);
  });

  it("forwards AbortSignal as externalSignal option", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });
    const controller = new AbortController();

    await fetchDiffAnalysis(undefined, controller.signal);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/diff-analysis",
      { externalSignal: controller.signal }
    );
  });

  it("unwraps the data array from the response envelope", async () => {
    const patterns: DiffErrorPattern[] = [DIFF_PATTERN, { ...DIFF_PATTERN, error_token: "whigt" }];
    mockedApiFetch.mockResolvedValueOnce({ data: patterns });

    const result = await fetchDiffAnalysis();

    expect(result).toHaveLength(2);
    expect(result[0]?.error_token).toBe("cliamte");
    expect(result[1]?.error_token).toBe("whigt");
  });

  it("returns empty array when data is empty", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    const result = await fetchDiffAnalysis();

    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// fetchCrossSegmentCandidates
// ---------------------------------------------------------------------------

describe("fetchCrossSegmentCandidates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with bare URL when no params provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [CROSS_SEGMENT] });

    const result = await fetchCrossSegmentCandidates();

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/cross-segment/candidates",
      {}
    );
    expect(result).toEqual([CROSS_SEGMENT]);
  });

  it("appends min_corrections query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchCrossSegmentCandidates({ minCorrections: 5 });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/cross-segment/candidates?min_corrections=5",
      {}
    );
  });

  it("appends entity_name query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchCrossSegmentCandidates({ entityName: "Bernie Sanders" });

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/cross-segment/candidates?entity_name=Bernie+Sanders",
      {}
    );
  });

  it("combines minCorrections and entityName params", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [CROSS_SEGMENT] });

    const result = await fetchCrossSegmentCandidates({
      minCorrections: 3,
      entityName: "AOC",
    });

    const [[url]] = mockedApiFetch.mock.calls as [[string, object]];
    expect(url).toContain("min_corrections=3");
    expect(url).toContain("entity_name=AOC");
    expect(result).toEqual([CROSS_SEGMENT]);
  });

  it("forwards AbortSignal as externalSignal option", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });
    const controller = new AbortController();

    await fetchCrossSegmentCandidates(undefined, controller.signal);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/corrections/batch/cross-segment/candidates",
      { externalSignal: controller.signal }
    );
  });

  it("unwraps the data array from the response envelope", async () => {
    const candidates: CrossSegmentCandidate[] = [
      CROSS_SEGMENT,
      { ...CROSS_SEGMENT, segment_n_id: 200, video_id: "xyz999" },
    ];
    mockedApiFetch.mockResolvedValueOnce({ data: candidates });

    const result = await fetchCrossSegmentCandidates();

    expect(result).toHaveLength(2);
    expect(result[0]?.segment_n_id).toBe(101);
    expect(result[1]?.segment_n_id).toBe(200);
  });

  it("returns empty array when data is empty", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    const result = await fetchCrossSegmentCandidates();

    expect(result).toEqual([]);
  });
});
