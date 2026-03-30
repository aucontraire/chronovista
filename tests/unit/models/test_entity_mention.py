"""
Tests for EntityMention Pydantic domain models and DetectionMethod enum.

Validates field constraints, enum enforcement, confidence range validation,
mention_text length boundaries, ORM compatibility, and model serialisation
for EntityMentionBase, EntityMentionCreate, and EntityMention models
(Feature 038 — Entity Mention Detection).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from uuid_utils import uuid7 as _uuid7_raw

from chronovista.models.entity_mention import (
    EntityMention,
    EntityMentionBase,
    EntityMentionCreate,
)
from chronovista.models.enums import DetectionMethod
from tests.factories.entity_mention_factory import (
    EntityMentionFactory,
    EntityMentionTestData,
    create_entity_mention,
    create_entity_mention_base,
    create_entity_mention_create,
)

# CRITICAL: Ensure async tests work with coverage tooling.
# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_VALID_VIDEO_ID = "dQw4w9WgXcQ"
_VALID_LANGUAGE_CODE = "en"
_VALID_MENTION_TEXT = "Elon Musk"


def _uuid7() -> uuid.UUID:
    """Generate a standard uuid.UUID from UUIDv7 bytes."""
    return uuid.UUID(bytes=_uuid7_raw().bytes)


def _make_entity_mention_base(**overrides: Any) -> EntityMentionBase:
    """Return a valid EntityMentionBase with optional field overrides.

    Parameters
    ----------
    **overrides : Any
        Any field values to override on top of sensible defaults.

    Returns
    -------
    EntityMentionBase
        A fully-populated base model.
    """
    defaults: dict[str, Any] = {
        "entity_id": _uuid7(),
        "segment_id": 1,
        "video_id": _VALID_VIDEO_ID,
        "language_code": _VALID_LANGUAGE_CODE,
        "mention_text": _VALID_MENTION_TEXT,
        "detection_method": DetectionMethod.RULE_MATCH,
        "confidence": 1.0,
    }
    defaults.update(overrides)
    return EntityMentionBase(**defaults)


def _make_entity_mention(**overrides: Any) -> EntityMention:
    """Return a valid EntityMention (full read model) with optional field overrides.

    Parameters
    ----------
    **overrides : Any
        Any field values to override on top of sensible defaults.

    Returns
    -------
    EntityMention
        A fully-populated read model with database-side fields.
    """
    defaults: dict[str, Any] = {
        "id": _uuid7(),
        "entity_id": _uuid7(),
        "segment_id": 1,
        "video_id": _VALID_VIDEO_ID,
        "language_code": _VALID_LANGUAGE_CODE,
        "mention_text": _VALID_MENTION_TEXT,
        "detection_method": DetectionMethod.RULE_MATCH,
        "confidence": 1.0,
        "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return EntityMention(**defaults)


# ===========================================================================
# T008 — DetectionMethod Enum Tests
# ===========================================================================


class TestDetectionMethodEnum:
    """Tests for the DetectionMethod enum (T008).

    Verifies that all 4 enum members exist with their expected string values,
    that DetectionMethod inherits from both str and Enum, and that string
    coercion (via Pydantic model fields) works correctly.
    """

    # -----------------------------------------------------------------------
    # Membership and value tests
    # -----------------------------------------------------------------------

    def test_rule_match_value(self) -> None:
        """DetectionMethod.RULE_MATCH has value 'rule_match'."""
        assert DetectionMethod.RULE_MATCH.value == "rule_match"

    def test_spacy_ner_value(self) -> None:
        """DetectionMethod.SPACY_NER has value 'spacy_ner'."""
        assert DetectionMethod.SPACY_NER.value == "spacy_ner"

    def test_llm_extraction_value(self) -> None:
        """DetectionMethod.LLM_EXTRACTION has value 'llm_extraction'."""
        assert DetectionMethod.LLM_EXTRACTION.value == "llm_extraction"

    def test_manual_value(self) -> None:
        """DetectionMethod.MANUAL has value 'manual'."""
        assert DetectionMethod.MANUAL.value == "manual"

    def test_exactly_five_members(self) -> None:
        """DetectionMethod has exactly 5 members — no accidental additions."""
        assert len(DetectionMethod) == 5

    def test_all_five_members_are_present(self) -> None:
        """All five expected DetectionMethod members exist in the enum."""
        members = set(DetectionMethod)
        assert DetectionMethod.RULE_MATCH in members
        assert DetectionMethod.SPACY_NER in members
        assert DetectionMethod.LLM_EXTRACTION in members
        assert DetectionMethod.MANUAL in members
        assert DetectionMethod.USER_CORRECTION in members

    # -----------------------------------------------------------------------
    # Inheritance: DetectionMethod is both str and Enum
    # -----------------------------------------------------------------------

    def test_detection_method_is_str_subclass(self) -> None:
        """DetectionMethod is a subclass of str."""
        assert issubclass(DetectionMethod, str)

    def test_each_member_is_str_instance(self) -> None:
        """Every DetectionMethod member is an instance of str."""
        for member in DetectionMethod:
            assert isinstance(member, str), f"{member!r} is not a str instance"

    def test_each_member_is_enum_instance(self) -> None:
        """Every DetectionMethod member is an instance of DetectionMethod."""
        for member in DetectionMethod:
            assert isinstance(
                member, DetectionMethod
            ), f"{member!r} is not a DetectionMethod instance"

    # -----------------------------------------------------------------------
    # String coercion via Pydantic
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "raw_value, expected_member",
        [
            ("rule_match", DetectionMethod.RULE_MATCH),
            ("spacy_ner", DetectionMethod.SPACY_NER),
            ("llm_extraction", DetectionMethod.LLM_EXTRACTION),
            ("manual", DetectionMethod.MANUAL),
        ],
        ids=["rule_match", "spacy_ner", "llm_extraction", "manual"],
    )
    def test_string_coercion_via_pydantic_field(
        self, raw_value: str, expected_member: DetectionMethod
    ) -> None:
        """Pydantic coerces plain strings to DetectionMethod enum members.

        Notes
        -----
        EntityMentionBase uses a DetectionMethod field, so this test exercises
        that the Pydantic integration correctly round-trips string → enum.
        """
        mention = _make_entity_mention_base(detection_method=raw_value)
        assert mention.detection_method == expected_member
        assert isinstance(mention.detection_method, DetectionMethod)

    def test_invalid_string_raises_validation_error_via_pydantic(self) -> None:
        """An unrecognised string value for detection_method raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(detection_method="nonexistent_method")

    def test_enum_members_compare_equal_to_their_string_values(self) -> None:
        """DetectionMethod members compare equal to their raw string values (str inheritance)."""
        assert DetectionMethod.RULE_MATCH.value == "rule_match"
        assert DetectionMethod.SPACY_NER.value == "spacy_ner"
        assert DetectionMethod.LLM_EXTRACTION.value == "llm_extraction"
        assert DetectionMethod.MANUAL.value == "manual"

    def test_detection_method_lookup_by_value(self) -> None:
        """DetectionMethod can be retrieved by its string value."""
        assert DetectionMethod("rule_match") is DetectionMethod.RULE_MATCH
        assert DetectionMethod("spacy_ner") is DetectionMethod.SPACY_NER
        assert DetectionMethod("llm_extraction") is DetectionMethod.LLM_EXTRACTION
        assert DetectionMethod("manual") is DetectionMethod.MANUAL


