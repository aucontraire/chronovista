"""US3 parity: removing the read-exclusions doesn't change matching (SC-004/SC-005).

After Feature 110, scan patterns are built from ``entity_aliases`` with **no**
``asr_error`` exclusion — because the name store can no longer hold one. A known-error
string lives only in ``entity_asr_errors``, which the scanner never reads, so it can
never become a scan pattern (SC-004); genuine name aliases are still loaded (SC-005).

Broader matching-parity is covered by the existing scan/membership suite continuing to
pass after the exclusion removal; this test pins the specific guarantee that an
error-store form is not a scan pattern while a genuine alias is.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias, EntityAsrError, NamedEntity
from chronovista.services.entity_mention_scan_service import EntityMentionScanService

pytestmark = pytest.mark.asyncio


@pytest.mark.db
@pytest.mark.integration
class TestScanPatternsExcludeErrorStore:
    async def test_genuine_alias_loaded_error_form_not(
        self, db_session: AsyncSession
    ) -> None:
        entity = NamedEntity(
            entity_type="person",
            canonical_name="Invented Person",
            canonical_name_normalized="invented person",
        )
        db_session.add(entity)
        await db_session.flush()

        # A genuine name alias in the name store...
        db_session.add(
            EntityAlias(
                entity_id=entity.id,
                alias_name="Inv Variant",
                alias_name_normalized="inv variant",
                alias_type="name_variant",
            )
        )
        await db_session.flush()
        # ...and a known-error form in the dedicated store (never a scan input).
        db_session.add(
            EntityAsrError(
                entity_id=entity.id,
                alias_name="garbled person",
                alias_name_normalized="garbled person",
            )
        )
        await db_session.flush()

        svc = EntityMentionScanService(session_factory=MagicMock())
        patterns = await svc._load_entity_patterns(
            db_session,
            entity_type=None,
            new_entities_only=False,
            entity_ids=[entity.id],
        )

        # entity_ids was restricted to this one entity, so there is exactly one
        # pattern. (Avoid comparing entity_id across the uuid_utils/stdlib UUID
        # boundary, where equality is false despite identical string form.)
        assert len(patterns) == 1
        pattern = patterns[0]
        assert (
            "Inv Variant" in pattern.alias_names
        ), "A genuine name alias must still be loaded as a scan pattern (SC-005)."
        assert (
            "garbled person" not in pattern.alias_names
        ), "A dedicated-store error form must never become a scan pattern (SC-004)."
