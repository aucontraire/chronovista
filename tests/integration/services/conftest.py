"""Shared fixtures for candidate-suggestion integration tests (Feature 096).

Factories for seeding a grounded seed entity (whose stored relation points at a
not-yet-library target) and corpus videos, plus a service wired with real repos and
no enrichment (tests never hit the network — enrichment is best-effort, FR-009).
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable

import pytest

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

_SET_AT = "2026-10-27T00:00:00Z"


@pytest.fixture
def make_seed_entity() -> Callable[..., NamedEntityDB]:
    """Factory: a grounded, active entity whose ``relation`` points at a target QID."""

    def _make(
        *,
        name: str,
        qid: str,
        relation: str,
        target_qid: str,
        target_label: str,
        entity_type: str = "person",
    ) -> NamedEntityDB:
        return NamedEntityDB(
            id=uuid.uuid4(),
            canonical_name=name,
            canonical_name_normalized=name.lower(),
            entity_type=entity_type,
            external_ids={"wikidata": {"id": qid}},
            properties={
                relation: {
                    "qids": [target_qid],
                    "values": [target_label],
                    "source": "wikidata",
                    "set_at": _SET_AT,
                }
            },
        )

    return _make


@pytest.fixture
def make_video() -> Callable[..., VideoDB]:
    """Factory: a video with title + optional description (the grounding corpus)."""

    def _make(*, video_id: str, title: str, description: str | None = None) -> VideoDB:
        return VideoDB(
            video_id=video_id,
            title=title,
            description=description,
            upload_date=datetime.datetime(2019, 1, 1, tzinfo=datetime.UTC),
            duration=120,
        )

    return _make


@pytest.fixture
def make_transcript_segments() -> (
    Callable[..., list[VideoTranscriptDB | TranscriptSegmentDB]]
):
    """Factory: a ``video_transcripts`` parent plus its ``transcript_segments`` (Feature 106).

    ``segments`` is a list of ``(text, corrected_text, has_correction)`` tuples, in sequence order.
    The composite FK ``(video_id, language_code)`` requires the parent transcript row, so this
    returns both the parent and the segment rows for the test to ``add``; the matching
    ``make_video`` must be added too (``video_transcripts.video_id`` FKs ``videos``). Placeholder
    text only — no library content.
    """

    def _make(
        *,
        video_id: str,
        language_code: str = "en",
        segments: list[tuple[str, str | None, bool]],
    ) -> list[VideoTranscriptDB | TranscriptSegmentDB]:
        rows: list[VideoTranscriptDB | TranscriptSegmentDB] = [
            VideoTranscriptDB(
                video_id=video_id,
                language_code=language_code,
                transcript_text=" ".join(text for text, _c, _h in segments),
                transcript_type="AUTO",
                download_reason="USER_REQUEST",
            )
        ]
        for i, (text, corrected_text, has_correction) in enumerate(segments):
            rows.append(
                TranscriptSegmentDB(
                    video_id=video_id,
                    language_code=language_code,
                    text=text,
                    corrected_text=corrected_text,
                    has_correction=has_correction,
                    start_time=float(i),
                    duration=1.0,
                    end_time=float(i) + 1.0,
                    sequence_number=i,
                )
            )
        return rows

    return _make


@pytest.fixture
def candidate_service() -> CandidateSuggestionService:
    """The service wired with real repos and no enrichment (no network in tests)."""
    return CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
    )
