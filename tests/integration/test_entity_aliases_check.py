"""US3 structural guard: the name store rejects the known-error type (SC-002).

After Feature 110, ``entity_aliases.chk_alias_type_valid`` no longer admits
``'asr_error'`` (the ORM metadata and the migration agree), so any attempt to file a
known-error string among names fails at the database. This is the schema enforcing
what every reader used to re-assert by hand.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias, NamedEntity

pytestmark = pytest.mark.asyncio


async def _seed_entity(db_session: AsyncSession) -> NamedEntity:
    entity = NamedEntity(
        entity_type="person",
        canonical_name="Invented Person",
        canonical_name_normalized="invented person",
    )
    db_session.add(entity)
    await db_session.flush()
    return entity


@pytest.mark.db
@pytest.mark.integration
class TestNameStoreRejectsKnownErrorType:
    async def test_asr_error_insert_is_rejected(self, db_session: AsyncSession) -> None:
        """Inserting an asr_error-typed row into entity_aliases violates the CHECK."""
        entity = await _seed_entity(db_session)
        db_session.add(
            EntityAlias(
                entity_id=entity.id,
                alias_name="garbled form",
                alias_name_normalized="garbled form",
                alias_type="asr_error",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_name_type_insert_is_accepted(self, db_session: AsyncSession) -> None:
        """A genuine name type is still accepted (the CHECK keeps the five name types)."""
        entity = await _seed_entity(db_session)
        db_session.add(
            EntityAlias(
                entity_id=entity.id,
                alias_name="A Nickname",
                alias_name_normalized="a nickname",
                alias_type="nickname",
            )
        )
        await db_session.flush()  # must not raise
