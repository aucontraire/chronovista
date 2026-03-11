/**
 * Correction domain types for the inline correction UI (Feature 035).
 * These types match the backend API response schemas for correction functionality.
 */

export type CorrectionType =
  | "spelling"
  | "proper_noun"
  | "context_correction"
  | "word_boundary"
  | "formatting"
  | "profanity_fix"
  | "other";

export const CORRECTION_TYPE_LABELS: Record<CorrectionType, string> = {
  spelling: "Spelling",
  proper_noun: "Proper Noun",
  context_correction: "Context Correction",
  word_boundary: "Word Boundary",
  formatting: "Formatting",
  profanity_fix: "Profanity Restoration",
  other: "Other",
};

export const CORRECTION_TYPE_DESCRIPTIONS: Record<CorrectionType, string> = {
  spelling: "Non-name orthographic errors (typos, misspellings of common words)",
  proper_noun: "Names of people, places, or organizations that ASR misrecognized",
  context_correction: "Right sound, wrong word — ASR picked a valid word that doesn't fit the context",
  word_boundary: "Run-together words or wrongly split compounds (e.g., 'alotof' → 'a lot of')",
  formatting: "Punctuation, capitalization, or spacing corrections",
  profanity_fix: "ASR garbled or censored profanity that needs restoration",
  other: "Corrections that don't fit other categories",
};

export const DEFAULT_CORRECTION_TYPE: CorrectionType = "proper_noun";

export interface CorrectionSubmitRequest {
  corrected_text: string;
  correction_type: CorrectionType;
  correction_note: string | null;
  // corrected_by_user_id intentionally omitted — backend defaults to null.
  // See Non-Goals: "Correction author display" (no auth UI exists).
}

export interface CorrectionAuditRecord {
  id: string; // UUID
  video_id: string;
  language_code: string;
  segment_id: number | null;
  correction_type: CorrectionType | "revert";
  original_text: string;
  corrected_text: string;
  correction_note: string | null;
  corrected_by_user_id: string | null;
  corrected_at: string; // ISO 8601 datetime
  version_number: number;
}

export interface SegmentCorrectionState {
  has_correction: boolean;
  effective_text: string;
}

export interface CorrectionSubmitResponse {
  correction: CorrectionAuditRecord;
  segment_state: SegmentCorrectionState;
}

// Same shape as CorrectionSubmitResponse
export type CorrectionRevertResponse = CorrectionSubmitResponse;

/**
 * Named alias for the correction history endpoint response.
 * Structurally identical to ApiResponseEnvelope&lt;CorrectionAuditRecord[]&gt;.
 * Using a named type improves readability in hook signatures.
 */
export type CorrectionHistoryResponse = {
  data: CorrectionAuditRecord[];
  pagination: {
    total: number;
    offset: number;
    limit: number;
    has_more: boolean;
  };
};

// --- State Types ---

export type SegmentEditState =
  | { mode: "read" }
  | { mode: "editing"; segmentId: number }
  | { mode: "confirming-revert"; segmentId: number }
  | { mode: "history"; segmentId: number };

export interface SegmentEditFormState {
  text: string;
  correctionType: CorrectionType;
  correctionNote: string;
  validationError: string | null;
}
