"""Integration test: canonical identity dedup repair (Feature 060, T020).

Real-DB proof that the merge is lossless, idempotent, and preserves the
watched-video set that downstream watch-based metrics (e.g. the "Saved &
Forgotten" dashboard, feature 059) depend on — the cross-feature
mutation-impact re-query.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    UserLanguagePreference,
    UserVideo,
    Video,
)
from chronovista.models.app_identity import IdentityInvariants
from chronovista.services.identity_service import (
    IdentityService,
    LanguagePrefRekeyError,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CHANNEL = "UCzYTmeK-6v3DcJ6hzRh1q9w"
PLACEHOLDER = "takeout_user"

T1 = datetime(2024, 1, 1, tzinfo=UTC)
T2 = datetime(2024, 2, 1, tzinfo=UTC)
T2_NEWER = datetime(2024, 3, 1, tzinfo=UTC)  # placeholder holds the newer B watch
T3 = datetime(2024, 4, 1, tzinfo=UTC)
T4 = datetime(2024, 5, 1, tzinfo=UTC)


async def _watched_video_ids(session: AsyncSession) -> set[str]:
    result = await session.execute(
        select(UserVideo.video_id).where(UserVideo.watched_at.is_not(None)).distinct()
    )
    return {row[0] for row in result.all()}


async def _distinct_user_ids(session: AsyncSession) -> list[str]:
    result = await session.execute(select(UserVideo.user_id).distinct())
    return [row[0] for row in result.all()]


async def _seed(session: AsyncSession) -> None:
    session.add(Channel(channel_id=CHANNEL, title="Me", description="my channel"))
    for vid in ("vid_aaaaaaa", "vid_bbbbbbb", "vid_ccccccc", "vid_ddddddd"):
        session.add(
            Video(
                video_id=vid,
                channel_id=CHANNEL,
                title=vid,
                description="t",
                upload_date=T1,
                duration=100,
            )
        )
    # Canonical identity rows.
    #   A: liked + rewatched + saved on BOTH sides (diverging values) — the case
    #      raw row/sum invariants would falsely count twice and abort on; proves
    #      the per-video invariants are stable and GREATEST/OR pick the winners.
    session.add(
        UserVideo(
            user_id=CHANNEL,
            video_id="vid_aaaaaaa",
            watched_at=T1,
            liked=True,
            rewatch_count=2,
            saved_to_playlist=True,
        )
    )
    session.add(
        UserVideo(user_id=CHANNEL, video_id="vid_bbbbbbb", watched_at=T2, liked=True)
    )
    session.add(UserVideo(user_id=CHANNEL, video_id="vid_ccccccc", watched_at=T3))
    # Placeholder rows: A overlaps (liked+rewatch on both, higher rewatch, saved
    # only on canonical), B overlaps (NEWER watch), D is new (re-key).
    session.add(
        UserVideo(
            user_id=PLACEHOLDER,
            video_id="vid_aaaaaaa",
            watched_at=T1,
            liked=True,
            rewatch_count=5,
            saved_to_playlist=False,
        )
    )
    session.add(
        UserVideo(user_id=PLACEHOLDER, video_id="vid_bbbbbbb", watched_at=T2_NEWER)
    )
    session.add(UserVideo(user_id=PLACEHOLDER, video_id="vid_ddddddd", watched_at=T4))
    # NOTE: app_identities intentionally left EMPTY — this mirrors the real prod
    # scenario (fresh table, data already under UC… + takeout_user). The repair
    # must adopt the real channel as the survivor on its own.
    await session.commit()


async def test_repair_is_lossless_idempotent_and_preserves_watched_set(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    # Pre-image goes to a temp dir (no test pollution of ./data).
    from chronovista.config.settings import settings as _settings

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    await _seed(db_session)

    watched_before = await _watched_video_ids(db_session)
    assert watched_before == {
        "vid_aaaaaaa",
        "vid_bbbbbbb",
        "vid_ccccccc",
        "vid_ddddddd",
    }
    assert sorted(await _distinct_user_ids(db_session)) == [CHANNEL, PLACEHOLDER]

    service = IdentityService()
    report = await service.repair(db_session, dry_run=False)

    # One identity remains (the survivor).
    assert report.placeholder_user_ids == [PLACEHOLDER]
    assert await _distinct_user_ids(db_session) == [CHANNEL]

    # Cross-feature invariant: the watched-video set is unchanged (this is what
    # "Saved & Forgotten" / feature 059 depends on — 609-stable analogue).
    assert await _watched_video_ids(db_session) == watched_before

    # Lossless field merge: newer placeholder watch preserved; like preserved.
    b_row = (
        await db_session.execute(
            select(UserVideo).where(
                UserVideo.user_id == CHANNEL, UserVideo.video_id == "vid_bbbbbbb"
            )
        )
    ).scalar_one()
    assert b_row.watched_at == T2_NEWER  # GREATEST kept the newer timestamp
    assert b_row.liked is True

    # A: liked/rewatch on both sides — GREATEST/OR keep the strongest per field,
    # and the per-video invariants did NOT falsely abort (report returned).
    a_row = (
        await db_session.execute(
            select(UserVideo).where(
                UserVideo.user_id == CHANNEL, UserVideo.video_id == "vid_aaaaaaa"
            )
        )
    ).scalar_one()
    assert a_row.rewatch_count == 5  # GREATEST(2, 5)
    assert a_row.liked is True  # OR(True, True)
    assert a_row.saved_to_playlist is True  # OR(True, False)

    # D was re-keyed onto the survivor.
    d_row = (
        await db_session.execute(
            select(UserVideo).where(UserVideo.video_id == "vid_ddddddd")
        )
    ).scalar_one()
    assert d_row.user_id == CHANNEL

    # Invariants stable AND correctly computed *per video* — pins the
    # computation itself, not merely before==after self-consistency. The old
    # raw-aggregate computation would have produced before=(4, 3, 7) here (A
    # liked/rewatched on both sides counted twice), tripping a false regression;
    # the per-video computation gives (4, 2, 5) on both sides.
    expected = IdentityInvariants(
        distinct_watched_videos=4,  # a, b, c, d
        liked_count=2,  # distinct liked videos: a (both sides) + b
        rewatch_sum=5,  # per-video max: a=max(2, 5)=5, rest 0
    )
    assert report.invariants_before == expected
    assert report.invariants_after == expected

    # S3: topic_analytics "total users" == COUNT(DISTINCT user_id) == 1 post-merge.
    total_users = (
        await db_session.execute(select(func.count(func.distinct(UserVideo.user_id))))
    ).scalar_one()
    assert total_users == 1

    # Pre-image written to persistent storage — and it captures BOTH sides of
    # the merge, so a committed repair is reconstructable. The survivor's own
    # pre-merge row for vid_bbbbbbb (watched_at=T2) is the critical one: the
    # merge overwrites it with the placeholder's newer T2_NEWER via GREATEST,
    # so T2 exists nowhere else afterwards. A placeholder-only pre-image would
    # silently lose it.
    assert report.pre_image_path is not None
    dumped = json.loads(Path(report.pre_image_path).read_text(encoding="utf-8"))
    by_key = {(r["user_id"], r["video_id"]): r for r in dumped}

    # Placeholder side: overlapping (a, b) and non-overlapping (d).
    assert (PLACEHOLDER, "vid_aaaaaaa") in by_key
    assert (PLACEHOLDER, "vid_bbbbbbb") in by_key
    assert (PLACEHOLDER, "vid_ddddddd") in by_key
    # Survivor side: only the rows the merge overwrites in place.
    assert (CHANNEL, "vid_aaaaaaa") in by_key
    assert (CHANNEL, "vid_bbbbbbb") in by_key
    assert (
        CHANNEL,
        "vid_ccccccc",
    ) not in by_key, "survivor-only rows are untouched by the merge; don't dump them"

    # The overwritten value is recoverable from the file.
    assert by_key[(CHANNEL, "vid_bbbbbbb")]["watched_at"] == T2.isoformat()
    assert by_key[(CHANNEL, "vid_aaaaaaa")]["rewatch_count"] == 2  # pre-GREATEST
    assert by_key[(CHANNEL, "vid_aaaaaaa")]["saved_to_playlist"] is True

    # Idempotent: re-running is a no-op.
    report2 = await service.repair(db_session, dry_run=False)
    assert report2.placeholder_user_ids == []
    assert await _distinct_user_ids(db_session) == [CHANNEL]


async def test_dry_run_writes_nothing(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    from chronovista.config.settings import settings as _settings

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    await _seed(db_session)
    before = sorted(await _distinct_user_ids(db_session))

    report = await IdentityService().repair(db_session, dry_run=True)

    assert report.dry_run is True
    # Rolled back — both identities still present, no pre-image file.
    assert sorted(await _distinct_user_ids(db_session)) == before
    assert report.pre_image_path is None
    assert not list(tmp_path.glob("backups/*.json"))


async def test_lang_pref_collision_aborts_and_rolls_back_everything(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    """FR-019: a real (user_id, language_code) PK collision during the re-key must
    roll back the *entire* repair — including the user_videos merge — not just
    the language-pref UPDATE, and surface as LanguagePrefRekeyError.
    """
    from chronovista.config.settings import settings as _settings

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    await _seed(db_session)  # user_videos under CHANNEL + takeout_user
    # Same language present under BOTH the canonical id and default_user → the
    # re-key of default_user → CHANNEL collides on the (user_id, language_code) PK.
    db_session.add(
        UserLanguagePreference(
            user_id=CHANNEL, language_code="en", preference_type="fluent", priority=1
        )
    )
    db_session.add(
        UserLanguagePreference(
            user_id="default_user",
            language_code="en",
            preference_type="fluent",
            priority=1,
        )
    )
    await db_session.commit()

    with pytest.raises(LanguagePrefRekeyError):
        await IdentityService().repair(db_session, dry_run=False)

    # Whole transaction rolled back: the user_videos merge is undone (both
    # identities remain) and language prefs are untouched (both ids remain).
    assert sorted(await _distinct_user_ids(db_session)) == [CHANNEL, PLACEHOLDER]
    lang_ids = sorted(
        (await db_session.execute(select(UserLanguagePreference.user_id).distinct()))
        .scalars()
        .all()
    )
    assert lang_ids == [CHANNEL, "default_user"]

    # The pre-image left on disk is clearly marked provisional — no committed
    # repair happened, so an operator can't mistake it for a completed run.
    leftover = list((tmp_path / "backups").glob("*.json"))
    assert leftover, "a provisional pre-image should have been written pre-merge"
    assert all(f.name.endswith(".provisional.json") for f in leftover)


async def test_freshly_adopted_identity_survives_commit(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    """The no-op branch (adopt a real channel, then find no placeholders to
    merge) must COMMIT the flush-only identity INSERT, not drop it on session
    close. Proven by reading the row back from a *separate* engine/connection —
    a same-session read cannot distinguish a flushed-but-uncommitted row from a
    committed one, which is the entire content of this bug.
    """
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from chronovista.config.settings import settings as _settings
    from chronovista.db.models import AppIdentity as AppIdentityDB

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    # Single identity already in user_videos, app_identities empty → the repair
    # adopts CHANNEL and hits the no-op branch (nothing to merge).
    db_session.add(Channel(channel_id=CHANNEL, title="Me", description="c"))
    db_session.add(
        Video(
            video_id="vid_solo_aa",
            channel_id=CHANNEL,
            title="v",
            description="t",
            upload_date=T1,
            duration=100,
        )
    )
    db_session.add(UserVideo(user_id=CHANNEL, video_id="vid_solo_aa", watched_at=T1))
    await db_session.commit()

    report = await IdentityService().repair(db_session, dry_run=False)
    assert report.canonical_user_id == CHANNEL
    assert report.placeholder_user_ids == []  # nothing to merge — the no-op path

    # Read from a brand-new engine/connection: the adopted row is visible ONLY if
    # it was actually committed (not merely flushed within db_session).
    url = os.getenv(
        "DATABASE_INTEGRATION_URL",
        "postgresql+asyncpg://dev_user:dev_password@localhost:5434"
        "/chronovista_integration_test",
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as fresh:
            row = (
                await fresh.execute(select(AppIdentityDB).where(AppIdentityDB.id == 1))
            ).scalar_one_or_none()
            assert row is not None, (
                "adopted identity was not committed — the flush-only INSERT was "
                "dropped on session close (the no-op commit-gap bug)"
            )
            assert row.user_id == CHANNEL
            assert row.source == "channel"
    finally:
        await engine.dispose()
