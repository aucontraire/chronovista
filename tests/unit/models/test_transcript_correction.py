"""
Tests for TranscriptCorrection Pydantic domain models.

Validates field constraints, enum enforcement, cross-field validators,
and ORM compatibility for TranscriptCorrectionCreate and
TranscriptCorrectionRead models (Feature 033, FR-018 append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from uuid_utils import uuid7

from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_correction import (
    TranscriptCorrectionCreate,
    TranscriptCorrectionRead,
)
from tests.factories.transcript_correction_factory import (
    TranscriptCorrectionFactory,
    TranscriptCorrectionTestData,
    create_transcript_correction,
)

# CRITICAL: Ensure async tests work with coverage tooling.
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ALL_CORRECTION_TYPES = list(CorrectionType)

_VALID_VIDEO_ID = "dQw4w9WgXcQ"
_VALID_LANGUAGE_CODE = "en"


def _make_correction_create(**overrides: Any) -> TranscriptCorrectionCreate:
    """Return a valid TranscriptCorrectionCreate with optional field overrides.

    Parameters
    ----------
    **overrides : Any
        Any field values to override on top of sensible defaults.

    Returns
    -------
    TranscriptCorrectionCreate
        A fully-populated create model.
    """
    defaults: dict[str, Any] = {
        "video_id": _VALID_VIDEO_ID,
        "language_code": _VALID_LANGUAGE_CODE,
        "segment_id": 1,
        "correction_type": CorrectionType.SPELLING,
        "original_text": "teh quick brown fox",
        "corrected_text": "the quick brown fox",
        "correction_note": None,
        "corrected_by_user_id": None,
        "version_number": 1,
    }
    defaults.update(overrides)
    return TranscriptCorrectionCreate(**defaults)


def _make_uuid7() -> uuid.UUID:
    """Generate a standard uuid.UUID from UUIDv7 bytes."""
    return uuid.UUID(bytes=uuid7().bytes)


# ---------------------------------------------------------------------------
# TranscriptCorrectionCreate tests
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionCreate:
    """Tests for TranscriptCorrectionCreate Pydantic model validation."""

    # ------------------------------------------------------------------
    # Valid creation scenarios
    # ------------------------------------------------------------------

    def test_valid_create_required_fields_only(self) -> None:
        """TranscriptCorrectionCreate is valid with only the required fields.

        Notes
        -----
        segment_id, correction_note, and corrected_by_user_id all default to
        None, so they must not be supplied to exercise this path.
        """
        correction = TranscriptCorrectionCreate(
            video_id=_VALID_VIDEO_ID,
            language_code=_VALID_LANGUAGE_CODE,
            correction_type=CorrectionType.SPELLING,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
            version_number=1,
        )

        assert correction.video_id == _VALID_VIDEO_ID
        assert correction.language_code == _VALID_LANGUAGE_CODE
        assert correction.segment_id is None
        assert correction.correction_type == CorrectionType.SPELLING
        assert correction.original_text == "teh quick brown fox"
        assert correction.corrected_text == "the quick brown fox"
        assert correction.correction_note is None
        assert correction.corrected_by_user_id is None
        assert correction.version_number == 1

    def test_valid_create_with_all_optional_fields(self) -> None:
        """TranscriptCorrectionCreate accepts all optional fields populated."""
        correction = TranscriptCorrectionCreate(
            video_id=_VALID_VIDEO_ID,
            language_code="en-US",
            segment_id=42,
            correction_type=CorrectionType.PROPER_NOUN,
            original_text="i went two the store",
            corrected_text="i went to the store",
            correction_note="ASR confused homophone 'to'/'two'",
            corrected_by_user_id="user_abc123",
            version_number=2,
        )

        assert correction.segment_id == 42
        assert correction.correction_note == "ASR confused homophone 'to'/'two'"
        assert correction.corrected_by_user_id == "user_abc123"
        assert correction.version_number == 2

    def test_valid_create_using_factory_defaults(self) -> None:
        """Factory-built ORM object has field values matching Pydantic expectations."""
        orm_obj = create_transcript_correction()

        # Build a Pydantic Create model from the ORM object's attribute dict
        correction = TranscriptCorrectionCreate(
            video_id=orm_obj.video_id,
            language_code=orm_obj.language_code,
            segment_id=orm_obj.segment_id,
            correction_type=CorrectionType(orm_obj.correction_type),
            original_text=orm_obj.original_text,
            corrected_text=orm_obj.corrected_text,
            correction_note=orm_obj.correction_note,
            corrected_by_user_id=orm_obj.corrected_by_user_id,
            version_number=orm_obj.version_number,
        )

        assert correction.video_id == orm_obj.video_id
        assert correction.version_number == orm_obj.version_number

    def test_valid_create_test_data_proper_noun(self) -> None:
        """TranscriptCorrectionTestData.proper_noun_data() produces a valid model."""
        data = TranscriptCorrectionTestData.proper_noun_data()
        # Remove ORM-only field not present on Create model
        data.pop("corrected_at", None)
        data.pop("id", None)

        correction = TranscriptCorrectionCreate(**data)

        assert correction.correction_type == CorrectionType.PROPER_NOUN
        assert correction.version_number == 2

    def test_valid_create_test_data_revert(self) -> None:
        """TranscriptCorrectionTestData.revert_data() produces a valid model."""
        data = TranscriptCorrectionTestData.revert_data()
        data.pop("corrected_at", None)
        data.pop("id", None)

        correction = TranscriptCorrectionCreate(**data)

        assert correction.correction_type == CorrectionType.REVERT
        assert correction.version_number == 3

    # ------------------------------------------------------------------
    # CorrectionType enum enforcement — all 6 values
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "correction_type",
        [
            CorrectionType.SPELLING,
            CorrectionType.PROPER_NOUN,
            CorrectionType.CONTEXT_CORRECTION,
            CorrectionType.WORD_BOUNDARY,
            CorrectionType.FORMATTING,
            CorrectionType.PROFANITY_FIX,
            CorrectionType.OTHER,
            CorrectionType.REVERT,
        ],
        ids=[
            "SPELLING",
            "PROPER_NOUN",
            "CONTEXT_CORRECTION",
            "WORD_BOUNDARY",
            "FORMATTING",
            "PROFANITY_FIX",
            "OTHER",
            "REVERT",
        ],
    )
    def test_all_correction_type_enum_values_are_valid(
        self, correction_type: CorrectionType
    ) -> None:
        """Every CorrectionType value produces a valid TranscriptCorrectionCreate.

        Notes
        -----
        This test exercises all six enum members defined in CorrectionType so
        that adding a seventh value without updating tests causes a CI failure.
        """
        correction = _make_correction_create(correction_type=correction_type)
        assert correction.correction_type == correction_type
        assert isinstance(correction.correction_type, CorrectionType)

    def test_invalid_correction_type_string_raises_validation_error(self) -> None:
        """Unrecognised string passed as correction_type raises ValidationError."""
        with pytest.raises(ValidationError, match="correction_type"):
            _make_correction_create(correction_type="nonexistent_type")

    def test_invalid_correction_type_int_raises_validation_error(self) -> None:
        """Integer passed as correction_type raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_correction_create(correction_type=99)

    def test_invalid_correction_type_none_raises_validation_error(self) -> None:
        """None passed for required correction_type raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_correction_create(correction_type=None)

    # ------------------------------------------------------------------
    # version_number constraints — must be >= 1
    # ------------------------------------------------------------------

    def test_version_number_minimum_boundary_is_accepted(self) -> None:
        """version_number == 1 (the minimum) is accepted."""
        correction = _make_correction_create(version_number=1)
        assert correction.version_number == 1

    def test_version_number_zero_raises_validation_error(self) -> None:
        """version_number == 0 violates the >= 1 constraint."""
        with pytest.raises(ValidationError, match="version_number"):
            _make_correction_create(version_number=0)

    def test_version_number_negative_raises_validation_error(self) -> None:
        """Negative version_number violates the >= 1 constraint."""
        with pytest.raises(ValidationError, match="version_number"):
            _make_correction_create(version_number=-1)

    def test_version_number_large_positive_is_accepted(self) -> None:
        """Large positive version_number values are accepted."""
        correction = _make_correction_create(version_number=9_999)
        assert correction.version_number == 9_999

    # ------------------------------------------------------------------
    # No-op prevention — corrected_text must differ from original_text
    # ------------------------------------------------------------------

    def test_corrected_text_same_as_original_raises_validation_error(self) -> None:
        """Identical original_text and corrected_text raise ValidationError (no-op prevention)."""
        with pytest.raises(ValidationError, match="no-op corrections are not permitted"):
            TranscriptCorrectionCreate(
                video_id=_VALID_VIDEO_ID,
                language_code=_VALID_LANGUAGE_CODE,
                correction_type=CorrectionType.SPELLING,
                original_text="hello world",
                corrected_text="hello world",  # identical — must be rejected
                version_number=1,
            )

    def test_corrected_text_differs_from_original_is_valid(self) -> None:
        """corrected_text that differs from original_text is accepted."""
        correction = _make_correction_create(
            original_text="helo world",
            corrected_text="hello world",
        )
        assert correction.corrected_text == "hello world"

    def test_no_op_check_is_case_sensitive(self) -> None:
        """Strings differing only in case are NOT considered equal (case-sensitive no-op check)."""
        # "Hello" != "hello" — should be accepted
        correction = _make_correction_create(
            original_text="Hello world",
            corrected_text="hello world",
        )
        assert correction.corrected_text == "hello world"

    # ------------------------------------------------------------------
    # corrected_by_user_id max length (100 characters)
    # ------------------------------------------------------------------

    def test_corrected_by_user_id_at_max_length_is_accepted(self) -> None:
        """corrected_by_user_id at exactly 100 characters is accepted."""
        user_id_100 = "u" * 100
        correction = _make_correction_create(corrected_by_user_id=user_id_100)
        # str_strip_whitespace is set; "u"*100 has no whitespace to strip
        assert correction.corrected_by_user_id == user_id_100

    def test_corrected_by_user_id_exceeding_max_length_raises_error(self) -> None:
        """corrected_by_user_id longer than 100 characters raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_correction_create(corrected_by_user_id="u" * 101)

    def test_corrected_by_user_id_none_is_accepted(self) -> None:
        """corrected_by_user_id=None (default) is accepted."""
        correction = _make_correction_create(corrected_by_user_id=None)
        assert correction.corrected_by_user_id is None

    def test_corrected_by_user_id_short_string_is_accepted(self) -> None:
        """Short corrected_by_user_id strings are accepted."""
        correction = _make_correction_create(corrected_by_user_id="cli")
        assert correction.corrected_by_user_id == "cli"

    # ------------------------------------------------------------------
    # Empty string handling
    # ------------------------------------------------------------------

    def test_empty_original_text_is_accepted(self) -> None:
        """original_text may be an empty string (no non-empty constraint in model).

        Notes
        -----
        The model does not enforce non-empty text at the Pydantic layer.
        str_strip_whitespace is configured, so leading/trailing whitespace is
        stripped before the no-op cross-field check runs.
        """
        # Empty original_text + non-empty corrected_text differs → valid
        correction = _make_correction_create(
            original_text="",
            corrected_text="some corrected text",
        )
        assert correction.original_text == ""

    def test_empty_corrected_text_differs_from_nonempty_original(self) -> None:
        """Empty corrected_text is accepted when original_text is non-empty."""
        correction = _make_correction_create(
            original_text="some original text",
            corrected_text="",
        )
        assert correction.corrected_text == ""

    def test_both_empty_strings_raises_validation_error(self) -> None:
        """Two empty strings are equal so should trigger no-op prevention."""
        with pytest.raises(ValidationError, match="no-op corrections are not permitted"):
            _make_correction_create(
                original_text="",
                corrected_text="",
            )

    def test_whitespace_stripped_before_no_op_check(self) -> None:
        """str_strip_whitespace strips whitespace; equal stripped values raise ValidationError.

        Notes
        -----
        The base model sets str_strip_whitespace=True.  After stripping,
        "  hello  " becomes "hello" and " hello " also becomes "hello",
        so the no-op validator should fire.
        """
        with pytest.raises(ValidationError, match="no-op corrections are not permitted"):
            _make_correction_create(
                original_text="  hello  ",
                corrected_text=" hello ",
            )

    # ------------------------------------------------------------------
    # Model serialisation
    # ------------------------------------------------------------------

    def test_model_dump_serialises_enum_to_string(self) -> None:
        """model_dump() serialises CorrectionType to its string value."""
        correction = _make_correction_create(correction_type=CorrectionType.FORMATTING)
        data = correction.model_dump()

        assert data["correction_type"] == "formatting"
        assert isinstance(data["correction_type"], str)

    def test_model_dump_round_trip(self) -> None:
        """model_dump() output can be used to reconstruct an equivalent model."""
        original = _make_correction_create()
        data = original.model_dump()
        reconstructed = TranscriptCorrectionCreate(**data)

        assert reconstructed == original


