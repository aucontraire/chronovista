import { describe, it, expect, vi } from "vitest";

import { fetchRelationshipCandidates } from "../useRelationshipCandidates";

const apiFetchMock = vi.fn().mockResolvedValue({});
vi.mock("../../api/config", () => ({
  apiFetch: (...a: unknown[]) => apiFetchMock(...a),
}));

describe("fetchRelationshipCandidates", () => {
  it("sends review, sort_by and sort_dir as query params", async () => {
    await fetchRelationshipCandidates({
      limit: 50,
      offset: 0,
      eligible_only: false,
      review: "unreviewed",
      verdict: ["co_cast", "covers"],
      sort_by: "reviewed_at",
      sort_dir: "asc",
    });
    const url = new URL(`http://x${String(apiFetchMock.mock.calls[0]![0])}`);
    expect(url.searchParams.get("review")).toBe("unreviewed");
    expect(url.searchParams.getAll("verdict")).toEqual(["co_cast", "covers"]);
    expect(url.searchParams.get("sort_by")).toBe("reviewed_at");
    expect(url.searchParams.get("sort_dir")).toBe("asc");
  });
});
