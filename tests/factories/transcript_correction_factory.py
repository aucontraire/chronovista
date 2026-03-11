"""
Factory for TranscriptCorrection ORM models using factory_boy.

Provides reusable test data factories for the TranscriptCorrection ORM model
(append-only audit records for transcript segment corrections, Feature 033)
with sensible defaults and easy customization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.models.enums import CorrectionType


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID for Pydantic compatibility."""
    return uuid.UUID(bytes=uuid7().bytes)


class TranscriptCorrectionFactory(factory.Factory[TranscriptCorrectionDB]):
    """Factory for TranscriptCorrectionDB ORM models.

    Produces fully-populated TranscriptCorrection ORM instances suitable
    for unit tests that do not touch the database.  Use `.build()` to
    instantiate without a session; use `.create()` only inside database-backed
    integration tests with a live session.
    """

    class Meta:
        model = TranscriptCorrectionDB

    id: Any = LazyFunction(_uuid7)
    video_id: Any = LazyFunction(lambda: "dQw4w9WgXcQ")
    language_code: Any = LazyFunction(lambda: "en")
    segment_id: Any = LazyFunction(lambda: 1)
    correction_type: Any = LazyFunction(lambda: CorrectionType.SPELLING.value)
    original_text: Any = Sequence(lambda n: f"original text {n}")
    corrected_text: Any = Sequence(lambda n: f"corrected text {n}")
    correction_note: Any = LazyFunction(lambda: None)
    corrected_by_user_id: Any = LazyFunction(lambda: "cli")
    corrected_at: Any = LazyFunction(lambda: datetime.now(tz=timezone.utc))
    version_number: Any = LazyFunction(lambda: 1)


# ---------------------------------------------------------------------------
# Convenience factory function
# ---------------------------------------------------------------------------


def create_transcript_correction(**kwargs: Any) -> TranscriptCorrectionDB:
    """Create a TranscriptCorrectionDB ORM instance with keyword arguments.

    Parameters
    ----------
    **kwargs : Any
        Any field overrides to apply on top of factory defaults.

    Returns
    -------
    TranscriptCorrectionDB
        A built (not persisted) TranscriptCorrection ORM instance.
    """
    result = TranscriptCorrectionFactory.build(**kwargs)
    assert isinstance(result, TranscriptCorrectionDB)
    return result


# ---------------------------------------------------------------------------
# Common test data patterns
# ---------------------------------------------------------------------------


class TranscriptCorrectionTestData:
    """Common test data patterns for TranscriptCorrection models."""

    VALID_CORRECTION_DATA: dict[str, Any] = {
        "video_id": "dQw4w9WgXcQ",
        "language_code": "en",
        "segment_id": 1,
        "correction_type": CorrectionType.SPELLING.value,
        "original_text": "teh quick brown fox",
        "corrected_text": "the quick brown fox",
        "correction_note": None,
        "corrected_by_user_id": "cli",
        "corrected_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "version_number": 1,
    }

    VALID_CORRECTION_TYPES = [
        CorrectionType.SPELLING,
        CorrectionType.PROFANITY_FIX,
        CorrectionType.CONTEXT_CORRECTION,
        CorrectionType.FORMATTING,
        CorrectionType.PROPER_NOUN,
        CorrectionType.WORD_BOUNDARY,
        CorrectionType.OTHER,
        CorrectionType.REVERT,
    ]

    VALID_LANGUAGE_CODES = [
        "en",
        "en-US",
        "es",
        "fr",
        "de",
        "ja",
        "ko",
        "zh-CN",
        "pt-BR",
    ]

    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]

    @classmethod
    def valid_correction_data(cls) -> dict[str, Any]:
        """Get a copy of the canonical valid correction data dictionary.

        Returns
        -------
        dict[str, Any]
            A fresh copy of VALID_CORRECTION_DATA safe to mutate in tests.
        """
        return dict(cls.VALID_CORRECTION_DATA)

    @classmethod
    def proper_noun_data(cls) -> dict[str, Any]:
        """Get valid correction data for a proper noun correction.

        Returns
        -------
        dict[str, Any]
            Correction data with correction_type set to PROPER_NOUN.
        """
        data = cls.valid_correction_data()
        data.update(
            {
                "correction_type": CorrectionType.PROPER_NOUN.value,
                "original_text": "i went two the store",
                "corrected_text": "i went to the store",
                "correction_note": "ASR confused homophone",
                "version_number": 2,
            }
        )
        return data

    @classmethod
    def revert_data(cls) -> dict[str, Any]:
        """Get valid correction data for a revert operation.

        Returns
        -------
        dict[str, Any]
            Correction data with correction_type set to REVERT.
        """
        data = cls.valid_correction_data()
        data.update(
            {
                "correction_type": CorrectionType.REVERT.value,
                "original_text": "the quick brown fox",
                "corrected_text": "teh quick brown fox",
                "correction_note": "Reverted erroneous spelling correction",
                "version_number": 3,
            }
        )
        return data