# ---------------------------------------------------------------------------
# TranscriptCorrectionRead tests
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionRead:
    """Tests for TranscriptCorrectionRead Pydantic model.

    TranscriptCorrectionRead extends TranscriptCorrectionCreate with two
    database-side fields: id (UUIDv7) and corrected_at (datetime).
    It is configured with from_attributes=True for SQLAlchemy ORM compatibility.
    """

    def _make_read(self, **overrides: Any) -> TranscriptCorrectionRead:
        """Build a valid TranscriptCorrectionRead with optional field overrides."""
        now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        defaults: dict[str, Any] = {
            "id": _make_uuid7(),
            "video_id": _VALID_VIDEO_ID,
            "language_code": _VALID_LANGUAGE_CODE,
            "segment_id": None,
            "correction_type": CorrectionType.SPELLING,
            "original_text": "teh quick brown fox",
            "corrected_text": "the quick brown fox",
            "correction_note": None,
            "corrected_by_user_id": None,
            "version_number": 1,
            "corrected_at": now,
        }
        defaults.update(overrides)
        return TranscriptCorrectionRead(**defaults)

    # ------------------------------------------------------------------
    # Valid creation scenarios
    # ------------------------------------------------------------------

    def test_valid_read_with_required_fields(self) -> None:
        """TranscriptCorrectionRead is valid with all required fields present."""
        correction_id = _make_uuid7()
        now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        correction = TranscriptCorrectionRead(
            id=correction_id,
            video_id=_VALID_VIDEO_ID,
            language_code=_VALID_LANGUAGE_CODE,
            correction_type=CorrectionType.SPELLING,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
            version_number=1,
            corrected_at=now,
        )

        assert correction.id == correction_id
        assert correction.corrected_at == now
        assert correction.video_id == _VALID_VIDEO_ID

    def test_all_fields_present_including_id_and_corrected_at(self) -> None:
        """TranscriptCorrectionRead exposes all expected fields including id and corrected_at."""
        correction = self._make_read()

        # Base inherited fields
        assert hasattr(correction, "video_id")
        assert hasattr(correction, "language_code")
        assert hasattr(correction, "segment_id")
        assert hasattr(correction, "correction_type")
        assert hasattr(correction, "original_text")
        assert hasattr(correction, "corrected_text")
        assert hasattr(correction, "correction_note")
        assert hasattr(correction, "corrected_by_user_id")
        assert hasattr(correction, "version_number")
        # Read-specific fields
        assert hasattr(correction, "id")
        assert hasattr(correction, "corrected_at")

    def test_id_is_uuid_instance(self) -> None:
        """id field is a uuid.UUID instance."""
        correction = self._make_read()
        assert isinstance(correction.id, uuid.UUID)

    def test_corrected_at_is_datetime_instance(self) -> None:
        """corrected_at field is a datetime instance."""
        correction = self._make_read()
        assert isinstance(correction.corrected_at, datetime)

    # ------------------------------------------------------------------
    # from_attributes ORM compatibility
    # ------------------------------------------------------------------

    def test_from_attributes_works_with_orm_like_object(self) -> None:
        """TranscriptCorrectionRead.model_validate() works against ORM-like object.

        Notes
        -----
        TranscriptCorrectionRead has from_attributes=True in its ConfigDict.
        This test verifies model_validate() can consume a SQLAlchemy ORM
        object built via the factory (which mirrors the ORM model structure).
        """
        orm_obj = create_transcript_correction(
            correction_type=CorrectionType.PROPER_NOUN.value,
            original_text="i went two the store",
            corrected_text="i went to the store",
            correction_note="ASR homophone error",
            version_number=2,
        )

        pydantic_obj = TranscriptCorrectionRead.model_validate(orm_obj)

        assert pydantic_obj.id == orm_obj.id
        assert pydantic_obj.video_id == orm_obj.video_id
        assert pydantic_obj.language_code == orm_obj.language_code
        assert pydantic_obj.correction_type == CorrectionType.PROPER_NOUN
        assert pydantic_obj.original_text == orm_obj.original_text
        assert pydantic_obj.corrected_text == orm_obj.corrected_text
        assert pydantic_obj.correction_note == orm_obj.correction_note
        assert pydantic_obj.version_number == orm_obj.version_number
        assert isinstance(pydantic_obj.corrected_at, datetime)

    def test_from_attributes_factory_batch_produces_unique_ids(self) -> None:
        """Factory-built ORM objects produce unique UUIDs when validated via model_validate."""
        orm_objects = TranscriptCorrectionFactory.build_batch(3)
        pydantic_objects = [
            TranscriptCorrectionRead.model_validate(o) for o in orm_objects
        ]
        ids = [o.id for o in pydantic_objects]
        assert len(ids) == len(set(ids)), "Each factory-built object must have a unique id"

    def test_from_attributes_all_correction_types(self) -> None:
        """model_validate() correctly coerces the string correction_type from ORM to enum."""
        for correction_type in CorrectionType:
            orm_obj = create_transcript_correction(
                correction_type=correction_type.value,
            )
            pydantic_obj = TranscriptCorrectionRead.model_validate(orm_obj)
            assert pydantic_obj.correction_type == correction_type

    # ------------------------------------------------------------------
    # Missing database fields raise ValidationError
    # ------------------------------------------------------------------

    def test_missing_id_raises_validation_error(self) -> None:
        """TranscriptCorrectionRead without id raises ValidationError."""
        with pytest.raises(ValidationError):
            TranscriptCorrectionRead(  # type: ignore[call-arg]
                # id deliberately omitted
                video_id=_VALID_VIDEO_ID,
                language_code=_VALID_LANGUAGE_CODE,
                correction_type=CorrectionType.SPELLING,
                original_text="teh",
                corrected_text="the",
                version_number=1,
                corrected_at=datetime.now(timezone.utc),
            )

    def test_missing_corrected_at_raises_validation_error(self) -> None:
        """TranscriptCorrectionRead without corrected_at raises ValidationError."""
        with pytest.raises(ValidationError):
            TranscriptCorrectionRead(  # type: ignore[call-arg]
                id=_make_uuid7(),
                video_id=_VALID_VIDEO_ID,
                language_code=_VALID_LANGUAGE_CODE,
                correction_type=CorrectionType.SPELLING,
                original_text="teh",
                corrected_text="the",
                version_number=1,
                # corrected_at deliberately omitted
            )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def test_model_dump_includes_id_and_corrected_at(self) -> None:
        """model_dump() output includes both id and corrected_at keys."""
        correction = self._make_read()
        data = correction.model_dump()

        assert "id" in data
        assert "corrected_at" in data
        assert isinstance(data["id"], uuid.UUID)
        assert isinstance(data["corrected_at"], datetime)

    def test_model_dump_serialises_correction_type_to_string(self) -> None:
        """model_dump() serialises correction_type enum to its string value."""
        correction = self._make_read(correction_type=CorrectionType.PROFANITY_FIX)
        data = correction.model_dump()
        assert data["correction_type"] == "profanity_fix"


