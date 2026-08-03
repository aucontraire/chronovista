"""Shape tests for the shared watched-video derivation (Feature 061, T006).

``watched_video_ids()`` is the single definition of "watched" on the read side.
These tests pin the three properties it exists to guarantee — correctness,
duplicate-safety, and the non-correlated form — because the correlated
alternative returns *identical results* 370x slower, so no value assertion can
distinguish them (research R1).
"""

from __future__ import annotations

import re

from sqlalchemy.dialects import postgresql

from chronovista.repositories.user_video_repository import watched_video_ids


def _sql() -> str:
    """Compile the subquery to PostgreSQL SQL with whitespace collapsed."""
    raw = str(
        watched_video_ids().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return re.sub(r"\s+", " ", raw).strip().lower()


def test_selects_video_id_from_user_videos() -> None:
    sql = _sql()
    assert "select" in sql
    assert "user_videos.video_id" in sql
    assert "from user_videos" in sql


def test_filters_on_watched_at_not_membership() -> None:
    """FR-001: watched-status comes from the watch timestamp, never membership."""
    sql = _sql()
    assert "user_videos.watched_at is not null" in sql
    assert (
        "playlist_membership" not in sql
    ), "watched-status must never be derived from playlist membership"


def test_is_distinct_so_duplicate_watch_rows_cannot_inflate() -> None:
    """FR-002: counts must not depend on one watch-history row per video."""
    assert "distinct" in _sql()


def test_is_not_correlated() -> None:
    """Research R1: the correlated form measured 25,676 ms vs 69 ms.

    A correlated subquery references the outer query's tables. This one must
    reference ``user_videos`` and nothing else, so PostgreSQL evaluates it once
    rather than once per candidate row.

    Table references are compared as whole names rather than by substring —
    ``"videos." in sql`` is true of ``user_videos.video_id`` and would pass
    vacuously.
    """
    sql = _sql()
    qualifiers = set(re.findall(r"\b(\w+)\.\w+", sql))
    assert qualifiers == {"user_videos"}, (
        f"subquery references {qualifiers - {'user_videos'}} besides user_videos — "
        "it is correlated and will be re-evaluated per row (research R1)"
    )
