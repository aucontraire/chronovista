"""Integration tests for the manual entity-image upload API (Feature 092, US1 — T018).

Exercises ``POST /api/v1/entities/{entity_id}/image`` over real HTTP against the integration DB:
a synthetic valid image uploaded to an entity with no automated image becomes the served portrait
(``GET /images/entities/{id}``) and the detail reports ``image.source == "manual"``; a missing
entity is ``404``; a text blob renamed ``.jpg`` and an oversized file are each ``422`` with nothing
stored; and the upload invalidates any stale cached Wikidata render so the portrait reflects the
upload (quickstart Scenarios 1–2).

Synthetic images and neutral placeholder entities only — no real names, no real image files
(Constitution VI). The integration DB is shared and never reset, so entities use fresh UUIDv7 ids
and every file this module writes under ``data_dir`` / ``cache_dir`` is cleaned up.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.config.settings import settings
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.correction_actors import ACTOR_USER_LOCAL
from chronovista.repositories.entity_operation_log_repository import (
    EntityOperationLogRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.entity_curation_service import EntityCurationService
from chronovista.services.image_validation import MAX_IMAGE_BYTES

pytestmark = pytest.mark.asyncio

_PREFIX = "f092img"

# Smallest payloads whose first bytes match a supported signature — the validator checks the
# content signature, not size, so these are accepted and served verbatim.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"

# A synthetic, name-free Commons filename standing in for an automated Wikidata image, and the
# bytes of a cached Wikidata render. The render must clear ``_MIN_IMAGE_BYTES`` (1 KiB) so the
# serve path handles it as a deterministic cache HIT rather than re-fetching over the network.
_COMMONS_FILENAME = "F092_placeholder_portrait.jpg"
_WIKIDATA_RENDER_BYTES = b"\xff\xd8\xff" + b"\x22" * 2048


def _seeded_properties() -> dict[str, object]:
    """A property bag with a usable automated image, mirroring the resolver's expected shape."""
    return {
        "image": {
            "values": [_COMMONS_FILENAME],
            "set_at": "2026-01-02T03:04:05+00:00",
        }
    }


def _manual_path(entity_id: str, ext: str) -> Path:
    return settings.data_dir / "entity_images" / f"{entity_id}.{ext}"


def _render_cache_path(entity_id: str) -> Path:
    return settings.cache_dir / "images" / "entities" / f"{entity_id}.jpg"


def _cleanup_files(entity_id: str) -> None:
    for ext in ("jpg", "png", "webp"):
        _manual_path(entity_id, ext).unlink(missing_ok=True)
    render = _render_cache_path(entity_id)
    render.unlink(missing_ok=True)
    render.with_suffix(".missing").unlink(missing_ok=True)


@pytest.fixture
async def bare_entity_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[str, None]:
    """A neutral, active entity with an empty property bag (no automated image).

    The integration DB is shared and never reset, so the name carries a random suffix to avoid
    the ``(canonical_name_normalized, entity_type)`` unique constraint across tests and re-runs.
    """
    suffix = uuid.uuid4().hex[:8]
    entity = NamedEntityDB(
        id=uuid7(),
        canonical_name=f"{_PREFIX} subject {suffix}",
        canonical_name_normalized=f"{_PREFIX} subject {suffix}",
        entity_type="organization",
        status="active",
        properties={},
    )
    async with integration_session_factory() as session:
        session.add(entity)
        await session.commit()
    entity_id = str(uuid.UUID(str(entity.id)))
    try:
        yield entity_id
    finally:
        _cleanup_files(entity_id)


@pytest.fixture
async def grounded_entity_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[str, None]:
    """A neutral, Wikidata-grounded entity with a usable automated image.

    Carries ``external_ids.wikidata`` (so the re-grounding path has a link to snapshot) and a
    ``properties.image`` block (so ``has_wikidata`` is true), both synthetic/name-free. The random
    name suffix avoids the shared-DB unique constraint across tests and re-runs.
    """
    suffix = uuid.uuid4().hex[:8]
    entity = NamedEntityDB(
        id=uuid7(),
        canonical_name=f"{_PREFIX} grounded {suffix}",
        canonical_name_normalized=f"{_PREFIX} grounded {suffix}",
        entity_type="organization",
        status="active",
        external_ids={
            "wikidata": {"id": "Q424242", "verified": True, "status": "verified"}
        },
        properties=_seeded_properties(),
    )
    async with integration_session_factory() as session:
        session.add(entity)
        await session.commit()
    entity_id = str(uuid.UUID(str(entity.id)))
    try:
        yield entity_id
    finally:
        _cleanup_files(entity_id)


