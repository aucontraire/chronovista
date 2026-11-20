import { describe, expect, it } from "vitest";

import { buildVideoDeepLink } from "../videoDeepLink";

describe("buildVideoDeepLink", () => {
  it("builds a full lang+seg+t link and floors the timestamp", () => {
    expect(buildVideoDeepLink("vid1", { lang: "en", seg: 42, t: 12.9 })).toBe(
      "/videos/vid1?lang=en&seg=42&t=12",
    );
  });

  it("omits absent params (seg+t only, no lang)", () => {
    expect(buildVideoDeepLink("vid1", { seg: 5, t: 3 })).toBe(
      "/videos/vid1?seg=5&t=3",
    );
  });

  it("returns a bare path when no params are given", () => {
    expect(buildVideoDeepLink("vid1")).toBe("/videos/vid1");
  });
});
