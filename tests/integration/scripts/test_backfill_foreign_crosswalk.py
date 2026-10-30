"""Feature 100 (US2/US3): ``backfill_foreign_categories`` against the real integration DB.

The script's own ``db_manager.session`` is pointed at the test session and its capture dir at a
tmp path; the cross-walk's Wikidata + per-language fetch are stubbed (no live network). Verifies the
dry-run/apply gate, the reversible capture, idempotency, the Cross-Feature Data Contract (visible
THROUGH the Feature 083 shared-category bridge), and reversal. Placeholder names/categories only.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import EntityCategory, NamedEntity, WikipediaCategory
from chronovista.repositories.entity_category_repository import EntityCategoryRepository
from chronovista.services.category_size import CategorySizeService
from scripts.utilities import backfill_foreign_categories as bfc

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

assign_repo = EntityCategoryRepository()


class _StubSizes(CategorySizeService):
    async def sizes_for(self, names: Any) -> dict[str, int]:
        return {}


class _StubWikidata:
    """Wikidata stub: entity sitelinks (foreign-only) + category-item enwiki sitelinks."""

    def __init__(
        self,
        entity_sitelinks: dict[str, dict[str, str]],
        category_sitelinks: dict[str, dict[str, str]],
    ) -> None:
        self._merged = {**entity_sitelinks, **category_sitelinks}

    async def fetch_sitelinks(self, qids: list[str]) -> dict[str, dict[str, str]]:
        return {q: self._merged.get(q, {}) for q in qids}


class _StubFetch:
    def __init__(self, cats: dict[str, list[str]], cat_qids: dict[str, str]) -> None:
        self._cats = cats
        self._cat_qids = cat_qids

    async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
        return {t: self._cats.get(t, []) for t in titles}

    async def wikibase_items_for_categories(self, titles: Any) -> dict[str, str]:
        return {t: self._cat_qids[t] for t in titles if t in self._cat_qids}


@pytest.fixture
def wired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, db_session: AsyncSession
) -> Path:
    @asynccontextmanager
    async def _session(**_: Any) -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(db_manager, "session", _session)
    capture = tmp_path / "capture"
    monkeypatch.setattr(bfc, "_CAPTURE_DIR", capture)
    monkeypatch.setattr(bfc, "_INTER_ENTITY_PAUSE", 0.0)
    return capture


async def _seed_foreign_only(session: AsyncSession, qid: str) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    entity = NamedEntity(
        id=uuid.uuid4(),
        canonical_name=f"Seam {suffix}",
        canonical_name_normalized=f"seam {suffix}",
        entity_type="person",
        status="active",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={},
    )
    session.add(entity)
    await session.commit()
    return uuid.UUID(str(entity.id))


def _two_entity_shared_setup() -> tuple[_StubWikidata, dict[str, _StubFetch]]:
    wikidata = _StubWikidata(
        entity_sitelinks={"Q7001": {"eswiki": "Art P"}, "Q7002": {"eswiki": "Art Q"}},
        category_sitelinks={
            "QC1": {"enwiki": "Category:Shared"},
            "QC2": {"enwiki": "Category:P only"},
            "QC3": {"enwiki": "Category:Q only"},
        },
    )
    fetch = {
        "es": _StubFetch(
            cats={
                "Art P": ["Cat_es:Shared", "Cat_es:P"],
                "Art Q": ["Cat_es:Shared", "Cat_es:Q"],
            },
            cat_qids={
                "Cat_es:Shared": "QC1",
                "Cat_es:P": "QC2",
                "Cat_es:Q": "QC3",
            },
        )
    }
    return wikidata, fetch


async def _count_categories(session: AsyncSession, entity_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(EntityCategory)
                .where(EntityCategory.entity_id == entity_id)
            )
        ).scalar_one()
    )


class TestBackfillForeignCrosswalk:
    async def test_dry_run_plans_but_writes_nothing(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        eid = await _seed_foreign_only(db_session, "Q7001")
        wikidata, fetch = _two_entity_shared_setup()

        plan = await bfc.build_plan(
            wikidata_client=wikidata,  # type: ignore[arg-type]
            size_service=_StubSizes(),
            fetch_factory=lambda lang: fetch[lang],  # type: ignore[arg-type,return-value]
        )
        assert any(e == eid for e, _n, _l in plan.to_write)
        # build_plan is read-only: no assignments written, no capture file.
        assert await _count_categories(db_session, eid) == 0
        assert not wired.exists()

    async def test_apply_writes_wikipedia_source_and_capture(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        eid = await _seed_foreign_only(db_session, "Q7001")
        wikidata, fetch = _two_entity_shared_setup()
        plan = await bfc.build_plan(
            wikidata_client=wikidata,  # type: ignore[arg-type]
            size_service=_StubSizes(),
            fetch_factory=lambda lang: fetch[lang],  # type: ignore[arg-type,return-value]
        )
        await bfc._apply(
            plan,
            "testdb",
            cat_repo=bfc.WikipediaCategoryRepository(),
            assign_repo=assign_repo,
        )

        sources = (
            (
                await db_session.execute(
                    select(EntityCategory.source).where(EntityCategory.entity_id == eid)
                )
            )
            .scalars()
            .all()
        )
        assert set(sources) == {"wikipedia"}
        assert len(sources) == 2  # Shared + "P only"

        captures = list(wired.glob("foreign_category_crosswalk_capture_*.json"))
        assert len(captures) == 1
        payload = json.loads(captures[0].read_text())
        inserted = payload["assignments_inserted"]
        assert any(row["source_langs"] for row in inserted)  # audit trail present

    async def test_idempotent_and_visible_through_bridge(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        p = await _seed_foreign_only(db_session, "Q7001")
        q = await _seed_foreign_only(db_session, "Q7002")
        wikidata, fetch = _two_entity_shared_setup()

        async def _run() -> None:
            plan = await bfc.build_plan(
                wikidata_client=wikidata,  # type: ignore[arg-type]
                size_service=_StubSizes(),
                fetch_factory=lambda lang: fetch[lang],  # type: ignore[arg-type,return-value]
            )
            await bfc._apply(
                plan,
                "testdb",
                cat_repo=bfc.WikipediaCategoryRepository(),
                assign_repo=assign_repo,
            )

        await _run()
        first = await _count_categories(db_session, p)
        # Second pass RE-QUERIES eligibility: P now has categories, so the NOT EXISTS clause
        # excludes it from the plan — eligibility-level idempotency (no re-processing).
        await _run()
        assert await _count_categories(db_session, p) == first  # unchanged (FR-015)

        # Cross-Feature Data Contract (SC-005): P neighbors Q via the cross-walked "Shared" category.
        neighbors = await assign_repo.shared_category_bridge(db_session, p)
        assert (uuid.UUID(str(q)), "Shared") in {
            (uuid.UUID(str(n.neighbor_id)), n.shared_category) for n in neighbors
        }

    async def test_reapplying_same_plan_is_conflict_safe(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        # Exercises the ON CONFLICT DO NOTHING path directly: apply the SAME plan twice (bypassing
        # the eligibility re-query), so the second apply re-adds the identical assignments and must
        # create no duplicate rows (the add-only write-level idempotency, FR-015).
        p = await _seed_foreign_only(db_session, "Q7001")
        wikidata, fetch = _two_entity_shared_setup()
        plan = await bfc.build_plan(
            wikidata_client=wikidata,  # type: ignore[arg-type]
            size_service=_StubSizes(),
            fetch_factory=lambda lang: fetch[lang],  # type: ignore[arg-type,return-value]
        )
        await bfc._apply(
            plan,
            "testdb",
            cat_repo=bfc.WikipediaCategoryRepository(),
            assign_repo=assign_repo,
        )
        first = await _count_categories(db_session, p)
        await bfc._apply(  # re-apply the identical plan — hits ON CONFLICT DO NOTHING
            plan,
            "testdb",
            cat_repo=bfc.WikipediaCategoryRepository(),
            assign_repo=assign_repo,
        )
        assert first == 2
        assert await _count_categories(db_session, p) == first  # no duplicate rows

    async def test_apply_refused_without_matching_confirm_target(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        eid = await _seed_foreign_only(db_session, "Q7001")
        # current_database() is the real test DB, never "definitely-not-the-db".
        code = await bfc.run_backfill(
            apply=True, confirm_target="definitely-not-the-db"
        )
        assert code == 2
        assert await _count_categories(db_session, eid) == 0  # refusal wrote nothing

    async def test_reverse_from_capture_restores_prior_state(
        self, wired: Path, db_session: AsyncSession
    ) -> None:
        # US3: applying then deleting exactly the captured (entity, category) assignments restores
        # the prior zero-category state.
        eid = await _seed_foreign_only(db_session, "Q7001")
        wikidata, fetch = _two_entity_shared_setup()
        plan = await bfc.build_plan(
            wikidata_client=wikidata,  # type: ignore[arg-type]
            size_service=_StubSizes(),
            fetch_factory=lambda lang: fetch[lang],  # type: ignore[arg-type,return-value]
        )
        await bfc._apply(
            plan,
            "testdb",
            cat_repo=bfc.WikipediaCategoryRepository(),
            assign_repo=assign_repo,
        )
        assert await _count_categories(db_session, eid) > 0

        # Reverse using ONLY the captured (entity, category) pairs — proving the capture is
        # self-sufficient for a precise, category-scoped rollback (not a blanket per-entity wipe).
        capture = json.loads(
            next(wired.glob("foreign_category_crosswalk_capture_*.json")).read_text()
        )
        for row in capture["assignments_inserted"]:
            ent = uuid.UUID(row["entity_id"])
            for name in row["categories"]:
                cat_id = (
                    await db_session.execute(
                        select(WikipediaCategory.id).where(
                            WikipediaCategory.name == name
                        )
                    )
                ).scalar_one()
                await db_session.execute(
                    delete(EntityCategory).where(
                        EntityCategory.entity_id == ent,
                        EntityCategory.category_id == cat_id,
                    )
                )
        await db_session.commit()
        assert await _count_categories(db_session, eid) == 0  # back to prior state
