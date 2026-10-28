"""Ranking & triage quality integration test (Feature 096, T022, SC-002).

A specific, modestly-present multi-word candidate must outrank a common, ubiquitous
single-word one (Decision 2b: specificity beats raw frequency), and the worth-review
bucket must be a smaller share than the whole queue. Real DB.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio


async def test_specific_name_outranks_common_word(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    # Two dangling targets from one seed each: a specific two-word name (rare) and a
    # common single word that appears in many videos.
    db_session.add_all(
        [
            make_seed_entity(
                name="Seed Specific",
                qid="Q8001",
                relation="spouse",
                target_qid="Q9001",
                target_label="Testname Alpha",
            ),
            make_seed_entity(
                name="Seed Common",
                qid="Q8002",
                relation="spouse",
                target_qid="Q9002",
                target_label="water",
            ),
        ]
    )
    videos = [
        make_video(
            video_id=f"vidcommon{i:03d}", title="a clip about water", description=None
        )
        for i in range(10)
    ]
    videos.append(
        make_video(
            video_id="vidspecific1",
            title="An interview with Testname Alpha",
            description=None,
        )
    )
    db_session.add_all(videos)
    await db_session.flush()

    await candidate_service.generate(db_session)
    repo = candidate_service._candidates

    rows, total = await repo.list_pending(db_session, source_channel="relation")
    qids = [r.wikidata_qid for r in rows]
    assert qids, "expected candidates"
    # Decision 2b: the specific multi-word name ranks above the common single word,
    # even though the common word has far higher raw salience.
    assert qids.index("Q9001") < qids.index("Q9002")

    common = next(r for r in rows if r.wikidata_qid == "Q9002")
    specific = next(r for r in rows if r.wikidata_qid == "Q9001")
    assert common.salience > specific.salience  # raw frequency favours the common word
    assert specific.score > common.score  # specificity wins the score

    # SC-002: the worth-review bucket is a strict subset of the whole queue.
    counts = await repo.counts_by_status(db_session, source_channel="relation")
    assert counts["worth_review"] < total
    assert common.triage == "likely_eliminable"
    assert specific.triage == "worth_review"
