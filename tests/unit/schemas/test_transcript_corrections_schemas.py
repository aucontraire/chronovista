"""
Unit tests for transcript correction API request/response schemas.

Covers CorrectionSubmitRequest, CorrectionAuditRecord, SegmentCorrectionState,
CorrectionSubmitResponse, and CorrectionRevertResponse.

Key behavioral notes verified against the actual schema implementation:
- CorrectionSubmitRequest uses ConfigDict(strict=True, str_strip_whitespace=True).
- str_strip_whitespace strips leading/trailing whitespace before validation,
  so whitespace-only strings are stripped to "" and rejected by min_length=1.
- CorrectionType.REVERT is rejected by a field_validator.
- CorrectionAuditRecord enables from_attributes=True for ORM-like mapping.
- CorrectionRevertResponse is a type alias pointing at CorrectionSubmitResponse.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from chronovista.api.schemas.transcript_corrections import (
    CorrectionAuditRecord,
    CorrectionRevertResponse,
    CorrectionSubmitRequest,
    CorrectionSubmitResponse,
    SegmentCorrectionState,
)
from chronovista.models.enums import CorrectionType

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_audit_record_dict(
    *,
    id: uuid.UUID | None = None,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    segment_id: int | None = 7,
    correction_type: CorrectionType = CorrectionType.SPELLING,
    original_text: str = "teh quick fox",
    corrected_text: str = "the quick fox",
    correction_note: str | None = "Typo fix",
    corrected_by_user_id: str | None = "user_abc",
    corrected_at: datetime | None = None,
    version_number: int = 1,
) -> dict[str, Any]:
    """Return a dict with all fields needed for CorrectionAuditRecord."""
    return {
        "id": id or uuid.uuid4(),
        "video_id": video_id,
        "language_code": language_code,
        "segment_id": segment_id,
        "correction_type": correction_type,
        "original_text": original_text,
        "corrected_text": corrected_text,
        "correction_note": correction_note,
        "corrected_by_user_id": corrected_by_user_id,
        "corrected_at": corrected_at or datetime.now(tz=timezone.utc),
        "version_number": version_number,
    }


def _make_audit_record(**overrides) -> CorrectionAuditRecord:
    """Instantiate a valid CorrectionAuditRecord."""
    return CorrectionAuditRecord(**_make_audit_record_dict(**overrides))


def _make_segment_state(
    has_correction: bool = True,
    effective_text: str = "the quick fox",
) -> SegmentCorrectionState:
    return SegmentCorrectionState(
        has_correction=has_correction,
        effective_text=effective_text,
    )


# ---------------------------------------------------------------------------
# TestCorrectionSubmitRequest
# ---------------------------------------------------------------------------


class TestCorrectionSubmitRequest:
    """Tests for CorrectionSubmitRequest schema validation."""

    def test_valid_payload_all_fields(self) -> None:
        """Valid payload with every field populated should succeed."""
        req = CorrectionSubmitRequest(
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed common typo",
            corrected_by_user_id="user_42",
        )

        assert req.corrected_text == "the quick brown fox"
        assert req.correction_type == CorrectionType.SPELLING
        assert req.correction_note == "Fixed common typo"
        assert req.corrected_by_user_id == "user_42"

    def test_valid_payload_only_required_fields(self) -> None:
        """Payload with only required fields and optional fields defaulting to None."""
        req = CorrectionSubmitRequest(
            corrected_text="corrected segment",
            correction_type=CorrectionType.ASR_ERROR,
        )

        assert req.corrected_text == "corrected segment"
        assert req.correction_type == CorrectionType.ASR_ERROR
        assert req.correction_note is None
        assert req.corrected_by_user_id is None

    def test_empty_corrected_text_raises_validation_error(self) -> None:
        """Empty string for corrected_text violates min_length=1 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(
                corrected_text="",
                correction_type=CorrectionType.FORMATTING,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("corrected_text",) for e in errors)
        assert any(e["type"] == "string_too_short" for e in errors)

    def test_whitespace_only_corrected_text_is_rejected(self) -> None:
        """Whitespace-only string is stripped to empty then rejected by min_length=1.

        ConfigDict(str_strip_whitespace=True) strips leading/trailing whitespace,
        so "   " becomes "" which fails the min_length=1 constraint (FR-015).
        """
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(
                corrected_text="   ",
                correction_type=CorrectionType.FORMATTING,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("corrected_text",) for e in errors)

    def test_correction_type_revert_raises_validation_error(self) -> None:
        """CorrectionType.REVERT must be rejected by the field_validator."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(
                corrected_text="some text",
                correction_type=CorrectionType.REVERT,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("correction_type",) for e in errors)
        # The validator raises ValueError with a descriptive message.
        assert any("revert" in str(e.get("msg", "")).lower() for e in errors)

    def test_correction_type_spelling_is_valid(self) -> None:
        """CorrectionType.SPELLING is a permitted correction type."""
        req = CorrectionSubmitRequest(
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )
        assert req.correction_type == CorrectionType.SPELLING

    def test_correction_type_profanity_fix_is_valid(self) -> None:
        """CorrectionType.PROFANITY_FIX is a permitted correction type."""
        req = CorrectionSubmitRequest(
            corrected_text="[censored]",
            correction_type=CorrectionType.PROFANITY_FIX,
        )
        assert req.correction_type == CorrectionType.PROFANITY_FIX

    def test_correction_type_context_correction_is_valid(self) -> None:
        """CorrectionType.CONTEXT_CORRECTION is a permitted correction type."""
        req = CorrectionSubmitRequest(
            corrected_text="better context",
            correction_type=CorrectionType.CONTEXT_CORRECTION,
        )
        assert req.correction_type == CorrectionType.CONTEXT_CORRECTION

    def test_correction_type_formatting_is_valid(self) -> None:
        """CorrectionType.FORMATTING is a permitted correction type."""
        req = CorrectionSubmitRequest(
            corrected_text="Properly. Formatted.",
            correction_type=CorrectionType.FORMATTING,
        )
        assert req.correction_type == CorrectionType.FORMATTING

    def test_correction_type_asr_error_is_valid(self) -> None:
        """CorrectionType.ASR_ERROR is a permitted correction type."""
        req = CorrectionSubmitRequest(
            corrected_text="speech recognition fix",
            correction_type=CorrectionType.ASR_ERROR,
        )
        assert req.correction_type == CorrectionType.ASR_ERROR

    def test_missing_corrected_text_raises_validation_error(self) -> None:
        """Omitting the required corrected_text field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(  # type: ignore[call-arg]
                correction_type=CorrectionType.SPELLING,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("corrected_text",) for e in errors)

    def test_missing_correction_type_raises_validation_error(self) -> None:
        """Omitting the required correction_type field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(  # type: ignore[call-arg]
                corrected_text="some text",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("correction_type",) for e in errors)

    def test_corrected_by_user_id_exceeds_max_length_raises_validation_error(
        self,
    ) -> None:
        """corrected_by_user_id longer than 100 characters raises ValidationError."""
        long_user_id = "u" * 101  # 101 chars — one over the limit

        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitRequest(
                corrected_text="some text",
                correction_type=CorrectionType.SPELLING,
                corrected_by_user_id=long_user_id,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("corrected_by_user_id",) for e in errors)
        assert any(e["type"] == "string_too_long" for e in errors)

    def test_corrected_by_user_id_at_max_length_is_accepted(self) -> None:
        """corrected_by_user_id of exactly 100 characters is accepted."""
        exact_user_id = "u" * 100

        req = CorrectionSubmitRequest(
            corrected_text="some text",
            correction_type=CorrectionType.SPELLING,
            corrected_by_user_id=exact_user_id,
        )

        assert req.corrected_by_user_id == exact_user_id


# ---------------------------------------------------------------------------
# TestCorrectionAuditRecord
# ---------------------------------------------------------------------------


class TestCorrectionAuditRecord:
    """Tests for CorrectionAuditRecord schema."""

    def test_valid_construction_from_dict_all_fields(self) -> None:
        """CorrectionAuditRecord is constructible from a complete dict."""
        record_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        record = CorrectionAuditRecord(
            id=record_id,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=3,
            correction_type=CorrectionType.CONTEXT_CORRECTION,
            original_text="original segment text",
            corrected_text="corrected segment text",
            correction_note="Context was wrong",
            corrected_by_user_id="reviewer_99",
            corrected_at=now,
            version_number=2,
        )

        assert record.id == record_id
        assert record.video_id == "dQw4w9WgXcQ"
        assert record.language_code == "en"
        assert record.segment_id == 3
        assert record.correction_type == CorrectionType.CONTEXT_CORRECTION
        assert record.original_text == "original segment text"
        assert record.corrected_text == "corrected segment text"
        assert record.correction_note == "Context was wrong"
        assert record.corrected_by_user_id == "reviewer_99"
        assert record.corrected_at == now
        assert record.version_number == 2

    def test_from_attributes_orm_like_object_mapping(self) -> None:
        """CorrectionAuditRecord.model_validate maps attribute-based objects.

        ConfigDict(from_attributes=True) allows construction from objects
        that expose fields as attributes (e.g., SQLAlchemy ORM row proxies).
        SimpleNamespace is used here as a lightweight stand-in.
        """
        record_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        orm_like = SimpleNamespace(
            id=record_id,
            video_id="abc123",
            language_code="es",
            segment_id=15,
            correction_type=CorrectionType.SPELLING,
            original_text="teh",
            corrected_text="the",
            correction_note=None,
            corrected_by_user_id=None,
            corrected_at=now,
            version_number=1,
        )

        record = CorrectionAuditRecord.model_validate(orm_like)

        assert record.id == record_id
        assert record.video_id == "abc123"
        assert record.language_code == "es"
        assert record.segment_id == 15
        assert record.correction_type == CorrectionType.SPELLING
        assert record.original_text == "teh"
        assert record.corrected_text == "the"
        assert record.correction_note is None
        assert record.corrected_by_user_id is None
        assert record.corrected_at == now
        assert record.version_number == 1

    def test_segment_id_none_is_allowed(self) -> None:
        """segment_id is nullable; None must be accepted without error."""
        record = _make_audit_record(segment_id=None)

        assert record.segment_id is None

    def test_segment_id_integer_is_stored(self) -> None:
        """segment_id stores integer values when provided."""
        record = _make_audit_record(segment_id=42)

        assert record.segment_id == 42

    def test_correction_note_none_is_allowed(self) -> None:
        """correction_note is nullable; None must be accepted without error."""
        record = _make_audit_record(correction_note=None)

        assert record.correction_note is None

    def test_corrected_by_user_id_none_is_allowed(self) -> None:
        """corrected_by_user_id is nullable; None must be accepted without error."""
        record = _make_audit_record(corrected_by_user_id=None)

        assert record.corrected_by_user_id is None

    def test_all_correction_types_accepted(self) -> None:
        """Every CorrectionType value (including REVERT) is valid in the record.

        Unlike CorrectionSubmitRequest, CorrectionAuditRecord has no validator
        that blocks REVERT — it stores the historical audit entry verbatim.
        """
        for ct in CorrectionType:
            record = _make_audit_record(correction_type=ct)
            assert record.correction_type == ct


# ---------------------------------------------------------------------------
# TestSegmentCorrectionState
# ---------------------------------------------------------------------------


class TestSegmentCorrectionState:
    """Tests for SegmentCorrectionState schema."""

    def test_valid_construction_has_correction_true(self) -> None:
        """SegmentCorrectionState with has_correction=True is constructed correctly."""
        state = SegmentCorrectionState(
            has_correction=True,
            effective_text="the corrected segment text",
        )

        assert state.has_correction is True
        assert state.effective_text == "the corrected segment text"

    def test_valid_construction_has_correction_false(self) -> None:
        """SegmentCorrectionState with has_correction=False reflects original text."""
        state = SegmentCorrectionState(
            has_correction=False,
            effective_text="the original segment text",
        )

        assert state.has_correction is False
        assert state.effective_text == "the original segment text"

    def test_missing_has_correction_raises_validation_error(self) -> None:
        """Omitting has_correction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SegmentCorrectionState(  # type: ignore[call-arg]
                effective_text="some text",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("has_correction",) for e in errors)

    def test_missing_effective_text_raises_validation_error(self) -> None:
        """Omitting effective_text raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SegmentCorrectionState(  # type: ignore[call-arg]
                has_correction=True,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("effective_text",) for e in errors)


# ---------------------------------------------------------------------------
# TestCorrectionSubmitResponse
# ---------------------------------------------------------------------------


class TestCorrectionSubmitResponse:
    """Tests for CorrectionSubmitResponse schema."""

    def test_valid_construction_with_nested_models(self) -> None:
        """CorrectionSubmitResponse accepts nested CorrectionAuditRecord and state."""
        audit_record = _make_audit_record()
        segment_state = _make_segment_state()

        response = CorrectionSubmitResponse(
            correction=audit_record,
            segment_state=segment_state,
        )

        assert response.correction is audit_record
        assert response.segment_state is segment_state

    def test_correction_field_carries_audit_data(self) -> None:
        """Nested correction field exposes all audit record attributes."""
        record_id = uuid.uuid4()
        audit_record = _make_audit_record(
            id=record_id,
            video_id="testVideoId",
            correction_type=CorrectionType.PROFANITY_FIX,
            version_number=3,
        )
        response = CorrectionSubmitResponse(
            correction=audit_record,
            segment_state=_make_segment_state(),
        )

        assert response.correction.id == record_id
        assert response.correction.video_id == "testVideoId"
        assert response.correction.correction_type == CorrectionType.PROFANITY_FIX
        assert response.correction.version_number == 3

    def test_segment_state_field_carries_state_data(self) -> None:
        """Nested segment_state field exposes has_correction and effective_text."""
        response = CorrectionSubmitResponse(
            correction=_make_audit_record(),
            segment_state=_make_segment_state(
                has_correction=False,
                effective_text="reverted original",
            ),
        )

        assert response.segment_state.has_correction is False
        assert response.segment_state.effective_text == "reverted original"

    def test_missing_correction_field_raises_validation_error(self) -> None:
        """Omitting the correction field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitResponse(  # type: ignore[call-arg]
                segment_state=_make_segment_state(),
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("correction",) for e in errors)

    def test_missing_segment_state_field_raises_validation_error(self) -> None:
        """Omitting the segment_state field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionSubmitResponse(  # type: ignore[call-arg]
                correction=_make_audit_record(),
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("segment_state",) for e in errors)


# ---------------------------------------------------------------------------
# TestCorrectionRevertResponse
# ---------------------------------------------------------------------------


class TestCorrectionRevertResponse:
    """Tests for CorrectionRevertResponse type alias."""

    def test_revert_response_is_same_type_as_submit_response(self) -> None:
        """CorrectionRevertResponse is a type alias for CorrectionSubmitResponse.

        The alias is defined as:
            CorrectionRevertResponse = CorrectionSubmitResponse

        Both names must refer to exactly the same class object so that
        FastAPI serializes revert responses with the same schema.
        """
        assert CorrectionRevertResponse is CorrectionSubmitResponse

    def test_revert_response_constructs_identically(self) -> None:
        """Instances created via either name are the same class."""
        audit_record = _make_audit_record(correction_type=CorrectionType.REVERT)
        segment_state = _make_segment_state(
            has_correction=False,
            effective_text="reverted to original",
        )

        response = CorrectionRevertResponse(
            correction=audit_record,
            segment_state=segment_state,
        )

        assert isinstance(response, CorrectionSubmitResponse)
        assert response.correction.correction_type == CorrectionType.REVERT
        assert response.segment_state.has_correction is False
        assert response.segment_state.effective_text == "reverted to original"

    def test_revert_response_model_fields_match_submit_response(self) -> None:
        """Both names expose the same model_fields dict."""
        assert CorrectionRevertResponse.model_fields == CorrectionSubmitResponse.model_fields
