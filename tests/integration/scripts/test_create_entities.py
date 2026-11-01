"""Integration test: the offline loader writes the structured external_ids shape (Feature 101).

FR-003 bug-fix diff for ``scripts/entity_resolution/create_entities.py``. The loader previously
wrote a bare ``{"wikidata": qid}`` string under the source key (the #4 bug); it now routes
grounding through the shared ``build_grounding`` helper and persists the structured
``{id, verified, status}`` dump every ``external_ids`` reader expects (SC-003). This is the
explicit current-wrong → corrected diff FR-009 requires.

``db_manager.get_session`` is pointed at the shared test session. Placeholder name/QID only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.enums import EntityType

# The offline loader lives in the gitignored ``scripts/entity_resolution/`` tree (local
# operational tooling), so skip this test wherever that module is absent — e.g. a fresh CI
# checkout — rather than failing collection on the import.
create_entities = pytest.importorskip("scripts.entity_resolution.create_entities")

_NAME = "Test Loader Person"
_NORMALIZED = "test loader person"
_QID = "Q90000001"


@pytest.fixture
def wired(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the script's ``db_manager.get_session`` at the shared test session."""

    async def _get_session(**_: Any) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(db_manager, "get_session", _get_session)


async def _cleanup(session: AsyncSession) -> None:
    rows = (
        (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == _NORMALIZED
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id == row.id)
        )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized == _NORMALIZED
        )
    )
    await session.commit()


async def test_loader_writes_structured_grounding(
    wired: None, db_session: AsyncSession
) -> None:
    """``run(..., apply=True)`` creates a grounded entity whose ``external_ids`` is the structured
    dump, never the pre-fix bare string."""
    await _cleanup(db_session)
    try:
        await create_entities.run(
            [{"name": _NAME, "qid": _QID, "description": "fixture"}],
            EntityType.PERSON,
            apply=True,
        )
        entity = (
            (
                await db_session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.canonical_name_normalized == _NORMALIZED
                    )
                )
            )
            .scalars()
            .one()
        )
        grounding = entity.external_ids["wikidata"]
        assert isinstance(
            grounding, dict
        ), f"expected structured dict, got {grounding!r}"
        assert grounding["id"] == _QID
        assert grounding["verified"] is True
        assert grounding["status"] == "verified"
        # And the canonical NAME_VARIANT self-alias the core registers exists.
        aliases = (
            (
                await db_session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.entity_id == entity.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(aliases) == 1
        assert aliases[0].alias_name == _NAME
    finally:
        await _cleanup(db_session)
