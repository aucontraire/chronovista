"""Unit tests for the Feature 116 candidate-signal models (the Option-C child).

Pure Pydantic construction — no DB, no async. Guards the ``CandidateSignal`` values and the
structural ``_lift_matches_signal`` invariant (title/description carries a lift; transcript
does not, since it ranks by proximity). The numeric qualifying floors (support >= 5, the tuned
transcript bar) are DB CHECK constraints, not model validation, so they are not tested here.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from chronovista.models.relationship_candidate import (
    CandidateSignal,
    RelationshipCandidateSignalCreate,
)


def _kwargs(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate_id": uuid.uuid4(),
        "signal": CandidateSignal.TITLE_DESCRIPTION,
        "support": 7,
        "lift": 50.0,
        "entity_a_video_count": 10,
        "entity_b_video_count": 12,
        "signal_universe": 40000,
    }
    base.update(over)
    return base


class TestCandidateSignal:
    def test_values(self) -> None:
        assert CandidateSignal.TITLE_DESCRIPTION.value == "title_description"
        assert CandidateSignal.TRANSCRIPT.value == "transcript"

    def test_is_str_enum(self) -> None:
        # A str-Enum, so it binds as its string value in the per-channel `channel == signal`
        # SQL filter (Feature 116, list_ranked).
        assert isinstance(CandidateSignal.TRANSCRIPT, str)
        assert f"{CandidateSignal.TRANSCRIPT.value}" == "transcript"


class TestLiftMatchesSignal:
    """The definitional per-signal shape: title/description has a lift, transcript does not."""

    def test_title_description_with_lift_ok(self) -> None:
        row = RelationshipCandidateSignalCreate(**_kwargs())
        assert row.lift == 50.0
        assert row.signal is CandidateSignal.TITLE_DESCRIPTION

    def test_title_description_without_lift_raises(self) -> None:
        with pytest.raises(ValidationError, match="must carry a lift"):
            RelationshipCandidateSignalCreate(**_kwargs(lift=None))

    def test_transcript_without_lift_ok(self) -> None:
        row = RelationshipCandidateSignalCreate(
            **_kwargs(signal=CandidateSignal.TRANSCRIPT, lift=None, min_gap_seconds=3.0)
        )
        assert row.lift is None
        assert row.min_gap_seconds == 3.0

    def test_transcript_with_lift_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not carry a lift"):
            RelationshipCandidateSignalCreate(
                **_kwargs(signal=CandidateSignal.TRANSCRIPT, lift=50.0)
            )
