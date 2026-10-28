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
from chronovista.db.models import Video as VideoDB
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
def candidate_service() -> CandidateSuggestionService:
    """The service wired with real repos and no enrichment (no network in tests)."""
    return CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
    )