# ===========================================================================
# T007 — EntityMentionBase Tests
# ===========================================================================


class TestEntityMentionBase:
    """Tests for EntityMentionBase Pydantic model validation (T007)."""

    # -----------------------------------------------------------------------
    # Valid creation scenarios
    # -----------------------------------------------------------------------

    def test_valid_data_creates_model_successfully(self) -> None:
        """EntityMentionBase is created without error when all fields are valid."""
        entity_id = _uuid7()
        mention = EntityMentionBase(
            entity_id=entity_id,
            segment_id=42,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Elon Musk",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=0.95,
        )

        assert mention.entity_id == entity_id
        assert mention.segment_id == 42
        assert mention.video_id == _VALID_VIDEO_ID
        assert mention.language_code == "en"
        assert mention.mention_text == "Elon Musk"
        assert mention.detection_method == DetectionMethod.RULE_MATCH
        assert mention.confidence == 0.95

    def test_valid_data_using_factory_defaults(self) -> None:
        """Factory-built EntityMentionBase has valid default field values."""
        mention = create_entity_mention_base()

        assert isinstance(mention.entity_id, uuid.UUID)
        assert isinstance(mention.segment_id, int)
        assert mention.segment_id >= 1
        assert len(mention.video_id) == 11
        assert mention.language_code is not None and len(mention.language_code) >= 2
        assert len(mention.mention_text) >= 1
        assert mention.detection_method == DetectionMethod.RULE_MATCH
        assert mention.confidence == 1.0

    def test_valid_data_with_all_detection_methods(self) -> None:
        """EntityMentionBase accepts all four DetectionMethod values."""
        for method in DetectionMethod:
            mention = _make_entity_mention_base(detection_method=method)
            assert mention.detection_method == method

    # -----------------------------------------------------------------------
    # entity_id — must be a valid UUID
    # -----------------------------------------------------------------------

    def test_entity_id_accepts_uuid_instance(self) -> None:
        """entity_id accepts a uuid.UUID instance."""
        entity_id = _uuid7()
        mention = _make_entity_mention_base(entity_id=entity_id)
        assert mention.entity_id == entity_id
        assert isinstance(mention.entity_id, uuid.UUID)

    def test_entity_id_accepts_uuid_string(self) -> None:
        """entity_id accepts a UUID formatted as a string (Pydantic coerces it)."""
        entity_id = _uuid7()
        mention = _make_entity_mention_base(entity_id=str(entity_id))
        assert mention.entity_id == entity_id

    # -----------------------------------------------------------------------
    # video_id — VideoId type (exactly 11 chars, alphanumeric/hyphen/underscore)
    # -----------------------------------------------------------------------

    def test_video_id_valid_11_char_alphanumeric(self) -> None:
        """video_id accepts a valid 11-character alphanumeric string."""
        mention = _make_entity_mention_base(video_id="dQw4w9WgXcQ")
        assert mention.video_id == "dQw4w9WgXcQ"

    def test_video_id_valid_with_hyphen_and_underscore(self) -> None:
        """video_id accepts 11-char strings containing hyphens and underscores."""
        mention = _make_entity_mention_base(video_id="abc-def_ghi")
        assert mention.video_id == "abc-def_ghi"

    def test_video_id_too_short_raises_validation_error(self) -> None:
        """video_id with fewer than 11 chars raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(video_id="short")

    def test_video_id_too_long_raises_validation_error(self) -> None:
        """video_id with more than 11 chars raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(video_id="dQw4w9WgXcQ_extra")

    def test_video_id_empty_raises_validation_error(self) -> None:
        """Empty video_id raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(video_id="")

    def test_video_id_with_invalid_characters_raises_validation_error(self) -> None:
        """video_id with special characters (not alphanumeric/hyphen/underscore) raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(video_id="abc!@#$%^&*")

    # -----------------------------------------------------------------------
    # confidence — float in [0.0, 1.0] with default of 1.0
    # -----------------------------------------------------------------------

    def test_confidence_defaults_to_none(self) -> None:
        """confidence defaults to None when not supplied."""
        entity_id = _uuid7()
        mention = EntityMentionBase(
            entity_id=entity_id,
            segment_id=1,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Elon Musk",
        )
        assert mention.confidence is None

    def test_confidence_boundary_zero_is_accepted(self) -> None:
        """confidence == 0.0 (lower bound) is accepted."""
        mention = _make_entity_mention_base(confidence=0.0)
        assert mention.confidence == 0.0

    def test_confidence_boundary_one_is_accepted(self) -> None:
        """confidence == 1.0 (upper bound) is accepted."""
        mention = _make_entity_mention_base(confidence=1.0)
        assert mention.confidence == 1.0

    def test_confidence_midpoint_is_accepted(self) -> None:
        """confidence == 0.5 (midpoint) is accepted."""
        mention = _make_entity_mention_base(confidence=0.5)
        assert mention.confidence == 0.5

    def test_confidence_below_zero_raises_validation_error(self) -> None:
        """confidence < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(confidence=-0.001)

    def test_confidence_above_one_raises_validation_error(self) -> None:
        """confidence > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(confidence=1.001)

    def test_confidence_negative_one_raises_validation_error(self) -> None:
        """confidence == -1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(confidence=-1.0)

    def test_confidence_two_raises_validation_error(self) -> None:
        """confidence == 2.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(confidence=2.0)

    # -----------------------------------------------------------------------
    # detection_method — defaults to RULE_MATCH
    # -----------------------------------------------------------------------

    def test_detection_method_defaults_to_rule_match(self) -> None:
        """detection_method defaults to DetectionMethod.RULE_MATCH when not supplied."""
        entity_id = _uuid7()
        mention = EntityMentionBase(
            entity_id=entity_id,
            segment_id=1,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Elon Musk",
        )
        assert mention.detection_method == DetectionMethod.RULE_MATCH

    def test_detection_method_is_detection_method_instance(self) -> None:
        """detection_method field holds a DetectionMethod enum instance."""
        mention = _make_entity_mention_base()
        assert isinstance(mention.detection_method, DetectionMethod)

    # -----------------------------------------------------------------------
    # mention_text — 1 to 500 characters
    # -----------------------------------------------------------------------

    def test_mention_text_single_char_is_accepted(self) -> None:
        """mention_text of exactly 1 character (minimum) is accepted."""
        mention = _make_entity_mention_base(mention_text="A")
        assert mention.mention_text == "A"

    def test_mention_text_500_chars_is_accepted(self) -> None:
        """mention_text of exactly 500 characters (maximum) is accepted."""
        long_text = "x" * 500
        mention = _make_entity_mention_base(mention_text=long_text)
        assert mention.mention_text == long_text
        assert len(mention.mention_text) == 500

    def test_mention_text_empty_string_raises_validation_error(self) -> None:
        """Empty mention_text (below min_length=1) raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(mention_text="")

    def test_mention_text_501_chars_raises_validation_error(self) -> None:
        """mention_text of 501 characters (above max_length=500) raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(mention_text="x" * 501)

    def test_mention_text_typical_entity_name(self) -> None:
        """mention_text accepts typical entity names."""
        for name in ["Google", "New York City", "Python", "Machine Learning"]:
            mention = _make_entity_mention_base(mention_text=name)
            assert mention.mention_text == name

    # -----------------------------------------------------------------------
    # language_code — 2 to 10 characters
    # -----------------------------------------------------------------------

    def test_language_code_two_chars_is_accepted(self) -> None:
        """language_code of exactly 2 characters (minimum) is accepted."""
        mention = _make_entity_mention_base(language_code="en")
        assert mention.language_code == "en"

    def test_language_code_10_chars_is_accepted(self) -> None:
        """language_code of exactly 10 characters (maximum) is accepted."""
        # A valid BCP-47 code that is 10 chars or fewer
        mention = _make_entity_mention_base(language_code="zh-Hans-CN")
        assert mention.language_code == "zh-Hans-CN"

    def test_language_code_single_char_is_accepted(self) -> None:
        """language_code of 1 character is accepted (no min_length since Feature 050)."""
        mention = _make_entity_mention_base(language_code="a")
        assert mention.language_code == "a"

    def test_language_code_empty_is_accepted(self) -> None:
        """Empty language_code is accepted (no min_length since Feature 050)."""
        mention = _make_entity_mention_base(language_code="")
        assert mention.language_code == ""

    def test_language_code_none_is_accepted(self) -> None:
        """None language_code is accepted (nullable since Feature 050)."""
        mention = _make_entity_mention_base(language_code=None)
        assert mention.language_code is None

    def test_language_code_bcp47_formats_accepted(self) -> None:
        """Common BCP-47 language code formats are accepted."""
        for code in EntityMentionTestData.VALID_LANGUAGE_CODES:
            mention = _make_entity_mention_base(language_code=code)
            assert mention.language_code == code

    # -----------------------------------------------------------------------
    # validate_assignment — model_config
    # -----------------------------------------------------------------------

    def test_validate_assignment_rejects_invalid_confidence(self) -> None:
        """validate_assignment=True means assigning invalid confidence after creation raises ValidationError."""
        mention = _make_entity_mention_base(confidence=0.5)
        with pytest.raises(ValidationError):
            mention.confidence = 1.5

    def test_validate_assignment_rejects_invalid_mention_text(self) -> None:
        """validate_assignment=True means assigning empty mention_text after creation raises ValidationError."""
        mention = _make_entity_mention_base(mention_text="Valid text")
        with pytest.raises(ValidationError):
            mention.mention_text = ""

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def test_model_dump_serialises_detection_method_to_string(self) -> None:
        """model_dump() serialises DetectionMethod to its string value."""
        mention = _make_entity_mention_base(detection_method=DetectionMethod.SPACY_NER)
        data = mention.model_dump()

        assert data["detection_method"] == "spacy_ner"
        assert isinstance(data["detection_method"], str)

    def test_model_dump_round_trip(self) -> None:
        """model_dump() output can be used to reconstruct an equivalent model."""
        original = _make_entity_mention_base()
        data = original.model_dump()
        reconstructed = EntityMentionBase(**data)

        assert reconstructed == original

    def test_model_dump_contains_expected_keys(self) -> None:
        """model_dump() output contains all expected field keys."""
        mention = _make_entity_mention_base()
        data = mention.model_dump()

        expected_keys = {
            "entity_id",
            "segment_id",
            "video_id",
            "language_code",
            "mention_text",
            "detection_method",
            "confidence",
            "match_start",
            "match_end",
            "correction_id",
            "mention_source",
            "mention_context",
        }
        assert expected_keys == set(data.keys())