async def _read_image_cols(
    factory: async_sessionmaker[AsyncSession], entity_id: str
) -> tuple[str | None, object, str, dict[str, object] | None]:
    """Read the manual-image columns + properties straight from the row (test oracle)."""
    async with factory() as session:
        row = (
            await session.execute(
                select(
                    NamedEntityDB.manual_image_ext,
                    NamedEntityDB.manual_image_uploaded_at,
                    NamedEntityDB.image_source_preference,
                    NamedEntityDB.properties,
                ).where(NamedEntityDB.id == uuid.UUID(entity_id))
            )
        ).first()
    assert row is not None
    return (row[0], row[1], row[2], row[3])


class TestUploadMakesManualPortrait:
    async def test_upload_sets_manual_and_serves_portrait(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        resp = await async_client.post(
            f"/api/v1/entities/{bare_entity_id}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_manual"] is True
        assert body["has_wikidata"] is False
        assert body["source"] == "manual"
        assert body["version"]  # ISO timestamp cache-buster

        # The portrait route now serves the uploaded bytes straight from the durable store.
        served = await async_client.get(f"/api/v1/images/entities/{bare_entity_id}")
        assert served.status_code == 200
        assert served.content == _PNG_BYTES
        assert served.headers["X-Cache"] == "MANUAL"
        assert served.headers["content-type"] == "image/png"

        # The detail response carries the additive image-state object.
        detail = await async_client.get(f"/api/v1/entities/{bare_entity_id}")
        assert detail.status_code == 200
        image = detail.json()["data"]["image"]
        assert image["source"] == "manual"
        assert image["has_manual"] is True
        assert image["has_wikidata"] is False
        assert image["version"] == body["version"]

    async def test_upload_invalidates_stale_render(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        # Seed a stale cached Wikidata render; the upload must invalidate it so the portrait
        # reflects the new manual image rather than the stale cache.
        render = _render_cache_path(bare_entity_id)
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"\xff\xd8\xff" + b"\x11" * 2048)
        assert render.is_file()

        resp = await async_client.post(
            f"/api/v1/entities/{bare_entity_id}/image",
            files={"file": ("portrait.jpg", _JPEG_BYTES, "image/jpeg")},
        )
        assert resp.status_code == 200

        assert not render.is_file()  # invalidated
        served = await async_client.get(f"/api/v1/images/entities/{bare_entity_id}")
        assert served.status_code == 200
        assert served.content == _JPEG_BYTES


class TestUploadRejections:
    async def test_404_for_unknown_entity(self, async_client: AsyncClient) -> None:
        missing = str(uuid.uuid4())
        resp = await async_client.post(
            f"/api/v1/entities/{missing}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert resp.status_code == 404
        # Nothing stored for a non-existent entity.
        assert not _manual_path(missing, "png").is_file()

    async def test_422_for_mislabeled_text(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        resp = await async_client.post(
            f"/api/v1/entities/{bare_entity_id}/image",
            files={
                "file": ("portrait.jpg", b"this is plainly not an image", "image/jpeg")
            },
        )
        assert resp.status_code == 422
        # No partial file stored on rejection, and the portrait falls back to the placeholder.
        for ext in ("jpg", "png", "webp"):
            assert not _manual_path(bare_entity_id, ext).is_file()
        served = await async_client.get(f"/api/v1/images/entities/{bare_entity_id}")
        assert served.headers["content-type"] == "image/svg+xml"

    async def test_422_for_oversized(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_BYTES + 1)
        resp = await async_client.post(
            f"/api/v1/entities/{bare_entity_id}/image",
            files={"file": ("portrait.jpg", oversized, "image/jpeg")},
        )
        assert resp.status_code == 422
        for ext in ("jpg", "png", "webp"):
            assert not _manual_path(bare_entity_id, ext).is_file()


class TestManualImageSurvivesEnrichment:
    """US2 / T020 — the manual image is never clobbered by enrichment (FR-010, FR-009).

    Exercises the real enrichment write paths against the integration DB: a re-grounding
    (``EntityCurationService.reground_entity``, which full-replaces ``external_ids`` and clears
    ``properties`` synchronously) followed by a property refetch (``replace_properties``, the
    background-fetch write). The three manual-image columns, the file on disk, and the served
    portrait must all be unchanged across both, and the automated image must be available again.
    """

    async def test_reground_and_refetch_preserve_manual_image(
        self,
        async_client: AsyncClient,
        grounded_entity_id: str,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = grounded_entity_id

        # Upload a manual image to the grounded entity.
        up = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert up.status_code == 200

        before_ext, before_uploaded_at, before_pref, _ = await _read_image_cols(
            integration_session_factory, eid
        )
        assert before_ext == "png"
        assert before_uploaded_at is not None
        assert before_pref == "manual"
        manual_file = _manual_path(eid, "png")
        assert manual_file.is_file()
        original_bytes = manual_file.read_bytes()

        served_before = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served_before.status_code == 200
        assert served_before.content == _PNG_BYTES
        assert served_before.headers["X-Cache"] == "MANUAL"

        entity_repo = NamedEntityRepository()
        curation = EntityCurationService(
            named_entity_repo=entity_repo,
            operation_log_repo=EntityOperationLogRepository(),
        )

        # Re-grounding clears properties synchronously — the automated image vanishes here, so
        # this is the write the manual image must survive.
        async with integration_session_factory() as session:
            await curation.reground_entity(
                session, uuid.UUID(eid), qid="Q999999", actor=ACTOR_USER_LOCAL
            )
            await session.commit()

        mid_ext, mid_uploaded_at, mid_pref, mid_props = await _read_image_cols(
            integration_session_factory, eid
        )
        # Automated facts cleared, but the manual image is untouched by the reground.
        assert "image" not in (mid_props or {})
        assert mid_ext == "png"
        assert mid_uploaded_at == before_uploaded_at
        assert mid_pref == "manual"

        # The property refetch (background-fetch write path) re-populates properties.image.
        async with integration_session_factory() as session:
            await entity_repo.replace_properties(
                session, uuid.UUID(eid), properties=_seeded_properties()
            )
            await session.commit()

        after_ext, after_uploaded_at, after_pref, _ = await _read_image_cols(
            integration_session_factory, eid
        )
        assert after_ext == before_ext
        assert after_uploaded_at == before_uploaded_at
        assert after_pref == before_pref
        assert manual_file.is_file()
        assert manual_file.read_bytes() == original_bytes

        served_after = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served_after.status_code == 200
        assert served_after.content == _PNG_BYTES
        assert served_after.headers["X-Cache"] == "MANUAL"

        # FR-009: the automated image is available again so the switch-to-automated target exists.
        detail = await async_client.get(f"/api/v1/entities/{eid}")
        assert detail.status_code == 200
        image = detail.json()["data"]["image"]
        assert image["has_wikidata"] is True
        assert image["has_manual"] is True
        assert image["source"] == "manual"


class TestSwitchImageSource:
    """US3 / T024 — toggle the displayed source without re-uploading (FR-007)."""

    async def test_toggle_between_sources_without_reupload(
        self, async_client: AsyncClient, grounded_entity_id: str
    ) -> None:
        eid = grounded_entity_id

        up = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert up.status_code == 200
        manual_file = _manual_path(eid, "png")
        assert manual_file.is_file()

        # Switch to the automated source.
        patch_w = await async_client.patch(
            f"/api/v1/entities/{eid}/image/source", json={"source": "wikidata"}
        )
        assert patch_w.status_code == 200
        assert patch_w.json()["source"] == "wikidata"

        detail = await async_client.get(f"/api/v1/entities/{eid}")
        assert detail.json()["data"]["image"]["source"] == "wikidata"
        # The uploaded file is retained, so switching back needs no re-upload.
        assert manual_file.is_file()

        # Serve the Wikidata image. The PATCH invalidated any prior render, so seed a cached
        # render afterwards — the serve path returns it via a deterministic HIT (no network).
        render = _render_cache_path(eid)
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(_WIKIDATA_RENDER_BYTES)
        served_w = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served_w.status_code == 200
        assert served_w.content == _WIKIDATA_RENDER_BYTES
        assert served_w.headers["X-Cache"] == "HIT"

        # Switch back to manual → the uploaded image serves again, no re-upload.
        patch_m = await async_client.patch(
            f"/api/v1/entities/{eid}/image/source", json={"source": "manual"}
        )
        assert patch_m.status_code == 200
        assert patch_m.json()["source"] == "manual"
        served_m = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served_m.status_code == 200
        assert served_m.content == _PNG_BYTES
        assert served_m.headers["X-Cache"] == "MANUAL"

    async def test_patch_manual_without_upload_conflicts(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        resp = await async_client.patch(
            f"/api/v1/entities/{bare_entity_id}/image/source",
            json={"source": "manual"},
        )
        assert resp.status_code == 409

    async def test_patch_404_for_unknown_entity(
        self, async_client: AsyncClient
    ) -> None:
        missing = str(uuid.uuid4())
        resp = await async_client.patch(
            f"/api/v1/entities/{missing}/image/source", json={"source": "wikidata"}
        )
        assert resp.status_code == 404


class TestReplaceAndRemove:
    """US4 / T028 — replace (no orphan), remove (revert), idempotent, graceful fallback."""

    async def test_replace_different_extension_leaves_no_orphan(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        eid = bare_entity_id

        a = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("a.png", _PNG_BYTES, "image/png")},
        )
        assert a.status_code == 200
        assert _manual_path(eid, "png").is_file()

        # Replace with a different extension.
        b = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("b.jpg", _JPEG_BYTES, "image/jpeg")},
        )
        assert b.status_code == 200
        # B is the current file; A's file is gone (no orphan on disk).
        assert _manual_path(eid, "jpg").is_file()
        assert not _manual_path(eid, "png").is_file()

        served = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served.status_code == 200
        assert served.content == _JPEG_BYTES
        assert served.headers["content-type"] == "image/jpeg"
        assert served.headers["X-Cache"] == "MANUAL"

    async def test_delete_reverts_and_is_idempotent(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        eid = bare_entity_id

        up = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert up.status_code == 200
        assert _manual_path(eid, "png").is_file()

        d1 = await async_client.delete(f"/api/v1/entities/{eid}/image")
        assert d1.status_code == 204
        assert not _manual_path(eid, "png").is_file()

        detail = await async_client.get(f"/api/v1/entities/{eid}")
        image = detail.json()["data"]["image"]
        assert image["has_manual"] is False
        assert image["source"] == "wikidata"

        # No automated image on this bare entity → the portrait reverts to the placeholder.
        served = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/svg+xml"

        # A second DELETE is a no-op success.
        d2 = await async_client.delete(f"/api/v1/entities/{eid}/image")
        assert d2.status_code == 204

    async def test_missing_manual_file_falls_back_gracefully(
        self, async_client: AsyncClient, bare_entity_id: str
    ) -> None:
        eid = bare_entity_id

        up = await async_client.post(
            f"/api/v1/entities/{eid}/image",
            files={"file": ("portrait.png", _PNG_BYTES, "image/png")},
        )
        assert up.status_code == 200

        # Remove the file out-of-band; the preference stays 'manual'.
        _manual_path(eid, "png").unlink()

        # The resolver must fall through to the automated path/placeholder — never a 500 (FR-014).
        served = await async_client.get(f"/api/v1/images/entities/{eid}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/svg+xml"

    async def test_delete_404_for_unknown_entity(
        self, async_client: AsyncClient
    ) -> None:
        missing = str(uuid.uuid4())
        resp = await async_client.delete(f"/api/v1/entities/{missing}/image")
        assert resp.status_code == 404
