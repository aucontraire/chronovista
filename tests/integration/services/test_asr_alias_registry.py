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

from chronovista.db.models import (
    EntityAlias,
    EntityAsrError,
    EntityMention,
    NamedEntity,
)
from chronovista.models.entity_asr_error import EntityAsrErrorCreate
from chronovista.repositories.entity_asr_error_repository import (
    EntityAsrErrorRepository,
)
from chronovista.services.asr_alias_registry import (
    register_asr_alias,
    resolve_entity_id_from_text,
)

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


# ---------------------------------------------------------------------------
# Feature 111 US2 (Deliverable B, R1+R2): context-aware disambiguation
# ---------------------------------------------------------------------------


async def _seed_person(db_session: AsyncSession, name: str) -> NamedEntity:
    """Seed one active person entity with its normalized canonical name."""
    entity = NamedEntity(
        entity_type="person",
        canonical_name=name,
        canonical_name_normalized=name.lower(),
    )
    db_session.add(entity)
    await db_session.flush()
    return entity


async def _seed_alias(
    db_session: AsyncSession, entity: NamedEntity, alias: str
) -> None:
    """Attach a plain name-variant alias to an entity."""
    db_session.add(
        EntityAlias(
            entity_id=entity.id,
            alias_name=alias,
            alias_name_normalized=alias.lower(),
        )
    )
    await db_session.flush()


async def _seed_mention(
    db_session: AsyncSession, entity: NamedEntity, video_id: str
) -> None:
    """Record that an entity has a mention in a given video."""
    db_session.add(
        EntityMention(
            entity_id=entity.id,
            video_id=video_id,
            mention_text="placeholder",
        )
    )
    await db_session.flush()


@pytest.mark.db
@pytest.mark.integration
class TestContextAwareResolution:
    """FR-008 selection order replaces the three defective exits.

    A bare surname shared by two people ("Ada Quorne" / "Ben Quorne") is the
    running scenario: without context the old code attached to an arbitrary
    entity via ``.scalars().first()``; now it disambiguates or skips.
    """

    async def test_fast_path_adjacent_first_name_resolves_one_candidate(
        self, db_session: AsyncSession
    ) -> None:
        """Adjacent first name folding to exactly one candidate resolves it."""
        ada = await _seed_person(db_session, "Ada Quorne")
        await _seed_person(db_session, "Ben Quorne")

        result = await resolve_entity_id_from_text(
            db_session, "Quorne", adjacent_token="Ada"
        )

        assert result is not None
        entity_id, name = result
        assert entity_id == uuid.UUID(str(ada.id))
        assert name == "Ada Quorne"

    async def test_video_context_fallback_resolves_known_entity(
        self, db_session: AsyncSession
    ) -> None:
        """With no usable adjacent token, one video-known candidate resolves."""
        await _seed_person(db_session, "Ada Quorne")
        ben = await _seed_person(db_session, "Ben Quorne")
        await _seed_mention(db_session, ben, "vidQuorne01")

        # No adjacent first name; only Ben is known in this video.
        result = await resolve_entity_id_from_text(
            db_session, "Quorne", video_id="vidQuorne01"
        )

        assert result is not None
        entity_id, name = result
        assert entity_id == uuid.UUID(str(ben.id))
        assert name == "Ben Quorne"

    async def test_shared_alias_without_context_skips_and_counts(
        self, db_session: AsyncSession
    ) -> None:
        """A shared alias with no disambiguator is skipped and counted.

        This is the former arbitrary-mislink case: two entities carry the same
        alias. The resolver must not pick one; ``register_asr_alias`` reports a
        skip (the counter) and writes nothing.
        """
        ada = await _seed_person(db_session, "Ada Quorne")
        ben = await _seed_person(db_session, "Ben Quorne")
        await _seed_alias(db_session, ada, "Quorne")
        await _seed_alias(db_session, ben, "Quorne")

        # Resolver alone: never an arbitrary pick.
        assert await resolve_entity_id_from_text(db_session, "Quorne") is None

        skipped = await register_asr_alias(
            db_session,
            original_text="qorn",
            corrected_text="Quorne",
        )
        await db_session.flush()

        assert skipped == 1, "An ambiguous correction must increment the counter."

        total = (
            await db_session.execute(select(func.count()).select_from(EntityAsrError))
        ).scalar_one()
        assert total == 0, "An ambiguous correction must attach to no entity."

    async def test_shared_alias_resolved_by_adjacent_context(
        self, db_session: AsyncSession
    ) -> None:
        """The same shared-alias case resolves correctly given an adjacent name."""
        ada = await _seed_person(db_session, "Ada Quorne")
        ben = await _seed_person(db_session, "Ben Quorne")
        await _seed_alias(db_session, ada, "Quorne")
        await _seed_alias(db_session, ben, "Quorne")

        result = await resolve_entity_id_from_text(
            db_session, "Quorne", adjacent_token="Ben"
        )

        assert result is not None
        entity_id, _ = result
        assert entity_id == uuid.UUID(str(ben.id)), "Context must pick Ben, not Ada."

    async def test_r2_registers_full_name_form_beside_known_first_name(
        self, db_session: AsyncSession
    ) -> None:
        """R2 (FR-009): a disambiguated bare surname registers the full-name form."""
        ada = await _seed_person(db_session, "Ada Quorne")
        await _seed_person(db_session, "Ben Quorne")

        skipped = await register_asr_alias(
            db_session,
            original_text="qorn",
            corrected_text="Quorne",
            adjacent_token="Ada",
        )
        await db_session.flush()

        assert skipped == 0

        forms = set(
            (
                await db_session.execute(
                    select(EntityAsrError.alias_name).where(
                        EntityAsrError.entity_id == ada.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert (
            "Ada qorn" in forms
        ), "The specific full GARBLE form (adjacent first name + garble) must register."
        assert (
            "qorn" not in forms
        ), "The ambiguous bare fragment must not be registered."
        assert (
            "Ada Quorne" not in forms
        ), "The corrected name is matched via canonical/alias; it is not an error form."
