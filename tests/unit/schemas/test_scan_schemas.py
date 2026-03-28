"""
Unit tests for ScanRequest, ScanResultData, and ScanResultResponse schemas.

Covers Feature 052 — Targeted Entity & Video-Level Mention Scanning.

Tests:
- ScanRequest defaults (all None/False)
- ScanRequest entity_type validation against EntityType enum values
- ScanRequest rejects invalid entity_type strings
- ScanResultData field construction and all required fields
- ScanResultResponse wraps ScanResultData inside ``data`` key
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chronovista.api.schemas.entity_mentions import (
    ScanRequest,
    ScanResultData,
    ScanResultResponse,
)
from chronovista.models.enums import EntityType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan_result_data(**overrides: object) -> ScanResultData:
    """Build a valid ScanResultData with sensible defaults."""
    defaults: dict[str, object] = {
        "segments_scanned": 100,
        "mentions_found": 5,
        "mentions_skipped": 2,
        "unique_entities": 3,
        "unique_videos": 2,
        "duration_seconds": 1.23,
        "dry_run": False,
    }
    defaults.update(overrides)
    return ScanResultData(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestScanRequestDefaults
# ---------------------------------------------------------------------------


class TestScanRequestDefaults:
    """ScanRequest should default all fields to None/False when constructed empty."""

    def test_empty_body_produces_none_language_code(self) -> None:
        """ScanRequest() default: language_code is None."""
        req = ScanRequest()
        assert req.language_code is None

    def test_empty_body_produces_none_entity_type(self) -> None:
        """ScanRequest() default: entity_type is None."""
        req = ScanRequest()
        assert req.entity_type is None

    def test_empty_body_produces_false_dry_run(self) -> None:
        """ScanRequest() default: dry_run is False."""
        req = ScanRequest()
        assert req.dry_run is False

    def test_empty_body_produces_false_full_rescan(self) -> None:
        """ScanRequest() default: full_rescan is False."""
        req = ScanRequest()
        assert req.full_rescan is False

    def test_all_defaults_in_one_call(self) -> None:
        """All defaults hold simultaneously in a single ScanRequest()."""
        req = ScanRequest()
        assert req.language_code is None
        assert req.entity_type is None
        assert req.dry_run is False
        assert req.full_rescan is False

    def test_empty_dict_also_uses_defaults(self) -> None:
        """ScanRequest(**{}) must behave identically to ScanRequest()."""
        req = ScanRequest(**{})
        assert req.language_code is None
        assert req.entity_type is None
        assert req.dry_run is False
        assert req.full_rescan is False


# ---------------------------------------------------------------------------
# TestScanRequestEntityTypeValidation
# ---------------------------------------------------------------------------


class TestScanRequestEntityTypeValidation:
    """ScanRequest.entity_type must only accept valid EntityType enum values."""

    def test_valid_person_type(self) -> None:
        """entity_type='person' must be accepted."""
        req = ScanRequest(entity_type="person")
        assert req.entity_type == "person"

    def test_valid_organization_type(self) -> None:
        """entity_type='organization' must be accepted."""
        req = ScanRequest(entity_type="organization")
        assert req.entity_type == "organization"

    def test_valid_place_type(self) -> None:
        """entity_type='place' must be accepted."""
        req = ScanRequest(entity_type="place")
        assert req.entity_type == "place"

    def test_valid_event_type(self) -> None:
        """entity_type='event' must be accepted."""
        req = ScanRequest(entity_type="event")
        assert req.entity_type == "event"

    def test_valid_work_type(self) -> None:
        """entity_type='work' must be accepted."""
        req = ScanRequest(entity_type="work")
        assert req.entity_type == "work"

    def test_valid_technical_term_type(self) -> None:
        """entity_type='technical_term' must be accepted."""
        req = ScanRequest(entity_type="technical_term")
        assert req.entity_type == "technical_term"

    def test_valid_topic_type(self) -> None:
        """entity_type='topic' must be accepted (valid in ScanRequest)."""
        req = ScanRequest(entity_type="topic")
        assert req.entity_type == "topic"

    def test_valid_descriptor_type(self) -> None:
        """entity_type='descriptor' must be accepted (valid in ScanRequest)."""
        req = ScanRequest(entity_type="descriptor")
        assert req.entity_type == "descriptor"

    def test_valid_concept_type(self) -> None:
        """entity_type='concept' must be accepted."""
        req = ScanRequest(entity_type="concept")
        assert req.entity_type == "concept"

    def test_valid_other_type(self) -> None:
        """entity_type='other' must be accepted."""
        req = ScanRequest(entity_type="other")
        assert req.entity_type == "other"

    def test_all_entity_type_enum_values_are_valid(self) -> None:
        """Every EntityType enum value must be accepted by ScanRequest."""
        for entity_type in EntityType:
            req = ScanRequest(entity_type=entity_type.value)
            assert req.entity_type == entity_type.value

    def test_none_entity_type_is_valid(self) -> None:
        """entity_type=None must be accepted (default/no filter)."""
        req = ScanRequest(entity_type=None)
        assert req.entity_type is None

    def test_invalid_entity_type_raises_validation_error(self) -> None:
        """An unrecognized entity_type string must raise ValidationError."""
        with pytest.raises(ValidationError):
            ScanRequest(entity_type="dinosaur")

    def test_empty_string_entity_type_raises_validation_error(self) -> None:
        """An empty string entity_type must raise ValidationError."""
        with pytest.raises(ValidationError):
            ScanRequest(entity_type="")

    def test_uppercase_entity_type_raises_validation_error(self) -> None:
        """'PERSON' (uppercase) must be rejected (validator is case-sensitive)."""
        with pytest.raises(ValidationError):
            ScanRequest(entity_type="PERSON")

    def test_partial_entity_type_raises_validation_error(self) -> None:
        """A partial match like 'per' must be rejected."""
        with pytest.raises(ValidationError):
            ScanRequest(entity_type="per")

    def test_whitespace_padded_entity_type_raises_validation_error(self) -> None:
        """'person ' (trailing space) must be rejected."""
        with pytest.raises(ValidationError):
            ScanRequest(entity_type="person ")


# ---------------------------------------------------------------------------
# TestScanRequestFieldAssignment
# ---------------------------------------------------------------------------


class TestScanRequestFieldAssignment:
    """ScanRequest should accept valid field assignments."""

    def test_language_code_assigned(self) -> None:
        """language_code='en' must be stored."""
        req = ScanRequest(language_code="en")
        assert req.language_code == "en"

    def test_dry_run_true(self) -> None:
        """dry_run=True must be stored."""
        req = ScanRequest(dry_run=True)
        assert req.dry_run is True

    def test_full_rescan_true(self) -> None:
        """full_rescan=True must be stored."""
        req = ScanRequest(full_rescan=True)
        assert req.full_rescan is True

    def test_all_fields_assigned_simultaneously(self) -> None:
        """All four fields can be set at the same time."""
        req = ScanRequest(
            language_code="fr",
            entity_type="person",
            dry_run=True,
            full_rescan=True,
        )
        assert req.language_code == "fr"
        assert req.entity_type == "person"
        assert req.dry_run is True
        assert req.full_rescan is True


# ---------------------------------------------------------------------------
# TestScanResultData
# ---------------------------------------------------------------------------


class TestScanResultData:
    """ScanResultData construction and field requirements."""

    def test_valid_construction_with_all_fields(self) -> None:
        """ScanResultData must construct successfully with all required fields."""
        data = _make_scan_result_data()
        assert data.segments_scanned == 100
        assert data.mentions_found == 5
        assert data.mentions_skipped == 2
        assert data.unique_entities == 3
        assert data.unique_videos == 2
        assert data.duration_seconds == pytest.approx(1.23)
        assert data.dry_run is False

    def test_dry_run_true_stored(self) -> None:
        """dry_run=True must be stored in ScanResultData."""
        data = _make_scan_result_data(dry_run=True)
        assert data.dry_run is True

    def test_zero_counts_are_valid(self) -> None:
        """All count fields may be zero (empty scan result)."""
        data = _make_scan_result_data(
            segments_scanned=0,
            mentions_found=0,
            mentions_skipped=0,
            unique_entities=0,
            unique_videos=0,
            duration_seconds=0.0,
        )
        assert data.segments_scanned == 0
        assert data.mentions_found == 0
        assert data.unique_entities == 0

    def test_missing_segments_scanned_raises_validation_error(self) -> None:
        """Omitting required segments_scanned must raise ValidationError."""
        with pytest.raises(ValidationError):
            ScanResultData(  # type: ignore[call-arg]
                mentions_found=0,
                mentions_skipped=0,
                unique_entities=0,
                unique_videos=0,
                duration_seconds=0.0,
                dry_run=False,
            )

    def test_missing_dry_run_raises_validation_error(self) -> None:
        """Omitting required dry_run must raise ValidationError."""
        with pytest.raises(ValidationError):
            ScanResultData(  # type: ignore[call-arg]
                segments_scanned=1,
                mentions_found=0,
                mentions_skipped=0,
                unique_entities=0,
                unique_videos=0,
                duration_seconds=0.0,
            )

    def test_large_count_values_stored(self) -> None:
        """Large integer values must be stored without overflow."""
        data = _make_scan_result_data(
            segments_scanned=1_000_000,
            mentions_found=500_000,
            unique_videos=10_000,
        )
        assert data.segments_scanned == 1_000_000


# ---------------------------------------------------------------------------
# TestScanResultResponse
# ---------------------------------------------------------------------------


class TestScanResultResponse:
    """ScanResultResponse wraps ScanResultData under the ``data`` key."""

    def test_data_field_contains_scan_result_data(self) -> None:
        """ScanResultResponse.data must be a ScanResultData instance."""
        inner = _make_scan_result_data()
        resp = ScanResultResponse(data=inner)
        assert isinstance(resp.data, ScanResultData)

    def test_data_values_accessible(self) -> None:
        """Values in ScanResultData must be accessible via ScanResultResponse.data."""
        inner = _make_scan_result_data(mentions_found=42, unique_entities=7)
        resp = ScanResultResponse(data=inner)
        assert resp.data.mentions_found == 42
        assert resp.data.unique_entities == 7

    def test_missing_data_field_raises_validation_error(self) -> None:
        """Omitting the required data field must raise ValidationError."""
        with pytest.raises(ValidationError):
            ScanResultResponse()  # type: ignore[call-arg]

    def test_model_json_round_trip(self) -> None:
        """ScanResultResponse must survive JSON serialisation and deserialisation."""
        inner = _make_scan_result_data(segments_scanned=50, dry_run=True)
        resp = ScanResultResponse(data=inner)
        json_str = resp.model_dump_json()
        parsed = ScanResultResponse.model_validate_json(json_str)
        assert parsed.data.segments_scanned == 50
        assert parsed.data.dry_run is True
