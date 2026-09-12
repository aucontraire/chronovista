"""``GET /images/entities/{entity_id}`` — entity portrait proxy (Feature 079, US3).

Covers the two NO-NETWORK paths through the REAL endpoint (never hits Wikimedia):

(a) no ``properties.image`` -> SVG placeholder (``X-Cache: PLACEHOLDER``).
(b) a pre-existing valid cache file -> served straight from cache (``X-Cache: HIT``), which is
    reached BEFORE any DB lookup or network fetch — proving the cache-hit short circuit for real.

The router's module-level ``_image_cache_service`` (``src/chronovista/api/routers/images.py``) is
built once at import time from ``settings.cache_dir / "images" / "entities"`` — there is no
per-request override, so the cache-HIT path is exercised by writing a fake cached file into that
REAL directory under a fresh, random entity id (never colliding with a real cached portrait), then
deleting it in a ``finally`` block so the run leaves the developer's (gitignored) cache directory
exactly as it found it.

Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.config.settings import settings
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

# Real magic bytes for a JPEG (0xFF 0xD8 0xFF), padded past the service's 1024-byte
# corruption-detection floor (`_MIN_IMAGE_BYTES` in `image_cache.py`).
_FAKE_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 2000

_ENTITIES_CACHE_DIR = settings.cache_dir / "images" / "entities"


async def _seed_entity(
    factory: async_sessionmaker[AsyncSession], *, properties: dict[str, object]
) -> uuid.UUID:
    entity = create_named_entity_db(
        canonical_name=f"Placeholder ImageProxy {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder imageproxy {uuid.uuid4().hex[:8]}",
        entity_type="person",
        properties=properties,
    )
    async with factory() as s:
        s.add(entity)
        await s.commit()
        return uuid.UUID(str(entity.id))


async def test_no_image_property_serves_placeholder(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An entity with no ``properties.image`` degrades to the SVG placeholder, never an error."""
    entity_id = await _seed_entity(integration_session_factory, properties={})

    resp = await async_client.get(f"/api/v1/images/entities/{entity_id}")

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-cache"] == "PLACEHOLDER"
    assert resp.headers["content-type"].startswith("image/svg+xml")


async def test_cache_hit_serves_bytes_from_disk_no_network(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A pre-existing cache file is served as-is — the HIT path never touches the network."""
    entity_id = await _seed_entity(
        integration_session_factory,
        properties={
            "image": {
                "values": ["Placeholder_Portrait.jpg"],
                "qids": [],
                "source": "wikidata",
                "set_at": "2026-01-01T00:00:00+00:00",
            }
        },
    )
    cache_path = _ENTITIES_CACHE_DIR / f"{entity_id}.jpg"
    _ENTITIES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(_FAKE_JPEG_BYTES)

    try:
        resp = await async_client.get(f"/api/v1/images/entities/{entity_id}")
    finally:
        cache_path.unlink(missing_ok=True)

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-cache"] == "HIT"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == _FAKE_JPEG_BYTES