# ===========================================================================
# EntityMentionCreate Tests
# ===========================================================================


class TestEntityMentionCreate:
    """Tests for EntityMentionCreate model.

    EntityMentionCreate extends EntityMentionBase with no additional fields.
    These tests verify that it behaves identically to EntityMentionBase while
    confirming the inheritance relationship.
    """

    def test_entity_mention_create_is_subclass_of_base(self) -> None:
        """EntityMentionCreate is a subclass of EntityMentionBase."""
        assert issubclass(EntityMentionCreate, EntityMentionBase)

    def test_valid_create_with_all_fields(self) -> None:
        """EntityMentionCreate is created successfully with all valid fields."""
        entity_id = _uuid7()
        create = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=1,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Elon Musk",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )

        assert create.entity_id == entity_id
        assert create.segment_id == 1
        assert create.video_id == _VALID_VIDEO_ID
        assert create.language_code == "en"
        assert create.mention_text == "Elon Musk"
        assert create.detection_method == DetectionMethod.RULE_MATCH
        assert create.confidence == 1.0

    def test_valid_create_uses_base_defaults(self) -> None:
        """EntityMentionCreate inherits detection_method and confidence defaults from Base."""
        create = EntityMentionCreate(
            entity_id=_uuid7(),
            segment_id=1,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Some entity",
        )
        assert create.detection_method == DetectionMethod.RULE_MATCH
        # confidence defaults to None (nullable since Feature 050)
        assert create.confidence is None

    def test_create_factory_produces_valid_model(self) -> None:
        """EntityMentionCreateFactory.build() produces a valid EntityMentionCreate."""
        create = create_entity_mention_create()
        assert isinstance(create, EntityMentionCreate)
        assert isinstance(create, EntityMentionBase)

    def test_create_model_has_no_extra_fields_beyond_base(self) -> None:
        """EntityMentionCreate model_fields match EntityMentionBase model_fields exactly."""
        base_fields = set(EntityMentionBase.model_fields.keys())
        create_fields = set(EntityMentionCreate.model_fields.keys())
        assert base_fields == create_fields

    def test_invalid_mention_text_empty_raises_validation_error(self) -> None:
        """EntityMentionCreate rejects empty mention_text (inheriting Base validation)."""
        with pytest.raises(ValidationError):
            EntityMentionCreate(
                entity_id=_uuid7(),
                segment_id=1,
                video_id=_VALID_VIDEO_ID,
                language_code="en",
                mention_text="",
            )

    def test_invalid_confidence_out_of_range_raises_validation_error(self) -> None:
        """EntityMentionCreate rejects out-of-range confidence (inheriting Base validation)."""
        with pytest.raises(ValidationError):
            EntityMentionCreate(
                entity_id=_uuid7(),
                segment_id=1,
                video_id=_VALID_VIDEO_ID,
                language_code="en",
                mention_text="Elon Musk",
                confidence=1.5,
            )

    @pytest.mark.parametrize(
        "detection_method",
        list(DetectionMethod),
        ids=[m.value for m in DetectionMethod],
    )
    def test_all_detection_methods_produce_valid_create(
        self, detection_method: DetectionMethod
    ) -> None:
        """Every DetectionMethod value produces a valid EntityMentionCreate."""
        # Manual detection_method requires segment_id=None (Feature 050)
        if detection_method == DetectionMethod.MANUAL:
            create = EntityMentionCreate(
                entity_id=_uuid7(),
                segment_id=None,
                video_id=_VALID_VIDEO_ID,
                language_code=None,
                mention_text="Some entity",
                detection_method=detection_method,
            )
        else:
            create = EntityMentionCreate(
                entity_id=_uuid7(),
                segment_id=1,
                video_id=_VALID_VIDEO_ID,
                language_code="en",
                mention_text="Some entity",
                detection_method=detection_method,
            )
        assert create.detection_method == detection_method

    def test_model_dump_round_trip(self) -> None:
        """EntityMentionCreate round-trips through model_dump() successfully."""
        original = create_entity_mention_create()
        data = original.model_dump()
        reconstructed = EntityMentionCreate(**data)
        assert reconstructed == original


