/**
 * Type-level tests for Feature 046 interfaces in corrections.ts (T001).
 *
 * These tests verify that:
 * - Each new interface can be instantiated with all required fields
 * - Optional fields (null unions) accept both values
 * - The interfaces are exported correctly from types/index.ts
 *
 * No mocking required — pure TypeScript structural verification at runtime.
 */

import { describe, it, expect } from "vitest";
import type {
  BatchSummary,
  DiffErrorPattern,
  CrossSegmentCandidate,
  PhoneticMatch,
} from "../corrections";

// Also verify the barrel re-exports compile correctly
import type {
  BatchSummary as BatchSummaryFromIndex,
  DiffErrorPattern as DiffErrorPatternFromIndex,
  CrossSegmentCandidate as CrossSegmentCandidateFromIndex,
  PhoneticMatch as PhoneticMatchFromIndex,
} from "../index";

describe("Feature 046 type interfaces (T001)", () => {
  describe("BatchSummary", () => {
    it("can be constructed with all required fields", () => {
      const summary: BatchSummary = {
        batch_id: "batch-uuid-001",
        correction_count: 47,
        corrected_by_user_id: "user:batch",
        pattern: "cliamte",
        replacement: "climate",
        batch_timestamp: "2026-03-15T10:00:00Z",
      };

      expect(summary.batch_id).toBe("batch-uuid-001");
      expect(summary.correction_count).toBe(47);
      expect(summary.corrected_by_user_id).toBe("user:batch");
      expect(summary.pattern).toBe("cliamte");
      expect(summary.replacement).toBe("climate");
      expect(summary.batch_timestamp).toBe("2026-03-15T10:00:00Z");
    });
  });

  describe("DiffErrorPattern", () => {
    it("can be constructed with entity_id and entity_name as null", () => {
      const pattern: DiffErrorPattern = {
        error_token: "whigt",
        canonical_form: "white",
        frequency: 5,
        remaining_matches: 3,
        entity_id: null,
        entity_name: null,
      };

      expect(pattern.error_token).toBe("whigt");
      expect(pattern.entity_id).toBeNull();
      expect(pattern.entity_name).toBeNull();
    });

    it("can be constructed with entity_id and entity_name as strings", () => {
      const pattern: DiffErrorPattern = {
        error_token: "berny",
        canonical_form: "Bernie",
        frequency: 10,
        remaining_matches: 7,
        entity_id: "3f4a7b2c-1d9e-4f6a-b8c2-9e0d1f2a3b4c",
        entity_name: "Bernie Sanders",
      };

      expect(pattern.entity_id).toBe("3f4a7b2c-1d9e-4f6a-b8c2-9e0d1f2a3b4c");
      expect(pattern.entity_name).toBe("Bernie Sanders");
    });
  });

  describe("CrossSegmentCandidate", () => {
    it("can be constructed with all required fields", () => {
      const candidate: CrossSegmentCandidate = {
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

      expect(candidate.segment_n_id).toBe(101);
      expect(candidate.segment_n1_id).toBe(102);
      expect(candidate.confidence).toBe(0.87);
      expect(candidate.is_partially_corrected).toBe(false);
      expect(candidate.video_id).toBe("abc123");
    });

    it("accepts is_partially_corrected as true", () => {
      const candidate: CrossSegmentCandidate = {
        segment_n_id: 200,
        segment_n_text: "half fixed",
        segment_n1_id: 201,
        segment_n1_text: "text here",
        proposed_correction: "half-fixed text here",
        source_pattern: "half fixed",
        confidence: 0.6,
        is_partially_corrected: true,
        video_id: "xyz789",
        discovery_source: "correction_pattern",
      };

      expect(candidate.is_partially_corrected).toBe(true);
    });
  });

  describe("PhoneticMatch", () => {
    it("can be constructed with video_title as null", () => {
      const match: PhoneticMatch = {
        original_text: "Alexandria Ocasio Cortez",
        proposed_correction: "Alexandria Ocasio-Cortez",
        confidence: 0.92,
        evidence_description: "Hyphen missing in hyphenated surname",
        video_id: "dQw4w9WgXcQ",
        segment_id: 42,
        video_title: null,
      };

      expect(match.video_title).toBeNull();
      expect(match.segment_id).toBe(42);
    });

    it("can be constructed with video_title as a string", () => {
      const match: PhoneticMatch = {
        original_text: "Ilhan",
        proposed_correction: "Ilhan Omar",
        confidence: 0.78,
        evidence_description: "Truncated name — surname likely cut by ASR pause",
        video_id: "vid456",
        segment_id: 99,
        video_title: "Congressional hearing highlights",
      };

      expect(match.video_title).toBe("Congressional hearing highlights");
    });
  });

  describe("Barrel re-exports from types/index.ts", () => {
    it("BatchSummary is accessible from the index barrel", () => {
      const summary: BatchSummaryFromIndex = {
        batch_id: "b",
        correction_count: 1,
        corrected_by_user_id: "u",
        pattern: "p",
        replacement: "r",
        batch_timestamp: "2026-01-01T00:00:00Z",
      };
      expect(summary.batch_id).toBe("b");
    });

    it("DiffErrorPattern is accessible from the index barrel", () => {
      const pattern: DiffErrorPatternFromIndex = {
        error_token: "tok",
        canonical_form: "token",
        frequency: 1,
        remaining_matches: 1,
        entity_id: null,
        entity_name: null,
      };
      expect(pattern.canonical_form).toBe("token");
    });

    it("CrossSegmentCandidate is accessible from the index barrel", () => {
      const candidate: CrossSegmentCandidateFromIndex = {
        segment_n_id: 1,
        segment_n_text: "a",
        segment_n1_id: 2,
        segment_n1_text: "b",
        proposed_correction: "ab",
        source_pattern: "a b",
        confidence: 0.5,
        is_partially_corrected: false,
        video_id: "v",
        discovery_source: "correction_pattern",
      };
      expect(candidate.video_id).toBe("v");
    });

    it("PhoneticMatch is accessible from the index barrel", () => {
      const match: PhoneticMatchFromIndex = {
        original_text: "x",
        proposed_correction: "y",
        confidence: 0.9,
        evidence_description: "desc",
        video_id: "v",
        segment_id: 1,
        video_title: null,
      };
      expect(match.proposed_correction).toBe("y");
    });
  });
});
