/**
 * Unit tests for the foldName utility.
 *
 * foldName is the case/accent-insensitive fold used to decide whether an alias
 * is the entity's own name ("Primary") on the entity detail page (Feature 075).
 * It mirrors the backend's `lower(unaccent(...))` membership fold.
 *
 * Accented illustration names are built from explicit code points (\u escapes)
 * so the tests never depend on how this source file happens to be encoded.
 *
 * @module tests/utils/foldName
 */

import { describe, it, expect } from "vitest";
import { foldName } from "../../utils/foldName";

const PENA_PRECOMPOSED = "Peña"; // n-tilde as one code point (U+00F1)
const PENA_DECOMPOSED = "Peña"; // n + combining tilde (U+0303)
const PENA_LOWER_ACCENT = "peña";

describe("foldName", () => {
  it("returns plain lowercase input unchanged", () => {
    expect(foldName("acme")).toBe("acme");
  });

  it("is case-insensitive", () => {
    expect(foldName("ACME")).toBe("acme");
    expect(foldName("AcMe")).toBe(foldName("acme"));
  });

  it("strips combining diacritics (accent-insensitive)", () => {
    // The fold-collision the feature must handle: two names that differ only
    // by an accent fold to the same value.
    expect(foldName(PENA_PRECOMPOSED)).toBe("pena");
    expect(foldName(PENA_LOWER_ACCENT)).toBe("pena");
    expect(foldName(PENA_PRECOMPOSED)).toBe(foldName("pena"));
  });

  it("folds precomposed and decomposed accents identically", () => {
    expect(PENA_PRECOMPOSED).not.toBe(PENA_DECOMPOSED); // genuinely different inputs
    expect(foldName(PENA_PRECOMPOSED)).toBe(foldName(PENA_DECOMPOSED));
    expect(foldName(PENA_DECOMPOSED)).toBe("pena");
  });

  it("trims surrounding whitespace", () => {
    expect(foldName("  Acme  ")).toBe("acme");
  });

  it("handles the empty string", () => {
    expect(foldName("")).toBe("");
    expect(foldName("   ")).toBe("");
  });

  it("does not throw on non-Latin scripts and lowercases where defined", () => {
    expect(() => foldName("Ελλ")).not.toThrow(); // Greek letters
    expect(foldName("Ω")).toBe("ω"); // capital omega -> small omega
  });

  it("keeps distinct names distinct", () => {
    expect(foldName("Acme")).not.toBe(foldName("Globex"));
  });
});