# ===========================================================================
# EntityMention (Full Read Model) Tests
# ===========================================================================


class TestEntityMention:
    """Tests for the full EntityMention read model.

    EntityMention extends EntityMentionBase with database-assigned fields
    (id: uuid.UUID, created_at: datetime) and is configured with
    from_attributes=True for SQLAlchemy ORM compatibility.
    """

    # -----------------------------------------------------------------------
    # Valid creation scenarios
    # -----------------------------------------------------------------------

    def test_valid_full_model_with_all_fields(self) -> None:
        """EntityMention is created successfully with all required fields."""
        mention_id = _uuid7()
        entity_id = _uuid7()
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        mention = EntityMention(
            id=mention_id,
            entity_id=entity_id,
            segment_id=1,
            video_id=_VALID_VIDEO_ID,
            language_code="en",
            mention_text="Elon Musk",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
            created_at=now,
        )

        assert mention.id == mention_id
        assert mention.entity_id == entity_id
        assert mention.created_at == now

    def test_id_is_uuid_instance(self) -> None:
        """id field is a uuid.UUID instance."""
        mention = _make_entity_mention()
        assert isinstance(mention.id, uuid.UUID)

    def test_created_at_is_datetime_instance(self) -> None:
        """created_at field is a datetime instance."""
        mention = _make_entity_mention()
        assert isinstance(mention.created_at, datetime)

    def test_factory_produces_valid_full_model(self) -> None:
        """EntityMentionFactory.build() produces a valid EntityMention."""
        mention = create_entity_mention()
        assert isinstance(mention, EntityMention)
        assert isinstance(mention, EntityMentionBase)

    # -----------------------------------------------------------------------
    # Inheritance verification
    # -----------------------------------------------------------------------

    def test_entity_mention_is_subclass_of_base(self) -> None:
        """EntityMention is a subclass of EntityMentionBase."""
        assert issubclass(EntityMention, EntityMentionBase)

    def test_entity_mention_has_id_and_created_at_beyond_base(self) -> None:
        """EntityMention model_fields includes id and created_at in addition to Base fields."""
        base_fields = set(EntityMentionBase.model_fields.keys())
        full_fields = set(EntityMention.model_fields.keys())
        extra_fields = full_fields - base_fields

        assert "id" in extra_fields
        assert "created_at" in extra_fields

    # -----------------------------------------------------------------------
    # Missing database-side fields raise ValidationError
    # -----------------------------------------------------------------------

    def test_missing_id_raises_validation_error(self) -> None:
        """EntityMention without id raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityMention(  # type: ignore[call-arg]
                # id deliberately omitted
                entity_id=_uuid7(),
                segment_id=1,
                video_id=_VALID_VIDEO_ID,
                language_code="en",
                mention_text="Elon Musk",
                created_at=datetime.now(UTC),
            )

    def test_missing_created_at_raises_validation_error(self) -> None:
        """EntityMention without created_at raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityMention(  # type: ignore[call-arg]
                id=_uuid7(),
                entity_id=_uuid7(),
                segment_id=1,
                video_id=_VALID_VIDEO_ID,
                language_code="en",
                mention_text="Elon Musk",
                # created_at deliberately omitted
            )

    # -----------------------------------------------------------------------
    # from_attributes=True — ORM compatibility
    # -----------------------------------------------------------------------

    def test_from_attributes_works_with_mock_orm_object(self) -> None:
        """EntityMention.model_validate() works against a mock ORM-like object.

        Notes
        -----
        EntityMention has from_attributes=True in its ConfigDict.
        This test verifies that model_validate() can consume an object whose
        attributes map to the model fields, as SQLAlchemy ORM objects do.
        """
        mention_id = _uuid7()
        entity_id = _uuid7()
        now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

        orm_like = MagicMock()
        orm_like.id = mention_id
        orm_like.entity_id = entity_id
        orm_like.segment_id = 42
        orm_like.video_id = _VALID_VIDEO_ID
        orm_like.language_code = "en-US"
        orm_like.mention_text = "Google DeepMind"
        orm_like.detection_method = DetectionMethod.SPACY_NER
        orm_like.confidence = 0.87
        orm_like.match_start = None
        orm_like.match_end = None
        orm_like.correction_id = None
        orm_like.mention_source = "transcript"
        orm_like.mention_context = None
        orm_like.created_at = now

        mention = EntityMention.model_validate(orm_like)

        assert mention.id == mention_id
        assert mention.entity_id == entity_id
        assert mention.segment_id == 42
        assert mention.video_id == _VALID_VIDEO_ID
        assert mention.language_code == "en-US"
        assert mention.mention_text == "Google DeepMind"
        assert mention.detection_method == DetectionMethod.SPACY_NER
        assert mention.confidence == 0.87
        assert mention.created_at == now

    def test_from_attributes_with_string_detection_method(self) -> None:
        """model_validate() correctly coerces string detection_method from ORM to enum.

        Notes
        -----
        ORM models store detection_method as a plain string column.
        Pydantic must coerce this string to the DetectionMethod enum.
        """
        orm_like = MagicMock()
        orm_like.id = _uuid7()
        orm_like.entity_id = _uuid7()
        orm_like.segment_id = 1
        orm_like.video_id = _VALID_VIDEO_ID
        orm_like.language_code = "en"
        orm_like.mention_text = "Elon Musk"
        orm_like.detection_method = "spacy_ner"  # plain string, not enum member
        orm_like.confidence = 0.75
        orm_like.match_start = None
        orm_like.match_end = None
        orm_like.correction_id = None
        orm_like.mention_source = "transcript"
        orm_like.mention_context = None
        orm_like.created_at = datetime.now(UTC)

        mention = EntityMention.model_validate(orm_like)
        assert mention.detection_method == DetectionMethod.SPACY_NER
        assert isinstance(mention.detection_method, DetectionMethod)

    def test_from_attributes_all_detection_methods(self) -> None:
        """model_validate() correctly coerces all detection_method string values from ORM."""
        for detection_method in DetectionMethod:
            orm_like = MagicMock()
            orm_like.id = _uuid7()
            orm_like.entity_id = _uuid7()
            orm_like.segment_id = 1
            orm_like.video_id = _VALID_VIDEO_ID
            orm_like.language_code = "en"
            orm_like.mention_text = "Some entity"
            orm_like.detection_method = detection_method.value
            orm_like.confidence = 1.0
            orm_like.match_start = None
            orm_like.match_end = None
            orm_like.correction_id = None
            orm_like.mention_source = "transcript"
            orm_like.mention_context = None
            orm_like.created_at = datetime.now(UTC)

            mention = EntityMention.model_validate(orm_like)
            assert mention.detection_method == detection_method

    def test_factory_batch_produces_unique_ids(self) -> None:
        """EntityMentionFactory.build_batch() produces unique id values."""
        mentions = EntityMentionFactory.build_batch(5)
        ids = [m.id for m in mentions]
        assert len(ids) == len(set(ids)), "Each factory-built mention must have a unique id"

    def test_factory_batch_produces_unique_entity_ids(self) -> None:
        """EntityMentionFactory.build_batch() produces unique entity_id values by default."""
        mentions = EntityMentionFactory.build_batch(3)
        entity_ids = [m.entity_id for m in mentions]
        assert len(entity_ids) == len(
            set(entity_ids)
        ), "Each factory-built mention should have a unique entity_id"

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def test_model_dump_includes_id_and_created_at(self) -> None:
        """model_dump() output includes both id and created_at keys."""
        mention = _make_entity_mention()
        data = mention.model_dump()

        assert "id" in data
        assert "created_at" in data
        assert isinstance(data["id"], uuid.UUID)
        assert isinstance(data["created_at"], datetime)

    def test_model_dump_serialises_detection_method_to_string(self) -> None:
        """model_dump() serialises DetectionMethod enum to its string value."""
        mention = _make_entity_mention(detection_method=DetectionMethod.LLM_EXTRACTION)
        data = mention.model_dump()
        assert data["detection_method"] == "llm_extraction"
        assert isinstance(data["detection_method"], str)

    def test_model_dump_round_trip(self) -> None:
        """EntityMention round-trips through model_dump() successfully."""
        original = _make_entity_mention()
        data = original.model_dump()
        reconstructed = EntityMention(**data)
        assert reconstructed == original


