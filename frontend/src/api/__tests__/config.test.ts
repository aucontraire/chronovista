/**
 * Tests for apiFetch in api/config.ts.
 *
 * Coverage:
 * - 204 No Content: returns undefined instead of calling response.json()
 * - 205 Reset Content: same bodyless handling as 204
 * - 200 OK: parses and returns JSON body
 * - 4xx errors: throws ApiError with appropriate type
 * - 401/403 errors: classified as "auth" error type (FR-001)
 * - 5xx errors: classified as "server" error type
 * - Network failure (TypeError): classified as "network" error type
 * - Timeout (AbortError): classified as "timeout" error type
 * - isApiError type guard: correctly identifies ApiError objects
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiFetch, isApiError } from "../config";

// ---------------------------------------------------------------------------
// Global fetch mock
// ---------------------------------------------------------------------------

function makeMockResponse(
  status: number,
  body: unknown = null,
  options: { hasJsonMethod?: boolean } = {}
): Response {
  const { hasJsonMethod = true } = options;
  return {
    ok: status >= 200 && status < 300,
    status,
    json: hasJsonMethod
      ? vi.fn().mockResolvedValue(body)
      : vi.fn().mockRejectedValue(new SyntaxError("Unexpected end of JSON input")),
    headers: new Headers(),
    redirected: false,
    statusText: String(status),
    type: "basic",
    url: "http://localhost:8765/api/v1/test",
    body: null,
    bodyUsed: false,
    arrayBuffer: vi.fn(),
    blob: vi.fn(),
    formData: vi.fn(),
    text: vi.fn(),
    clone: vi.fn(),
  } as unknown as Response;
}

// ---------------------------------------------------------------------------
// Suite: 204/205 bodyless responses
// ---------------------------------------------------------------------------

describe("apiFetch — 204/205 No Content handling", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns undefined for a 204 No Content response without calling response.json()", async () => {
    const mockResponse = makeMockResponse(204);
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

    const result = await apiFetch<{ id: string }>("/test");

    expect(result).toBeUndefined();
    expect(mockResponse.json).not.toHaveBeenCalled();
  });

  it("returns undefined for a 205 Reset Content response without calling response.json()", async () => {
    const mockResponse = makeMockResponse(205);
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

    const result = await apiFetch<{ id: string }>("/test");

    expect(result).toBeUndefined();
    expect(mockResponse.json).not.toHaveBeenCalled();
  });

  it("does NOT throw when the server returns 204 (no body to parse)", async () => {
    // Before the fix, apiFetch called response.json() which would throw SyntaxError
    // on an empty body.  This test verifies the fix is in place.
    const mockResponse = makeMockResponse(204, null, { hasJsonMethod: false });
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

    await expect(apiFetch("/test")).resolves.toBeUndefined();
  });

  it("does NOT throw when the server returns 205 (no body to parse)", async () => {
    const mockResponse = makeMockResponse(205, null, { hasJsonMethod: false });
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

    await expect(apiFetch("/test")).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Suite: Successful 200 response
// ---------------------------------------------------------------------------

describe("apiFetch — successful 200 response", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON for a 200 OK response", async () => {
    const payload = { id: "abc", name: "Test" };
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(200, payload));

    const result = await apiFetch<{ id: string; name: string }>("/test");

    expect(result).toEqual(payload);
  });

  it("returns parsed JSON for a 201 Created response", async () => {
    const payload = { id: "new-id" };
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(201, payload));

    const result = await apiFetch<{ id: string }>("/test");

    expect(result).toEqual(payload);
  });

  it("sends Content-Type: application/json header by default", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(200, {}));

    await apiFetch("/test");

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/test"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: HTTP error classification
// ---------------------------------------------------------------------------

describe("apiFetch — HTTP error classification", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws an ApiError for a 404 Not Found response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(404));

    await expect(apiFetch("/missing")).rejects.toMatchObject({
      type: "server",
      status: 404,
    });
  });

  it("throws an ApiError for a 500 Internal Server Error response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(500));

    await expect(apiFetch("/broken")).rejects.toMatchObject({
      type: "server",
      status: 500,
    });
  });

  it("classifies 401 Unauthorized as auth error type (FR-001)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(401));

    await expect(apiFetch("/protected")).rejects.toMatchObject({
      type: "auth",
      status: 401,
    });
  });

  it("classifies 403 Forbidden as auth error type (FR-001)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(403));

    await expect(apiFetch("/forbidden")).rejects.toMatchObject({
      type: "auth",
      status: 403,
    });
  });

  it("includes the HTTP status in the thrown ApiError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(422));

    let caughtError: unknown;
    try {
      await apiFetch("/invalid");
    } catch (e) {
      caughtError = e;
    }

    expect(isApiError(caughtError)).toBe(true);
    expect((caughtError as { status: number }).status).toBe(422);
  });

  it("re-throws an already-formed ApiError without double-wrapping", async () => {
    // If apiFetch itself throws an ApiError (from createApiError(null, response)),
    // it must be propagated as-is without being wrapped in another ApiError.
    vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(503));

    let caughtError: unknown;
    try {
      await apiFetch("/unavailable");
    } catch (e) {
      caughtError = e;
    }

    // There must be exactly one level of wrapping — 'type' is a plain string, not an object.
    expect(isApiError(caughtError)).toBe(true);
    expect(typeof (caughtError as { type: unknown }).type).toBe("string");
  });
});

// ---------------------------------------------------------------------------
// Suite: Network and timeout errors
// ---------------------------------------------------------------------------

describe("apiFetch — network and timeout error classification", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("classifies a fetch TypeError as a network error", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(
      new TypeError("Failed to fetch")
    );

    await expect(apiFetch("/offline")).rejects.toMatchObject({
      type: "network",
    });
  });

  it("classifies an AbortError (DOMException) as a timeout error", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(
      new DOMException("The operation was aborted.", "AbortError")
    );

    await expect(apiFetch("/slow")).rejects.toMatchObject({
      type: "timeout",
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: isApiError type guard
// ---------------------------------------------------------------------------

describe("isApiError type guard", () => {
  it("returns true for a valid ApiError-shaped object", () => {
    expect(
      isApiError({ type: "server", message: "Something went wrong", status: 500 })
    ).toBe(true);
  });

  it("returns true for an ApiError without a status field", () => {
    expect(isApiError({ type: "network", message: "Cannot reach server" })).toBe(
      true
    );
  });

  it("returns false for null", () => {
    expect(isApiError(null)).toBe(false);
  });

  it("returns false for undefined", () => {
    expect(isApiError(undefined)).toBe(false);
  });

  it("returns false for a plain Error instance", () => {
    expect(isApiError(new Error("plain error"))).toBe(false);
  });

  it("returns false for an object missing the 'type' field", () => {
    expect(isApiError({ message: "no type here" })).toBe(false);
  });

  it("returns false for an object with a non-string type", () => {
    expect(isApiError({ type: 42, message: "bad type" })).toBe(false);
  });

  it("returns false for a string", () => {
    expect(isApiError("server error")).toBe(false);
  });
});
