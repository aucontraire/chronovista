/**
 * Tests for scanEntity and scanVideoEntities in api/entityMentions.ts (Feature 052).
 *
 * Coverage:
 * - scanEntity: correct endpoint URL construction with entity ID
 * - scanEntity: sends POST with JSON body (empty object when no options)
 * - scanEntity: forwards options fields in request body
 * - scanEntity: returns ScanResultResponse on success
 * - scanEntity: propagates ApiError on failure
 * - scanVideoEntities: correct endpoint URL construction with video ID
 * - scanVideoEntities: sends POST with JSON body (empty object when no options)
 * - scanVideoEntities: forwards entity_type option in request body
 * - scanVideoEntities: returns ScanResultResponse on success
 * - scanVideoEntities: propagates ApiError on failure
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, SCAN_TIMEOUT } from "../config";
import { scanEntity, scanVideoEntities } from "../entityMentions";
import type { ScanResultResponse } from "../entityMentions";

vi.mock("../config", async () => {
  const actual = await vi.importActual<typeof import("../config")>("../config");
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTITY_ID = "3f4a7b2c-1d9e-4f6a-b8c2-9e0d1f2a3b4c";
const VIDEO_ID = "dQw4w9WgXcQ";

function makeScanResultResponse(
  overrides: Partial<ScanResultResponse["data"]> = {}
): ScanResultResponse {
  return {
    data: {
      segments_scanned: 150,
      mentions_found: 8,
      mentions_skipped: 2,
      unique_entities: 3,
      unique_videos: 1,
      duration_seconds: 0.42,
      dry_run: false,
      ...overrides,
    },
  };
}

// ===========================================================================
// scanEntity
// ===========================================================================

describe("scanEntity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with POST method on the correct entity scan endpoint", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/scan`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("uses a 5-minute timeout to accommodate large corpus scans", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.timeout).toBe(SCAN_TIMEOUT);
  });

  it("sends an empty JSON object as the body when no options are provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("sends an empty JSON object as the body when options is explicitly undefined", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID, undefined);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("serializes language_code option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID, { language_code: "en" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ language_code: "en" }));
  });

  it("serializes dry_run option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse({ dry_run: true }));

    await scanEntity(ENTITY_ID, { dry_run: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ dry_run: true }));
  });

  it("serializes full_rescan option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID, { full_rescan: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ full_rescan: true }));
  });

  it("serializes all options fields together in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanEntity(ENTITY_ID, {
      language_code: "es",
      entity_type: "person",
      dry_run: false,
      full_rescan: true,
    });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(
      JSON.stringify({
        language_code: "es",
        entity_type: "person",
        dry_run: false,
        full_rescan: true,
      })
    );
  });

  it("returns the ScanResultResponse from the server on success", async () => {
    const expected = makeScanResultResponse({
      mentions_found: 12,
      unique_videos: 4,
    });
    mockedApiFetch.mockResolvedValueOnce(expected);

    const result = await scanEntity(ENTITY_ID);

    expect(result).toEqual(expected);
    expect(result.data.mentions_found).toBe(12);
    expect(result.data.unique_videos).toBe(4);
  });

  it("correctly interpolates entity_id into the endpoint URL", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    const customEntityId = "aabbccdd-1111-2222-3333-444455556666";
    await scanEntity(customEntityId);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${customEntityId}/scan`,
      expect.any(Object)
    );
  });

  it("propagates an ApiError thrown by apiFetch", async () => {
    const apiError = { type: "server", message: "Entity not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanEntity(ENTITY_ID)).rejects.toEqual(apiError);
  });

  it("propagates a 503 service unavailable error", async () => {
    const apiError = {
      type: "server",
      message: "Scan service unavailable",
      status: 503,
    };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanEntity(ENTITY_ID)).rejects.toEqual(apiError);
  });

  it("returns scan result with dry_run=true when dry_run option was set", async () => {
    const expected = makeScanResultResponse({ dry_run: true, mentions_found: 5 });
    mockedApiFetch.mockResolvedValueOnce(expected);

    const result = await scanEntity(ENTITY_ID, { dry_run: true });

    expect(result.data.dry_run).toBe(true);
    expect(result.data.mentions_found).toBe(5);
  });
});

// ===========================================================================
// scanVideoEntities
// ===========================================================================

describe("scanVideoEntities", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with POST method on the correct video scan endpoint", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${VIDEO_ID}/scan-entities`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("uses a 5-minute timeout to accommodate large corpus scans", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.timeout).toBe(SCAN_TIMEOUT);
  });

  it("sends an empty JSON object as the body when no options are provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("sends an empty JSON object as the body when options is explicitly undefined", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID, undefined);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("serializes entity_type option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID, { entity_type: "person" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ entity_type: "person" }));
  });

  it("serializes language_code option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID, { language_code: "fr" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ language_code: "fr" }));
  });

  it("serializes dry_run option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse({ dry_run: true }));

    await scanVideoEntities(VIDEO_ID, { dry_run: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ dry_run: true }));
  });

  it("serializes full_rescan option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID, { full_rescan: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ full_rescan: true }));
  });

  it("serializes all options fields together in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    await scanVideoEntities(VIDEO_ID, {
      language_code: "de",
      entity_type: "organization",
      dry_run: true,
      full_rescan: false,
    });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(
      JSON.stringify({
        language_code: "de",
        entity_type: "organization",
        dry_run: true,
        full_rescan: false,
      })
    );
  });

  it("returns the ScanResultResponse from the server on success", async () => {
    const expected = makeScanResultResponse({
      segments_scanned: 200,
      unique_entities: 7,
      mentions_found: 25,
    });
    mockedApiFetch.mockResolvedValueOnce(expected);

    const result = await scanVideoEntities(VIDEO_ID);

    expect(result).toEqual(expected);
    expect(result.data.segments_scanned).toBe(200);
    expect(result.data.unique_entities).toBe(7);
  });

  it("correctly interpolates video_id into the endpoint URL", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanResultResponse());

    const customVideoId = "abc123XYZ";
    await scanVideoEntities(customVideoId);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${customVideoId}/scan-entities`,
      expect.any(Object)
    );
  });

  it("propagates an ApiError thrown by apiFetch", async () => {
    const apiError = { type: "server", message: "Video not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanVideoEntities(VIDEO_ID)).rejects.toEqual(apiError);
  });

  it("propagates a 500 internal server error", async () => {
    const apiError = {
      type: "server",
      message: "Internal server error",
      status: 500,
    };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanVideoEntities(VIDEO_ID)).rejects.toEqual(apiError);
  });

  it("returns zero mentions when no entities were found in the video", async () => {
    const expected = makeScanResultResponse({
      mentions_found: 0,
      unique_entities: 0,
    });
    mockedApiFetch.mockResolvedValueOnce(expected);

    const result = await scanVideoEntities(VIDEO_ID);

    expect(result.data.mentions_found).toBe(0);
    expect(result.data.unique_entities).toBe(0);
  });
});
