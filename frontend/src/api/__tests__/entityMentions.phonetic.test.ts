/**
 * Tests for fetchPhoneticMatches in entityMentions API client (Feature 046, T003).
 *
 * Coverage:
 * - URL construction with and without threshold param
 * - Response envelope unwrapping (returns PhoneticMatch[], not { data: ... })
 * - AbortSignal forwarding for cancellation
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import { fetchPhoneticMatches } from "../entityMentions";
import type { PhoneticMatch } from "../../types/corrections";

vi.mock("../config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTITY_ID = "3f4a7b2c-1d9e-4f6a-b8c2-9e0d1f2a3b4c";

const PHONETIC_MATCH: PhoneticMatch = {
  original_text: "Alexandria Ocasio Cortez",
  proposed_correction: "Alexandria Ocasio-Cortez",
  confidence: 0.92,
  evidence_description: "Hyphen missing in hyphenated surname",
  video_id: "dQw4w9WgXcQ",
  segment_id: 42,
  video_title: "Congressional hearing highlights",
};

// ---------------------------------------------------------------------------
// fetchPhoneticMatches
// ---------------------------------------------------------------------------

describe("fetchPhoneticMatches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with correct endpoint when no threshold provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [PHONETIC_MATCH] });

    const result = await fetchPhoneticMatches(ENTITY_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/phonetic-matches`,
      {}
    );
    expect(result).toEqual([PHONETIC_MATCH]);
  });

  it("appends threshold query param when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchPhoneticMatches(ENTITY_ID, 0.8);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/phonetic-matches?threshold=0.8`,
      {}
    );
  });

  it("appends threshold=0 correctly (does not skip falsy zero)", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    await fetchPhoneticMatches(ENTITY_ID, 0);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/phonetic-matches?threshold=0`,
      {}
    );
  });

  it("forwards AbortSignal as externalSignal option", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });
    const controller = new AbortController();

    await fetchPhoneticMatches(ENTITY_ID, undefined, controller.signal);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/phonetic-matches`,
      { externalSignal: controller.signal }
    );
  });

  it("forwards both threshold and AbortSignal together", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [PHONETIC_MATCH] });
    const controller = new AbortController();

    const result = await fetchPhoneticMatches(ENTITY_ID, 0.75, controller.signal);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/phonetic-matches?threshold=0.75`,
      { externalSignal: controller.signal }
    );
    expect(result).toEqual([PHONETIC_MATCH]);
  });

  it("unwraps the data array from the response envelope", async () => {
    const matches: PhoneticMatch[] = [
      PHONETIC_MATCH,
      { ...PHONETIC_MATCH, original_text: "Ilhan Omar", segment_id: 99 },
    ];
    mockedApiFetch.mockResolvedValueOnce({ data: matches });

    const result = await fetchPhoneticMatches(ENTITY_ID);

    expect(result).toHaveLength(2);
    expect(result[0]?.original_text).toBe("Alexandria Ocasio Cortez");
    expect(result[1]?.original_text).toBe("Ilhan Omar");
  });

  it("returns empty array when data is empty", async () => {
    mockedApiFetch.mockResolvedValueOnce({ data: [] });

    const result = await fetchPhoneticMatches(ENTITY_ID);

    expect(result).toEqual([]);
  });

  it("handles video_title being null", async () => {
    const matchWithNullTitle: PhoneticMatch = { ...PHONETIC_MATCH, video_title: null };
    mockedApiFetch.mockResolvedValueOnce({ data: [matchWithNullTitle] });

    const result = await fetchPhoneticMatches(ENTITY_ID);

    expect(result[0]?.video_title).toBeNull();
  });
});
