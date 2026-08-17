"""Shape-parity seam: on-approval write ≡ batch load (Feature 068, T008 / SC-002 / FR-002).

The load-bearing contract: the properties the on-approval fetch writes are **structurally identical**
(excluding the per-run ``set_at``) to what a later batch load of the same entity writes — so a load's
mirror-what's-present never rewrites the app data into a different shape.

Two legs:
1. **Cross-check vs the real pipeline** (skip-if-absent): the app's ``fetch_properties`` output equals
   the gitignored ``scripts/entity_resolution/fetch_properties.py`` extractor's output on the same
   recorded claims/labels. CI must not depend on the gitignored file, so this leg skips when it is
   absent.
2. **DB round-trip parity**: writing via ``replace_properties`` (the on-approval path) and via
   ``load_enrichment`` (the batch path) persist the SAME field set / per-field ``values``/``qids``/
   ``source`` through JSONB, even when the two carry different ``set_at`` timestamps.

Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import copy
import pathlib
import sys
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_enrichment import EntityEnrichmentRecord, LedgerWikidata
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.entity_enrichment_loader import load_enrichment
from chronovista.services.wikidata_client import WikidataClient

pytestmark = pytest.mark.asyncio


def _claims() -> dict[str, Any]:
    def item(q: str) -> dict[str, Any]:
        return {
            "mainsnak": {
                "snaktype": "value",
                "datavalue": {"type": "wikibase-entityid", "value": {"id": q}},
            }
        }

    def time_(s: str, p: int) -> dict[str, Any]:
        return {
            "mainsnak": {
                "snaktype": "value",
                "datavalue": {"type": "time", "value": {"time": s, "precision": p}},
            }
        }

    return {
        "entities": {
            "Q000001": {
                "claims": {
                    "P31": [item("Q5")],
                    "P106": [item("Q000010"), item("Q000011")],
                    "P27": [item("Q000030")],
                    "P569": [time_("+1970-05-06T00:00:00Z", 11)],
                }
            }
        }
    }


def _labels() -> dict[str, Any]:
    return {
        "entities": {
            "Q5": {"labels": {"en": {"value": "human"}}},
            "Q000010": {"labels": {"en": {"value": "Placeholder Occupation A"}}},
            "Q000011": {"labels": {"mul": {"value": "Placeholder Occupation B"}}},
            "Q000030": {"labels": {"en": {"value": "Placeholder Country"}}},
        }
    }


def _transport() -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("props") == "claims":
            return httpx.Response(200, json=_claims())
        if request.url.params.get("props") == "labels":
            return httpx.Response(200, json=_labels())
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _strip_set_at(props: dict[str, Any]) -> dict[str, Any]:
    """Structural view: drop the per-run set_at from every field block."""
    return {f: {k: v for k, v in b.items() if k != "set_at"} for f, b in props.items()}


async def _fetch_app_properties() -> dict[str, Any]:
    client = WikidataClient(http=httpx.AsyncClient(transport=_transport()))
    return await client.fetch_properties("Q000001")


# The shape the app fetch MUST produce for _claims()/_labels() — hand-pinned from the pipeline's
# known field mapping + label resolution + date precision. Independent of the gitignored pipeline
# (leg 1 skips in CI) AND of leg 2's writers (mine-to-mine). This is the CI regression guard for the
# FR-002 contract: if the app's extraction/shape drifts from the pipeline, this fails. set_at excluded.
EXPECTED_APP_SHAPE: dict[str, Any] = {
    "instance_of": {"values": ["human"], "qids": ["Q5"], "source": "wikidata"},
    "occupation": {
        "values": ["Placeholder Occupation A", "Placeholder Occupation B"],
        "qids": ["Q000010", "Q000011"],
        "source": "wikidata",
    },
    "country": {
        "values": ["Placeholder Country"],
        "qids": ["Q000030"],
        "source": "wikidata",
    },
    "birth_date": {"values": ["1970-05-06"], "qids": [], "source": "wikidata"},
}


class TestParity:
    async def test_app_fetch_has_expected_pipeline_shape(self) -> None:
        """CI guard for FR-002 — the app-fetch shape is pinned, independent of the gitignored file."""
        app_props = await _fetch_app_properties()
        assert _strip_set_at(app_props) == EXPECTED_APP_SHAPE

    async def test_app_fetch_matches_real_pipeline_extractor(self) -> None:
        """Leg 1 — cross-check vs the authoritative pipeline (skip if the gitignored file is absent)."""
        pipe_path = pathlib.Path("scripts/entity_resolution")
        if not (pipe_path / "fetch_properties.py").exists():
            pytest.skip("gitignored pipeline not present; skipping cross-check leg")
        sys.path.insert(0, str(pipe_path.resolve()))
        try:
            import fetch_properties as pipe  # type: ignore[import-not-found]
        finally:
            sys.path.pop(0)

        app_props = await _fetch_app_properties()

        # Reproduce the pipeline's output on the same recorded claims/labels.
        claims = _claims()["entities"]["Q000001"]["claims"]
        labels_raw = _labels()["entities"]
        extracted = pipe.extract_claims({"claims": claims})
        label_map = {
            q: next(
                (
                    labels_raw[q]["labels"][k]["value"]
                    for k in pipe.LABEL_ORDER
                    if k in labels_raw[q]["labels"]
                ),
                None,
            )
            for q in {v for b in extracted.values() for v in b["qids"]}
        }
        label_map = {q: t for q, t in label_map.items() if t}
        pipe_props = {
            f: {
                "values": [label_map.get(q, q) for q in b["qids"]] + b["literals"],
                "qids": b["qids"],
                "source": "wikidata",
            }
            for f, b in extracted.items()
        }
        assert _strip_set_at(app_props) == pipe_props

    async def test_on_approval_write_equals_batch_load(
        self, db_session: AsyncSession
    ) -> None:
        """Leg 2 — the two writers persist structurally identical properties (differing set_at)."""
        app_props = await _fetch_app_properties()
        # Simulate a LATER batch load of the same entity: same data, different set_at.
        load_props = copy.deepcopy(app_props)
        for block in load_props.values():
            block["set_at"] = "2099-01-01T00:00:00+00:00"

        # Entity A — written by the on-approval path (replace_properties).
        a = NamedEntityDB(
            canonical_name="Placeholder A",
            canonical_name_normalized=f"placeholder a {uuid.uuid4().hex[:8]}",
            entity_type="person",
            status="active",
        )
        # Entity B — written by the batch path (load_enrichment).
        b = NamedEntityDB(
            canonical_name="Placeholder B",
            canonical_name_normalized=f"placeholder b {uuid.uuid4().hex[:8]}",
            entity_type="person",
            status="active",
        )
        # Insert one at a time — bulk add_all trips SQLAlchemy's insertmanyvalues sentinel
        # matching against the uuid_utils.UUID default.
        db_session.add(a)
        await db_session.flush()
        db_session.add(b)
        await db_session.flush()
        a_id, b_id = uuid.UUID(str(a.id)), uuid.UUID(str(b.id))

        await NamedEntityRepository().replace_properties(
            db_session, a_id, properties=app_props
        )
        record = EntityEnrichmentRecord(
            entity_id=b_id,
            canonical_name="Placeholder B",
            properties=load_props,
            wikidata=LedgerWikidata(qid="Q000001", status="found", verified=True),
        )
        await load_enrichment(db_session, [record], apply=True)
        await db_session.commit()

        rows = {
            r.id: r
            for r in (
                await db_session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id.in_([a_id, b_id]))
                )
            )
            .scalars()
            .all()
        }
        props_app = _strip_set_at(rows[a_id].properties)
        props_load = _strip_set_at(rows[b_id].properties)
        assert props_app == props_load
        # And the app write is non-empty (the fetch actually produced fields).
        assert set(props_app) == {"instance_of", "occupation", "country", "birth_date"}
