"""
Tests for batch correction Pydantic V2 result models (Feature 036).

Validates instantiation with valid data, default values, immutability
(frozen ConfigDict), and field constraints (ge=0, ge=1) for all six
batch correction models.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from chronovista.models.batch_correction_models import (
    BatchCorrectionResult,
    CorrectionExportRecord,
    CorrectionPattern,
    CorrectionStats,
    TypeCount,
    VideoCount,
)

# CRITICAL: Ensure async tests work with coverage tooling.
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_type_count(**overrides: Any) -> TypeCount:
    """Return a valid TypeCount with optional field overrides."""
    defaults: dict[str, Any] = {
        "correction_type": "spelling",
        "count": 5,
    }
    defaults.update(overrides)
    return TypeCount(**defaults)


def _make_video_count(**overrides: Any) -> VideoCount:
    """Return a valid VideoCount with optional field overrides."""
    defaults: dict[str, Any] = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "count": 12,
    }
    defaults.update(overrides)
    return VideoCount(**defaults)


def _make_batch_result(**overrides: Any) -> BatchCorrectionResult:
    """Return a valid BatchCorrectionResult with optional field overrides."""
    defaults: dict[str, Any] = {
        "total_scanned": 1000,
        "total_matched": 50,
        "total_applied": 45,
        "total_skipped": 3,
        "total_failed": 2,
        "failed_batches": 1,
        "unique_videos": 10,
    }
    defaults.update(overrides)
    return BatchCorrectionResult(**defaults)


def _make_export_record(**overrides: Any) -> CorrectionExportRecord:
    """Return a valid CorrectionExportRecord with optional field overrides."""
    defaults: dict[str, Any] = {
        "id": "0193a5e0-7b1a-7000-8000-000000000001",
        "video_id": "dQw4w9WgXcQ",
        "language_code": "en",
        "segment_id": 42,
        "correction_type": "spelling",
        "original_text": "teh quick brown fox",
        "corrected_text": "the quick brown fox",
        "correction_note": "Fixed typo",
        "corrected_by_user_id": "user_abc",
        "corrected_at": "2024-06-15T12:00:00Z",
        "version_number": 1,
    }
    defaults.update(overrides)
    return CorrectionExportRecord(**defaults)


def _make_correction_pattern(**overrides: Any) -> CorrectionPattern:
    """Return a valid CorrectionPattern with optional field overrides."""
    defaults: dict[str, Any] = {
        "original_text": "teh",
        "corrected_text": "the",
        "occurrences": 15,
        "remaining_matches": 3,
    }
    defaults.update(overrides)
    return CorrectionPattern(**defaults)


def _make_correction_stats(**overrides: Any) -> CorrectionStats:
    """Return a valid CorrectionStats with optional field overrides."""
    defaults: dict[str, Any] = {
        "total_corrections": 100,
        "total_reverts": 5,
        "unique_segments": 80,
        "unique_videos": 20,
        "by_type": [],
        "top_videos": [],
    }
    defaults.update(overrides)
    return CorrectionStats(**defaults)


# ---------------------------------------------------------------------------
# TypeCount tests
# ---------------------------------------------------------------------------


class TestTypeCount:
    """Tests for TypeCount model."""

    def test_valid_instantiation(self) -> None:
        """TypeCount can be instantiated with valid data."""
        tc = _make_type_count()
        assert tc.correction_type == "spelling"
        assert tc.count == 5

    def test_count_zero_is_accepted(self) -> None:
        """count == 0 is valid (boundary for ge=0)."""
        tc = _make_type_count(count=0)
        assert tc.count == 0

    def test_count_negative_raises_validation_error(self) -> None:
        """Negative count violates the ge=0 constraint."""
        with pytest.raises(ValidationError, match="count"):
            _make_type_count(count=-1)

    def test_frozen_rejects_mutation(self) -> None:
        """TypeCount is immutable (frozen=True)."""
        tc = _make_type_count()
        with pytest.raises(ValidationError):
            tc.count = 10

    def test_model_dump_returns_dict(self) -> None:
        """model_dump() produces a plain dict."""
        tc = _make_type_count()
        data = tc.model_dump()
        assert data == {"correction_type": "spelling", "count": 5}


# ---------------------------------------------------------------------------
# VideoCount tests
# ---------------------------------------------------------------------------


class TestVideoCount:
    """Tests for VideoCount model."""

    def test_valid_instantiation_with_title(self) -> None:
        """VideoCount can be instantiated with all fields."""
        vc = _make_video_count()
        assert vc.video_id == "dQw4w9WgXcQ"
        assert vc.title == "Never Gonna Give You Up"
        assert vc.count == 12

    def test_title_defaults_to_none(self) -> None:
        """title defaults to None when not provided."""
        vc = VideoCount(video_id="abc123", count=3)
        assert vc.title is None

    def test_title_explicit_none(self) -> None:
        """title can be explicitly set to None."""
        vc = _make_video_count(title=None)
        assert vc.title is None

    def test_count_zero_is_accepted(self) -> None:
        """count == 0 is valid (boundary for ge=0)."""
        vc = _make_video_count(count=0)
        assert vc.count == 0

    def test_count_negative_raises_validation_error(self) -> None:
        """Negative count violates the ge=0 constraint."""
        with pytest.raises(ValidationError, match="count"):
            _make_video_count(count=-1)

    def test_frozen_rejects_mutation(self) -> None:
        """VideoCount is immutable (frozen=True)."""
        vc = _make_video_count()
        with pytest.raises(ValidationError):
            vc.count = 99


# ---------------------------------------------------------------------------
# BatchCorrectionResult tests
# ---------------------------------------------------------------------------


class TestBatchCorrectionResult:
    """Tests for BatchCorrectionResult model."""

    def test_valid_instantiation(self) -> None:
        """BatchCorrectionResult can be instantiated with valid data."""
        result = _make_batch_result()
        assert result.total_scanned == 1000
        assert result.total_matched == 50
        assert result.total_applied == 45
        assert result.total_skipped == 3
        assert result.total_failed == 2
        assert result.failed_batches == 1
        assert result.unique_videos == 10

    def test_all_zeroes_is_valid(self) -> None:
        """All fields at zero is valid (boundary for ge=0)."""
        result = BatchCorrectionResult(
            total_scanned=0,
            total_matched=0,
            total_applied=0,
            total_skipped=0,
            total_failed=0,
            failed_batches=0,
            unique_videos=0,
        )
        assert result.total_scanned == 0
        assert result.total_matched == 0

    @pytest.mark.parametrize(
        "field_name",
        [
            "total_scanned",
            "total_matched",
            "total_applied",
            "total_skipped",
            "total_failed",
            "failed_batches",
            "unique_videos",
        ],
    )
    def test_negative_value_raises_validation_error(self, field_name: str) -> None:
        """Each int field rejects negative values (ge=0)."""
        with pytest.raises(ValidationError, match=field_name):
            _make_batch_result(**{field_name: -1})

    def test_frozen_rejects_mutation(self) -> None:
        """BatchCorrectionResult is immutable (frozen=True)."""
        result = _make_batch_result()
        with pytest.raises(ValidationError):
            result.total_applied = 999

    def test_model_dump_round_trip(self) -> None:
        """model_dump() output can reconstruct an equivalent model."""
        original = _make_batch_result()
        data = original.model_dump()
        reconstructed = BatchCorrectionResult(**data)
        assert reconstructed == original


# ---------------------------------------------------------------------------
# CorrectionExportRecord tests
# ---------------------------------------------------------------------------


class TestCorrectionExportRecord:
    """Tests for CorrectionExportRecord model."""

    def test_valid_instantiation_with_all_fields(self) -> None:
        """CorrectionExportRecord can be instantiated with all fields."""
        record = _make_export_record()
        assert record.id == "0193a5e0-7b1a-7000-8000-000000000001"
        assert record.video_id == "dQw4w9WgXcQ"
        assert record.language_code == "en"
        assert record.segment_id == 42
        assert record.correction_type == "spelling"
        assert record.original_text == "teh quick brown fox"
        assert record.corrected_text == "the quick brown fox"
        assert record.correction_note == "Fixed typo"
        assert record.corrected_by_user_id == "user_abc"
        assert record.corrected_at == "2024-06-15T12:00:00Z"
        assert record.version_number == 1

    def test_optional_fields_default_to_none(self) -> None:
        """segment_id, correction_note, corrected_by_user_id default to None."""
        record = CorrectionExportRecord(
            id="uuid-string",
            video_id="abc123",
            language_code="en",
            correction_type="spelling",
            original_text="old",
            corrected_text="new",
            corrected_at="2024-01-01T00:00:00Z",
            version_number=1,
        )
        assert record.segment_id is None
        assert record.correction_note is None
        assert record.corrected_by_user_id is None

    def test_version_number_minimum_boundary(self) -> None:
        """version_number == 1 (the minimum) is accepted."""
        record = _make_export_record(version_number=1)
        assert record.version_number == 1

    def test_version_number_zero_raises_validation_error(self) -> None:
        """version_number == 0 violates the ge=1 constraint."""
        with pytest.raises(ValidationError, match="version_number"):
            _make_export_record(version_number=0)

    def test_version_number_negative_raises_validation_error(self) -> None:
        """Negative version_number violates the ge=1 constraint."""
        with pytest.raises(ValidationError, match="version_number"):
            _make_export_record(version_number=-1)

    def test_frozen_rejects_mutation(self) -> None:
        """CorrectionExportRecord is immutable (frozen=True)."""
        record = _make_export_record()
        with pytest.raises(ValidationError):
            record.video_id = "new_id"

    def test_model_dump_round_trip(self) -> None:
        """model_dump() output can reconstruct an equivalent model."""
        original = _make_export_record()
        data = original.model_dump()
        reconstructed = CorrectionExportRecord(**data)
        assert reconstructed == original


# ---------------------------------------------------------------------------
# CorrectionPattern tests
# ---------------------------------------------------------------------------


class TestCorrectionPattern:
    """Tests for CorrectionPattern model."""

    def test_valid_instantiation(self) -> None:
        """CorrectionPattern can be instantiated with valid data."""
        pattern = _make_correction_pattern()
        assert pattern.original_text == "teh"
        assert pattern.corrected_text == "the"
        assert pattern.occurrences == 15
        assert pattern.remaining_matches == 3

    def test_occurrences_zero_is_accepted(self) -> None:
        """occurrences == 0 is valid (boundary for ge=0)."""
        pattern = _make_correction_pattern(occurrences=0)
        assert pattern.occurrences == 0

    def test_remaining_matches_zero_is_accepted(self) -> None:
        """remaining_matches == 0 is valid (boundary for ge=0)."""
        pattern = _make_correction_pattern(remaining_matches=0)
        assert pattern.remaining_matches == 0

    def test_occurrences_negative_raises_validation_error(self) -> None:
        """Negative occurrences violates the ge=0 constraint."""
        with pytest.raises(ValidationError, match="occurrences"):
            _make_correction_pattern(occurrences=-1)

    def test_remaining_matches_negative_raises_validation_error(self) -> None:
        """Negative remaining_matches violates the ge=0 constraint."""
        with pytest.raises(ValidationError, match="remaining_matches"):
            _make_correction_pattern(remaining_matches=-1)

    def test_frozen_rejects_mutation(self) -> None:
        """CorrectionPattern is immutable (frozen=True)."""
        pattern = _make_correction_pattern()
        with pytest.raises(ValidationError):
            pattern.occurrences = 999


# ---------------------------------------------------------------------------
# CorrectionStats tests
# ---------------------------------------------------------------------------


class TestCorrectionStats:
    """Tests for CorrectionStats model."""

    def test_valid_instantiation_with_defaults(self) -> None:
        """CorrectionStats can be instantiated; by_type and top_videos default to []."""
        stats = CorrectionStats(
            total_corrections=100,
            total_reverts=5,
            unique_segments=80,
            unique_videos=20,
        )
        assert stats.total_corrections == 100
        assert stats.total_reverts == 5
        assert stats.unique_segments == 80
        assert stats.unique_videos == 20
        assert stats.by_type == []
        assert stats.top_videos == []

    def test_valid_instantiation_with_nested_models(self) -> None:
        """CorrectionStats accepts populated by_type and top_videos lists."""
        stats = _make_correction_stats(
            by_type=[
                TypeCount(correction_type="spelling", count=50),
                TypeCount(correction_type="asr_error", count=30),
            ],
            top_videos=[
                VideoCount(video_id="vid1", title="Video One", count=25),
                VideoCount(video_id="vid2", title=None, count=10),
            ],
        )
        assert len(stats.by_type) == 2
        assert stats.by_type[0].correction_type == "spelling"
        assert stats.by_type[0].count == 50
        assert len(stats.top_videos) == 2
        assert stats.top_videos[1].title is None

    def test_all_zeroes_is_valid(self) -> None:
        """All int fields at zero is valid (boundary for ge=0)."""
        stats = CorrectionStats(
            total_corrections=0,
            total_reverts=0,
            unique_segments=0,
            unique_videos=0,
        )
        assert stats.total_corrections == 0

    @pytest.mark.parametrize(
        "field_name",
        [
            "total_corrections",
            "total_reverts",
            "unique_segments",
            "unique_videos",
        ],
    )
    def test_negative_value_raises_validation_error(self, field_name: str) -> None:
        """Each int field rejects negative values (ge=0)."""
        with pytest.raises(ValidationError, match=field_name):
            _make_correction_stats(**{field_name: -1})

    def test_frozen_rejects_mutation(self) -> None:
        """CorrectionStats is immutable (frozen=True)."""
        stats = _make_correction_stats()
        with pytest.raises(ValidationError):
            stats.total_corrections = 999

    def test_frozen_rejects_list_assignment(self) -> None:
        """CorrectionStats rejects assignment to list fields (frozen=True)."""
        stats = _make_correction_stats()
        with pytest.raises(ValidationError):
            stats.by_type = []

    def test_model_dump_round_trip(self) -> None:
        """model_dump() output can reconstruct an equivalent model."""
        original = _make_correction_stats(
            by_type=[TypeCount(correction_type="spelling", count=10)],
            top_videos=[VideoCount(video_id="v1", title="T", count=5)],
        )
        data = original.model_dump()
        reconstructed = CorrectionStats(**data)
        assert reconstructed == original

    def test_nested_models_are_also_frozen(self) -> None:
        """Nested TypeCount and VideoCount instances are also immutable."""
        stats = _make_correction_stats(
            by_type=[TypeCount(correction_type="spelling", count=10)],
            top_videos=[VideoCount(video_id="v1", title="T", count=5)],
        )
        with pytest.raises(ValidationError):
            stats.by_type[0].count = 999
        with pytest.raises(ValidationError):
            stats.top_videos[0].count = 999
