"""Cross-table identity invariant guard (Feature 060, T027 / FR-016, FR-017).

The invariant that matters is *cross-table*: every identity-bearing table uses
the single canonical identity (matches the ``app_identities`` singleton) — NOT a
per-table "<= 1 distinct" cardinality check, which would pass green while two
tables used *different* single identities (the pre-fix `default_user`-vs-channel
state, and the PR #98 "looks-fixed-but-isn't" failure mode).

This module provides the reusable guard helper and covers the ``user_videos``
arm (P1). The ``user_language_preferences`` arm is added in US4 (T035a).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import AppIdentity as AppIdentityDB
from chronovista.db.models import Channel, UserLanguagePreference, UserVideo, Video
from chronovista.services.identity_service import IdentityService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CHANNEL = "UCzYTmeK-6v3DcJ6hzRh1q9w"
PLACEHOLDER = "takeout_user"

# Identity-bearing tables (model, user-id column) — the full cross-table set.
IDENTITY_TABLES: list[tuple[type, str]] = [
    (UserVideo, "user_id"),
    (UserLanguagePreference, "user_id"),
]


async def cross_table_identity_violations(session: AsyncSession) -> list[str]:
    """Return human-readable violations of the cross-table identity invariant.

    Empty list == invariant holds: a canonical identity is established and every
    identity-bearing table contains only that identity.
    """
    identity = (
        await session.execute(select(AppIdentityDB).where(AppIdentityDB.id == 1))
    ).scalar_one_or_none()
    canonical = identity.user_id if identity is not None else None

    violations: list[str] = []
    for model, col in IDENTITY_TABLES:
        ids = {
            row[0]
            for row in (
                await session.execute(select(getattr(model, col)).distinct())
            ).all()
        }
        if not ids:
            continue
        if canonical is None or (ids - {canonical}):
            violations.append(
                f"{model.__tablename__}: {sorted(ids)} (canonical={canonical})"
            )
    return violations


async def _seed_two_identities(session: AsyncSession) -> None:
    session.add(Channel(channel_id=CHANNEL, title="Me", description="c"))
    for vid in ("vid_g_aaaaa", "vid_g_bbbbb"):
        session.add(
            Video(
                video_id=vid,
                channel_id=CHANNEL,
                title=vid,
                description="t",
                upload_date=datetime(2024, 1, 1, tzinfo=UTC),
                duration=100,
            )
        )
    session.add(
        UserVideo(
            user_id=CHANNEL,
            video_id="vid_g_aaaaa",
            watched_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )
    session.add(
        UserVideo(
            user_id=PLACEHOLDER,
            video_id="vid_g_bbbbb",
            watched_at=datetime(2024, 2, 1, tzinfo=UTC),
        )
    )
    await session.commit()


async def test_guard_fails_on_pre_repair_split(db_session: AsyncSession) -> None:
    await _seed_two_identities(db_session)
    violations = await cross_table_identity_violations(db_session)
    assert violations, "guard must fail on the pre-repair two-identity state (#153)"


async def test_guard_passes_after_repair(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    from chronovista.config.settings import settings as _settings

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    await _seed_two_identities(db_session)
    await IdentityService().repair(db_session, dry_run=False)

    violations = await cross_table_identity_violations(db_session)
    assert violations == [], f"guard must pass after repair; got {violations}"


async def test_guard_catches_language_pref_mismatch_and_repair_fixes_it(
    db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    """T035a: the language-prefs arm — a default_user vs channel mismatch.

    Watch history is clean under the channel, but language preferences sit under
    `default_user`. A per-table "<=1 distinct" check would pass both tables; the
    cross-table guard catches the mismatch, and the repair re-keys it.
    """
    from chronovista.config.settings import settings as _settings

    monkeypatch.setattr(_settings, "data_dir", tmp_path)

    # Clean watch history under the channel + a language pref under default_user.
    session = db_session
    session.add(Channel(channel_id=CHANNEL, title="Me", description="c"))
    session.add(
        Video(
            video_id="vid_lang_aaa",
            channel_id=CHANNEL,
            title="v",
            description="t",
            upload_date=datetime(2024, 1, 1, tzinfo=UTC),
            duration=100,
        )
    )
    session.add(
        UserVideo(
            user_id=CHANNEL,
            video_id="vid_lang_aaa",
            watched_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )
    session.add(
        UserLanguagePreference(
            user_id="default_user",
            language_code="en",
            preference_type="fluent",
            priority=1,
        )
    )
    await session.commit()

    violations = await cross_table_identity_violations(session)
    assert any("user_language_preferences" in v for v in violations), violations

    await IdentityService().repair(session, dry_run=False)

    assert await cross_table_identity_violations(session) == []
    # The preference now lives under the canonical identity.
    langs = (
        (await session.execute(select(UserLanguagePreference.user_id).distinct()))
        .scalars()
        .all()
    )
    assert list(langs) == [CHANNEL]
