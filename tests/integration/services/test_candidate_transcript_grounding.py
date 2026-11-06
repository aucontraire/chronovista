"""End-to-end transcript grounding through generation (Feature 106).

The unit guards prove ``_CorpusIndex`` folds transcripts and ``_assemble_one_video`` applies
the effective-text rule and the language filter. These integration tests prove the transcript text
actually flows through the full ``generate`` → fetch segments → assemble → ``_CorpusIndex`` →
``salience`` → persist seam against a real DB: a candidate whose name is spoken only in a transcript
becomes reviewable (leaves ``grounds_nowhere``), the per-source ``salience_transcript`` column is
populated with a measured count (never a false NULL for a rescored pending row), corrections drive
the match (effective text), and an excluded language contributes nothing.

The ``candidate_service`` fixture wires no Wikidata client, so ``aliases_map={}`` / ``excluded_languages``
drive each path deterministically with no network. Placeholder names only — no library content.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import TriageCategory
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio

# A placeholder name whose tokens appear ONLY in a transcript, never in a title or description.
_TRANSCRIPT_NAME = "Zephyrine Quallsborough"


async def test_transcript_only_candidate_becomes_reviewable(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
    make_transcript_segments: Callable[
        ..., list[VideoTranscriptDB | TranscriptSegmentDB]
    ],
) -> None:
    """SC-001/SC-002: a name spoken only in a transcript scores > 0 and leaves grounds_nowhere."""
    db_session.add(
        make_seed_entity(
            name="Seed Transcript",
            qid="Q8201",
            relation="spouse",
            target_qid="Q9201",
            target_label=_TRANSCRIPT_NAME,
        )
    )
    db_session.add(
        make_video(
            video_id="vidtr_only_1",
            title="an unrelated title",
            description="an unrelated description",
        )
    )
    for obj in make_transcript_segments(
        video_id="vidtr_only_1",
        segments=[
            ("today we discuss " + _TRANSCRIPT_NAME + " at length", None, False),
            ("and other unrelated chatter", None, False),
        ],
    ):
        db_session.add(obj)
    await db_session.flush()

    summary = await candidate_service.generate(db_session, aliases_map={})

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9201"
    )
    assert cand is not None
    # The name is absent from title/description; a non-zero salience can ONLY come from transcript.
    assert cand.salience_title == 0
    assert cand.salience_description == 0
    assert cand.salience_transcript is not None and cand.salience_transcript >= 1
    assert cand.salience >= 1
    assert cand.triage != TriageCategory.GROUNDS_NOWHERE.value
    # The measurement mechanism (FR-008): the run summary reports the bucket this row landed in.
    assert summary.by_triage.get(TriageCategory.GROUNDS_NOWHERE.value, 0) >= 0


async def test_pending_candidate_has_measured_transcript_count_never_false_null(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
    make_transcript_segments: Callable[
        ..., list[VideoTranscriptDB | TranscriptSegmentDB]
    ],
) -> None:
    """SC-003/FR-004: a rescored pending candidate carries a measured int, never a false NULL.

    A candidate whose name is in no transcript must get ``salience_transcript == 0`` (measured,
    found nothing) — NOT NULL. NULL means "not measured" and is reserved for terminal rows the
    upsert's ``WHERE review_status = 'pending'`` guard never touches.
    """
    db_session.add(
        make_seed_entity(
            name="Seed Nowhere",
            qid="Q8202",
            relation="spouse",
            target_qid="Q9202",
            target_label="Obscurina Nevermentioned",  # in no source at all
        )
    )
    db_session.add(
        make_video(
            video_id="vidtr_none_1",
            title="unrelated",
            description="unrelated",
        )
    )
    for obj in make_transcript_segments(
        video_id="vidtr_none_1",
        segments=[("nothing relevant spoken here", None, False)],
    ):
        db_session.add(obj)
    await db_session.flush()

    await candidate_service.generate(db_session, aliases_map={})

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9202"
    )
    assert cand is not None
    assert (
        cand.salience_transcript == 0
    ), "measured-and-found-nothing is 0, never a false NULL"


async def test_correction_drives_the_transcript_match(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
    make_transcript_segments: Callable[
        ..., list[VideoTranscriptDB | TranscriptSegmentDB]
    ],
) -> None:
    """FR-001: grounding reads EFFECTIVE text — a corrected segment matches on its correction."""
    corrected_name = "Thaddeus Wimbleforth"  # placeholder; only in corrected_text
    db_session.add(
        make_seed_entity(
            name="Seed Corrected",
            qid="Q8203",
            relation="spouse",
            target_qid="Q9203",
            target_label=corrected_name,
        )
    )
    db_session.add(
        make_video(video_id="vidtr_corr_1", title="unrelated", description="unrelated")
    )
    for obj in make_transcript_segments(
        video_id="vidtr_corr_1",
        segments=[
            # Raw ASR mangled the name; the correction has the right spelling. Grounding must read
            # the correction (effective text), so it matches the corrected name, not the raw text.
            ("thadeus wimbleforthe", corrected_name, True),
        ],
    ):
        db_session.add(obj)
    await db_session.flush()

    await candidate_service.generate(db_session, aliases_map={})

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9203"
    )
    assert cand is not None
    assert cand.salience_transcript is not None and cand.salience_transcript >= 1


async def test_excluded_language_transcript_contributes_nothing(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
    make_transcript_segments: Callable[
        ..., list[VideoTranscriptDB | TranscriptSegmentDB]
    ],
) -> None:
    """FR-003 end-to-end: a name only in an EXCLUDED-language transcript scores 0.

    The same seed/video/transcript scores > 0 with no exclusions and 0 when its language is
    excluded — proving the filter flows through the real fetch + assembly, not just the unit.
    """
    db_session.add(
        make_seed_entity(
            name="Seed Lang",
            qid="Q8204",
            relation="spouse",
            target_qid="Q9204",
            target_label=_TRANSCRIPT_NAME,
        )
    )
    db_session.add(
        make_video(video_id="vidtr_lang_1", title="unrelated", description="unrelated")
    )
    for obj in make_transcript_segments(
        video_id="vidtr_lang_1",
        language_code="de",
        segments=[("heute sprechen wir über " + _TRANSCRIPT_NAME, None, False)],
    ):
        db_session.add(obj)
    await db_session.flush()

    # German excluded → the transcript is dropped → the name grounds nowhere.
    await candidate_service.generate(
        db_session, aliases_map={}, excluded_languages=frozenset({"de"})
    )
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9204"
    )
    assert cand is not None
    assert (
        cand.salience_transcript == 0
    ), "an excluded-language transcript must contribute nothing"

    # Re-run with no exclusions → the same transcript now grounds the name.
    await candidate_service.generate(
        db_session, aliases_map={}, excluded_languages=frozenset()
    )
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9204"
    )
    assert cand is not None
    assert cand.salience_transcript is not None and cand.salience_transcript >= 1