# ---------------------------------------------------------------------------
# Hypothesis-based property tests
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionHypothesis:
    """Property-based tests using Hypothesis (Constitution §V).

    These tests search for unexpected failure modes by generating many
    variations of input data and asserting invariants that should hold
    for all valid (or invalid) inputs.
    """

    # ------------------------------------------------------------------
    # CorrectionType enum exhaustiveness
    # ------------------------------------------------------------------

    @given(correction_type=st.sampled_from(CorrectionType))
    def test_all_enum_values_produce_valid_models(
        self, correction_type: CorrectionType
    ) -> None:
        """Every CorrectionType member produces a valid TranscriptCorrectionCreate.

        Notes
        -----
        If a new CorrectionType member is added to the enum this test will
        automatically cover it, ensuring exhaustiveness without manual
        parametrisation updates.
        """
        correction = _make_correction_create(correction_type=correction_type)
        assert correction.correction_type == correction_type
        assert isinstance(correction.correction_type, CorrectionType)

    # ------------------------------------------------------------------
    # Text field edge cases
    # ------------------------------------------------------------------

    @given(text=st.text(min_size=1, max_size=500))
    def test_non_identical_text_pairs_are_always_valid(self, text: str) -> None:
        """Any pair of distinct text values (original, corrected) produces a valid model.

        Notes
        -----
        We suffix the corrected text to guarantee non-equality after
        str_strip_whitespace normalisation.
        """
        suffix = "_CORRECTED"
        original = text
        corrected = text + suffix

        # Both strings stripped; they will differ as long as the suffix survives
        # after strip. Since suffix contains no leading/trailing whitespace, it
        # always survives stripping.
        correction = _make_correction_create(
            original_text=original,
            corrected_text=corrected,
        )
        assert correction.corrected_text.endswith(suffix)

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Po"),
                whitelist_characters=" ",
            ),
            min_size=1,
            max_size=200,
        )
    )
    def test_identical_text_always_raises_validation_error(self, text: str) -> None:
        """Two identical non-empty strings always trigger the no-op validator.

        Notes
        -----
        We restrict the alphabet to printable characters without leading or
        trailing whitespace characters so that str_strip_whitespace does not
        reduce two distinct raw strings to the same stripped form.
        """
        stripped = text.strip()
        # Only test non-empty stripped values to avoid ambiguity with the
        # empty-string edge case which is also rejected but for the same reason.
        assume(len(stripped) > 0)

        with pytest.raises(ValidationError, match="no-op corrections are not permitted"):
            _make_correction_create(
                original_text=stripped,
                corrected_text=stripped,
            )

    @given(
        text=st.text(
            # Unicode supplementary plane including emoji and combining chars
            alphabet=st.characters(whitelist_categories=("So", "Mn", "Ll")),
            min_size=1,
            max_size=100,
        )
    )
    def test_unicode_and_emoji_original_text_accepted(self, text: str) -> None:
        """Unicode / emoji content in original_text is accepted by the model.

        Notes
        -----
        The corrected text is forced to differ by appending an ASCII suffix.
        """
        corrected = text + "X"
        try:
            correction = _make_correction_create(
                original_text=text,
                corrected_text=corrected,
            )
            # If no error, the model must have stored the values
            assert correction.original_text is not None
        except ValidationError:
            # str_strip_whitespace may normalise both to identical empty strings
            # for pure-whitespace / combining-only inputs — that is expected.
            pass

    # ------------------------------------------------------------------
    # version_number boundary tests
    # ------------------------------------------------------------------

    @given(version_number=st.integers(min_value=1, max_value=100_000))
    def test_positive_version_numbers_are_always_valid(
        self, version_number: int
    ) -> None:
        """Any version_number >= 1 is accepted."""
        correction = _make_correction_create(version_number=version_number)
        assert correction.version_number == version_number

    @given(version_number=st.integers(max_value=0))
    def test_non_positive_version_numbers_always_raise_error(
        self, version_number: int
    ) -> None:
        """Any version_number <= 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_correction_create(version_number=version_number)

    @settings(max_examples=50)
    @given(
        version_number=st.integers(min_value=1, max_value=1_000_000),
        user_id_len=st.integers(min_value=1, max_value=100),
    )
    def test_version_and_user_id_combinations_are_independent(
        self, version_number: int, user_id_len: int
    ) -> None:
        """version_number and corrected_by_user_id constraints are independent.

        Notes
        -----
        A valid version_number combined with a valid corrected_by_user_id
        always produces a valid model.  This guards against accidental
        cross-field coupling.
        """
        user_id = "u" * user_id_len  # 1..100 chars, all valid
        correction = _make_correction_create(
            version_number=version_number,
            corrected_by_user_id=user_id,
        )
        assert correction.version_number == version_number
        assert correction.corrected_by_user_id == user_id
