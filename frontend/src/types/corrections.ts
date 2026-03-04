/**
 * Correction domain types for the inline correction UI (Feature 035).
 * These types match the backend API response schemas for correction functionality.
 */

export type CorrectionType =
  | "spelling"
  | "asr_error"
  | "context_correction"
  | "profanity_fix"
  | "formatting";

export const CORRECTION_TYPE_LABELS: Record<CorrectionType, string> = {
  spelling: "Spelling",
  asr_error: "ASR Error",
  context_correction: "Context Correction",
  profanity_fix: "Profanity Fix",
  formatting: "Formatting",
};

export const DEFAULT_CORRECTION_TYPE: CorrectionType = "asr_error";

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
