/**
 * Tests for scanEntity, scanVideoEntities, and getScanJob in
 * api/entityMentions.ts (Feature: async entity scan).
 *
 * Coverage:
 * - scanEntity: correct endpoint URL construction with entity ID
 * - scanEntity: sends POST with JSON body (empty object when no options)
 * - scanEntity: forwards options fields in request body
 * - scanEntity: no longer overrides the request timeout (launch is fast now)
 * - scanEntity: returns the unwrapped ScanJob (not the envelope) on success
 * - scanEntity: propagates ApiError on failure (404, 409)
 * - scanVideoEntities: correct endpoint URL construction with video ID
 * - scanVideoEntities: sends POST with JSON body (empty object when no options)
 * - scanVideoEntities: forwards entity_type option in request body
 * - scanVideoEntities: no longer overrides the request timeout
 * - scanVideoEntities: returns the unwrapped ScanJob on success
 * - scanVideoEntities: propagates ApiError on failure
 * - getScanJob: correct endpoint URL construction with job ID
 * - getScanJob: forwards an external AbortSignal
 * - getScanJob: returns the unwrapped ScanJob for running/succeeded/failed states
 * - getScanJob: propagates ApiError (404) for an unknown job
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import { scanEntity, scanVideoEntities, getScanJob } from "../entityMentions";
import type { ScanJob, ScanJobResponse } from "../entityMentions";

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
const JOB_ID = "job-uuid-1234";

function makeScanJob(overrides: Partial<ScanJob> = {}): ScanJob {
  return {
    job_id: JOB_ID,
    kind: "entity",
    target_id: ENTITY_ID,
    status: "running",
    result: null,
    error: null,
    started_at: "2026-07-19T12:00:00Z",
    finished_at: null,
    ...overrides,
  };
}

function makeScanJobResponse(
  overrides: Partial<ScanJob> = {}
): ScanJobResponse {
  return { data: makeScanJob(overrides) };
}

// ===========================================================================
// scanEntity
// ===========================================================================

describe("scanEntity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with POST method on the correct entity scan endpoint", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${ENTITY_ID}/scan`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("does not set a timeout override — the launch request is fast", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.timeout).toBeUndefined();
  });

  it("sends an empty JSON object as the body when no options are provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("sends an empty JSON object as the body when options is explicitly undefined", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID, undefined);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("serializes language_code option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID, { language_code: "en" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ language_code: "en" }));
  });

  it("serializes dry_run option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID, { dry_run: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ dry_run: true }));
  });

  it("serializes full_rescan option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanEntity(ENTITY_ID, { full_rescan: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ full_rescan: true }));
  });

  it("serializes all options fields together in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

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

  it("returns the unwrapped ScanJob (status running) on success", async () => {
    const response = makeScanJobResponse({ status: "running" });
    mockedApiFetch.mockResolvedValueOnce(response);

    const result = await scanEntity(ENTITY_ID);

    expect(result).toEqual(response.data);
    expect(result.status).toBe("running");
    expect(result.job_id).toBe(JOB_ID);
    expect(result.result).toBeNull();
  });

  it("correctly interpolates entity_id into the endpoint URL", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    const customEntityId = "aabbccdd-1111-2222-3333-444455556666";
    await scanEntity(customEntityId);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/entities/${customEntityId}/scan`,
      expect.any(Object)
    );
  });

  it("propagates a 404 ApiError thrown by apiFetch", async () => {
    const apiError = { type: "server", message: "Entity not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanEntity(ENTITY_ID)).rejects.toEqual(apiError);
  });

  it("propagates a 409 ApiError (scan already in progress)", async () => {
    const apiError = {
      type: "server",
      message: "A scan is already in progress for this entity",
      status: 409,
    };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanEntity(ENTITY_ID)).rejects.toEqual(apiError);
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
    mockedApiFetch.mockResolvedValueOnce(
      makeScanJobResponse({ kind: "video", target_id: VIDEO_ID })
    );

    await scanVideoEntities(VIDEO_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${VIDEO_ID}/scan-entities`,
      expect.objectContaining({ method: "POST" })
    );
  });

  it("does not set a timeout override — the launch request is fast", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.timeout).toBeUndefined();
  });

  it("sends an empty JSON object as the body when no options are provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("sends an empty JSON object as the body when options is explicitly undefined", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID, undefined);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({}));
  });

  it("serializes entity_type option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID, { entity_type: "person" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ entity_type: "person" }));
  });

  it("serializes language_code option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID, { language_code: "fr" });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ language_code: "fr" }));
  });

  it("serializes dry_run option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID, { dry_run: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ dry_run: true }));
  });

  it("serializes full_rescan option in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await scanVideoEntities(VIDEO_ID, { full_rescan: true });

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBe(JSON.stringify({ full_rescan: true }));
  });

  it("serializes all options fields together in the request body", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

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

  it("returns the unwrapped ScanJob (kind video) on success", async () => {
    const response = makeScanJobResponse({ kind: "video", target_id: VIDEO_ID });
    mockedApiFetch.mockResolvedValueOnce(response);

    const result = await scanVideoEntities(VIDEO_ID);

    expect(result).toEqual(response.data);
    expect(result.kind).toBe("video");
    expect(result.target_id).toBe(VIDEO_ID);
  });

  it("correctly interpolates video_id into the endpoint URL", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    const customVideoId = "abc123XYZ";
    await scanVideoEntities(customVideoId);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${customVideoId}/scan-entities`,
      expect.any(Object)
    );
  });

  it("propagates a 404 ApiError thrown by apiFetch", async () => {
    const apiError = { type: "server", message: "Video not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanVideoEntities(VIDEO_ID)).rejects.toEqual(apiError);
  });

  it("propagates a 409 ApiError (scan already in progress)", async () => {
    const apiError = {
      type: "server",
      message: "A scan is already in progress for this video",
      status: 409,
    };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(scanVideoEntities(VIDEO_ID)).rejects.toEqual(apiError);
  });
});

// ===========================================================================
// getScanJob
// ===========================================================================

describe("getScanJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch on the correct scan-job status endpoint", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await getScanJob(JOB_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/scan-jobs/${JOB_ID}`,
      expect.any(Object)
    );
  });

  it("forwards an external AbortSignal when provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());
    const controller = new AbortController();

    await getScanJob(JOB_ID, controller.signal);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.externalSignal).toBe(controller.signal);
  });

  it("omits externalSignal when no signal is provided", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeScanJobResponse());

    await getScanJob(JOB_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.externalSignal).toBeUndefined();
  });

  it("returns the unwrapped ScanJob while running (result null)", async () => {
    const response = makeScanJobResponse({ status: "running" });
    mockedApiFetch.mockResolvedValueOnce(response);

    const result = await getScanJob(JOB_ID);

    expect(result.status).toBe("running");
    expect(result.result).toBeNull();
    expect(result.error).toBeNull();
  });

  it("returns the unwrapped ScanJob with result metrics when succeeded", async () => {
    const response = makeScanJobResponse({
      status: "succeeded",
      finished_at: "2026-07-19T12:03:00Z",
      result: {
        segments_scanned: 150,
        mentions_found: 8,
        mentions_skipped: 2,
        unique_entities: 3,
        unique_videos: 1,
        duration_seconds: 120.4,
        dry_run: false,
      },
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const result = await getScanJob(JOB_ID);

    expect(result.status).toBe("succeeded");
    expect(result.result?.mentions_found).toBe(8);
    expect(result.finished_at).toBe("2026-07-19T12:03:00Z");
  });

  it("returns the unwrapped ScanJob with an error message when failed", async () => {
    const response = makeScanJobResponse({
      status: "failed",
      finished_at: "2026-07-19T12:01:00Z",
      error: "Database connection lost during scan",
    });
    mockedApiFetch.mockResolvedValueOnce(response);

    const result = await getScanJob(JOB_ID);

    expect(result.status).toBe("failed");
    expect(result.error).toBe("Database connection lost during scan");
    expect(result.result).toBeNull();
  });

  it("propagates a 404 ApiError for an unknown job id", async () => {
    const apiError = { type: "server", message: "Scan job not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(getScanJob("unknown-job-id")).rejects.toEqual(apiError);
  });
});