# ===========================================================================
# Hypothesis-based property tests
# ===========================================================================


class TestEntityMentionHypothesis:
    """Property-based tests using Hypothesis (Constitution §V).

    These tests search for unexpected failure modes by generating many
    variations of input data and asserting invariants that should hold
    for all valid (or invalid) inputs.
    """

    @given(method=st.sampled_from(DetectionMethod))
    def test_all_detection_methods_always_produce_valid_model(
        self, method: DetectionMethod
    ) -> None:
        """Every DetectionMethod member produces a valid EntityMentionBase.

        Notes
        -----
        If a new DetectionMethod member is added to the enum, this test
        automatically covers it without requiring manual parametrisation updates.
        """
        mention = _make_entity_mention_base(detection_method=method)
        assert mention.detection_method == method
        assert isinstance(mention.detection_method, DetectionMethod)

    @given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_valid_confidence_range_always_accepted(self, confidence: float) -> None:
        """Any float in [0.0, 1.0] is always accepted as a valid confidence value."""
        mention = _make_entity_mention_base(confidence=confidence)
        assert mention.confidence is not None and 0.0 <= mention.confidence <= 1.0

    @given(confidence=st.one_of(
        st.floats(max_value=-0.001, allow_nan=False),
        st.floats(min_value=1.001, allow_nan=False, allow_infinity=False),
    ))
    def test_out_of_range_confidence_always_raises_validation_error(
        self, confidence: float
    ) -> None:
        """Any float outside [0.0, 1.0] always raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(confidence=confidence)

    @given(text=st.text(min_size=1, max_size=500))
    def test_valid_mention_text_length_always_accepted(self, text: str) -> None:
        """Any text of 1–500 characters is accepted as mention_text."""
        mention = _make_entity_mention_base(mention_text=text)
        assert 1 <= len(mention.mention_text) <= 500

    @given(text=st.text(min_size=501))
    def test_mention_text_over_500_chars_always_raises_validation_error(
        self, text: str
    ) -> None:
        """Any text longer than 500 characters always raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_entity_mention_base(mention_text=text)

    @settings(max_examples=30)
    @given(
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        method=st.sampled_from(DetectionMethod),
    )
    def test_confidence_and_detection_method_are_independent(
        self, confidence: float, method: DetectionMethod
    ) -> None:
        """confidence and detection_method constraints are fully independent.

        Notes
        -----
        Any valid confidence combined with any DetectionMethod always
        produces a valid model — there must be no accidental cross-field coupling.
        """
        mention = _make_entity_mention_base(
            confidence=confidence, detection_method=method
        )
        assert mention.confidence is not None and 0.0 <= mention.confidence <= 1.0
        assert mention.detection_method == method
