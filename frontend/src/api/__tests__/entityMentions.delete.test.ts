/**
 * Tests for deleteManualAssociation in api/entityMentions.ts.
 *
 * Coverage:
 * - Sends DELETE request to correct endpoint
 * - Calls apiFetch with method: "DELETE"
 * - Returns void (Promise<void>) — no response body expected
 * - Works correctly with 204 No Content (relies on apiFetch 204 fix)
 * - Propagates ApiError on failure
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import { deleteManualAssociation, createManualAssociation } from "../entityMentions";

vi.mock("../config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VIDEO_ID = "dQw4w9WgXcQ";
const ENTITY_ID = "3f4a7b2c-1d9e-4f6a-b8c2-9e0d1f2a3b4c";

// ---------------------------------------------------------------------------
// deleteManualAssociation
// ---------------------------------------------------------------------------

describe("deleteManualAssociation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls apiFetch with DELETE method on the correct endpoint", async () => {
    // apiFetch returns undefined for 204 — mock that here
    mockedApiFetch.mockResolvedValueOnce(undefined);

    await deleteManualAssociation(VIDEO_ID, ENTITY_ID);

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${VIDEO_ID}/entities/${ENTITY_ID}/manual`,
      { method: "DELETE" }
    );
  });

  it("resolves to undefined (void) on success — no body expected", async () => {
    mockedApiFetch.mockResolvedValueOnce(undefined);

    const result = await deleteManualAssociation(VIDEO_ID, ENTITY_ID);

    // The function returns Promise<void> — result is undefined
    expect(result).toBeUndefined();
  });

  it("does not call apiFetch with a body payload", async () => {
    mockedApiFetch.mockResolvedValueOnce(undefined);

    await deleteManualAssociation(VIDEO_ID, ENTITY_ID);

    const callArgs = mockedApiFetch.mock.calls[0];
    const options = callArgs?.[1] as Record<string, unknown> | undefined;
    expect(options?.body).toBeUndefined();
  });

  it("propagates an ApiError thrown by apiFetch", async () => {
    const apiError = { type: "server", message: "Not found", status: 404 };
    mockedApiFetch.mockRejectedValueOnce(apiError);

    await expect(deleteManualAssociation(VIDEO_ID, ENTITY_ID)).rejects.toEqual(
      apiError
    );
  });

  it("correctly interpolates video_id and entity_id into the endpoint URL", async () => {
    mockedApiFetch.mockResolvedValueOnce(undefined);

    const testVideoId = "abc-video";
    const testEntityId = "xyz-entity";
    await deleteManualAssociation(testVideoId, testEntityId);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${testVideoId}/entities/${testEntityId}/manual`,
      expect.objectContaining({ method: "DELETE" })
    );
  });
});

// ---------------------------------------------------------------------------
// createManualAssociation (regression — ensure it still sends POST correctly)
// ---------------------------------------------------------------------------

describe("createManualAssociation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const MOCK_ASSOCIATION_RESPONSE = {
    id: "assoc-uuid",
    entity_id: ENTITY_ID,
    video_id: VIDEO_ID,
    detection_method: "manual",
    mention_text: "manual",
    created_at: "2024-01-01T00:00:00Z",
  };

  it("calls apiFetch with POST method on the correct endpoint", async () => {
    mockedApiFetch.mockResolvedValueOnce(MOCK_ASSOCIATION_RESPONSE);

    await createManualAssociation(VIDEO_ID, ENTITY_ID);

    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/videos/${VIDEO_ID}/entities/${ENTITY_ID}/manual`,
      { method: "POST" }
    );
  });

  it("returns the ManualAssociationResponse from the server", async () => {
    mockedApiFetch.mockResolvedValueOnce(MOCK_ASSOCIATION_RESPONSE);

    const result = await createManualAssociation(VIDEO_ID, ENTITY_ID);

    expect(result).toEqual(MOCK_ASSOCIATION_RESPONSE);
  });
});
