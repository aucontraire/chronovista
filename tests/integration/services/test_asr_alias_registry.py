"""US4 writer repoint: register_asr_alias writes the dedicated store (SC-006).

After Feature 110 the registration hook must write known-error strings to
``entity_asr_errors`` — never to ``entity_aliases`` — and must not carry an
occurrence counter (the dedicated store has no such column). This exercises the real
hook against a real database (Constitution V: cross a real seam, not a mock).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias, EntityAsrError, NamedEntity
from chronovista.models.entity_asr_error import EntityAsrErrorCreate
from chronovista.repositories.entity_asr_error_repository import (
    EntityAsrErrorRepository,
)
from chronovista.services.asr_alias_registry import register_asr_alias

pytestmark = pytest.mark.asyncio


async def _seed_entity(db_session: AsyncSession, name: str) -> NamedEntity:
    entity = NamedEntity(
        entity_type="person",
        canonical_name=name,
        canonical_name_normalized=name.lower(),
    )
    db_session.add(entity)
    await db_session.flush()
    return entity


@pytest.mark.db
@pytest.mark.integration
class TestRegisterAsrAliasWritesDedicatedStore:
    async def test_registration_lands_in_dedicated_store_not_name_store(
        self, db_session: AsyncSession
    ) -> None:
        """A registered error form appears in entity_asr_errors, not entity_aliases."""
        entity = await _seed_entity(db_session, "Invented Person")

        await register_asr_alias(
            db_session,
            original_text="garbled person",
            corrected_text="Invented Person",
        )
        await db_session.flush()

        # The full-string error form is in the dedicated store for this entity.
        asr_forms = (
            (
                await db_session.execute(
                    select(EntityAsrError.alias_name).where(
                        EntityAsrError.entity_id == entity.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "garbled person" in asr_forms

        # And NO asr_error row leaked into the name store.
        name_store_asr = (
            await db_session.execute(
                select(func.count())
                .select_from(EntityAlias)
                .where(EntityAlias.alias_type == "asr_error")
            )
        ).scalar_one()
        assert (
            name_store_asr == 0
        ), "Registration must not write asr_error to entity_aliases."

    async def test_sub_token_error_forms_are_registered(
        self, db_session: AsyncSession
    ) -> None:
        """The word-level diff registers sub-token error forms in the dedicated store.

        A multi-word correction whose words differ registers both the full-string
        error form and the minimal changed token(s) — all into entity_asr_errors.
        """
        entity = await _seed_entity(db_session, "Zorblax Qintell")

        await register_asr_alias(
            db_session,
            original_text="zorblax qintel",
            corrected_text="Zorblax Qintell",
        )
        await db_session.flush()

        forms = set(
            (
                await db_session.execute(
                    select(EntityAsrError.alias_name).where(
                        EntityAsrError.entity_id == entity.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "zorblax qintel" in forms, "The full-string error form must register."
        assert (
            "qintel" in forms
        ), "The minimal changed sub-token must register too (word-level diff)."

    async def test_create_or_update_dedupes_at_the_repository(
        self, db_session: AsyncSession
    ) -> None:
        """create_or_update's own dedup logic returns the same row on repeat.

        Called directly on the repository (no savepoint), so a broken dedup that
        fell through to a second INSERT would raise a UNIQUE IntegrityError here
        rather than being swallowed — this isolates the dedup branch from the
        constraint that also happens to enforce one-row end-to-end.
        """
        entity = await _seed_entity(db_session, "Invented Person")
        repo = EntityAsrErrorRepository()
        obj = EntityAsrErrorCreate(
            # entity.id on the freshly-added ORM object is a uuid_utils.UUID (the
            # Python default); normalize to a stdlib UUID the way a DB round-trip
            # would (the real registry path gets entity_id from a query result).
            entity_id=uuid.UUID(str(entity.id)),
            alias_name="garbled person",
            alias_name_normalized="garbled person",
        )

        first = await repo.create_or_update(db_session, obj_in=obj)
        second = await repo.create_or_update(db_session, obj_in=obj)

        assert first.id == second.id, "Repeat must return the same row, not a new one."
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(EntityAsrError)
                .where(
                    EntityAsrError.entity_id == entity.id,
                    EntityAsrError.alias_name_normalized == "garbled person",
                )
            )
        ).scalar_one()
        assert count == 1, "create_or_update must not duplicate the same error form."


@pytest.mark.db
@pytest.mark.integration
class TestRegisterAsrAliasBehaviours:
    """Behavioural seams of register_asr_alias, against a real database.

    These restore coverage that previously lived in mock-based unit tests (deleted
    with the writer repoint): the negative no-match path, that normalization reaches
    the stored row, and the single-word sub-token dedup skip.
    """

    async def _all_forms(
        self, db_session: AsyncSession, entity_id: uuid.UUID
    ) -> list[tuple[str, str]]:
        rows = (
            await db_session.execute(
                select(
                    EntityAsrError.alias_name, EntityAsrError.alias_name_normalized
                ).where(EntityAsrError.entity_id == entity_id)
            )
        ).all()
        return [(r[0], r[1]) for r in rows]

    async def test_no_write_when_corrected_text_matches_no_entity(
        self, db_session: AsyncSession
    ) -> None:
        """No entity match → nothing is written anywhere (negative path)."""
        await _seed_entity(db_session, "Invented Person")

        await register_asr_alias(
            db_session,
            original_text="some garble form",
            corrected_text="Nonexistent Entity Zqx",
        )
        await db_session.flush()

        total = (
            await db_session.execute(select(func.count()).select_from(EntityAsrError))
        ).scalar_one()
        assert total == 0, "An unmatched correction must not write an error row."

    async def test_normalized_form_reaches_the_stored_row(
        self, db_session: AsyncSession
    ) -> None:
        """The normalized form (not the raw text) is stored in alias_name_normalized.

        Uses upper-case input so a bug that stored the raw ``original_text`` as the
        normalized form would be caught (the prior happy-path test used already-
        lowercase input and could not see it).
        """
        entity = await _seed_entity(db_session, "Zorblax Qintell")

        await register_asr_alias(
            db_session,
            original_text="ZORBLAX QINTEL",
            corrected_text="Zorblax Qintell",
        )
        await db_session.flush()

        forms = dict(await self._all_forms(db_session, entity.id))
        assert "ZORBLAX QINTEL" in forms, "The raw alias text is stored verbatim."
        normalized = forms["ZORBLAX QINTEL"]
        assert normalized == normalized.lower(), (
            "alias_name_normalized must be the normalized (folded) form, "
            f"not the raw upper-case text; got {normalized!r}."
        )
        assert normalized != "ZORBLAX QINTEL"

    async def test_single_word_correction_registers_no_duplicate_subtoken(
        self, db_session: AsyncSession
    ) -> None:
        """A single-word correction registers exactly one row (sub-token skip rule).

        The word-level diff's only changed token equals the full string, so the
        sub-token registration is skipped (``error_token == original_text``) and no
        duplicate row is created.
        """
        entity = await _seed_entity(db_session, "Zorblax")

        await register_asr_alias(
            db_session,
            original_text="zorblaxx",
            corrected_text="Zorblax",
        )
        await db_session.flush()

        forms = [f for f, _ in await self._all_forms(db_session, entity.id)]
        assert forms == ["zorblaxx"], (
            "A single-word correction must register exactly the full-string form, "
            f"with no duplicate sub-token; got {forms!r}."
        )
