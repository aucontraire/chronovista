"""Rekey SQL-shape + collision tests for language prefs (Feature 060, T033)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.user_language_preference_repository import (
    RekeyCollisionError,
    UserLanguagePreferenceRepository,
)

pytestmark = pytest.mark.asyncio

FROM_ID = "default_user"
TO_ID = "UCzYTmeK-6v3DcJ6hzRh1q9w"


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


async def test_rekey_update_sets_user_id_only_no_collision() -> None:
    repo = UserLanguagePreferenceRepository()
    session = MagicMock(spec=AsyncSession)

    collision_result = MagicMock()
    collision_result.all.return_value = []  # no colliding languages
    update_result = MagicMock()
    update_result.rowcount = 8
    session.execute = AsyncMock(side_effect=[collision_result, update_result])

    count = await repo.rekey_user_id(session, from_user_id=FROM_ID, to_user_id=TO_ID)

    assert count == 8
    # 2nd execute is the UPDATE; assert SET targets user_id only.
    update_sql = _sql(session.execute.await_args_list[1].args[0])
    assert update_sql.lower().startswith("update user_language_preferences set user_id")
    for col in ("language_code", "preference_type", "priority"):
        assert f"set {col}" not in update_sql.lower()
    assert f"'{TO_ID}'" in update_sql
    assert f"user_language_preferences.user_id = '{FROM_ID}'" in update_sql


async def test_rekey_refuses_on_pk_collision() -> None:
    repo = UserLanguagePreferenceRepository()
    session = MagicMock(spec=AsyncSession)

    collision_result = MagicMock()
    collision_result.all.return_value = [("en",), ("es",)]  # colliding languages
    session.execute = AsyncMock(return_value=collision_result)

    with pytest.raises(RekeyCollisionError):
        await repo.rekey_user_id(session, from_user_id=FROM_ID, to_user_id=TO_ID)
    # Only the collision-check ran; no UPDATE was issued.
    assert session.execute.await_count == 1
