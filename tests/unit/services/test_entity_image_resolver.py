"""Unit tests for ``ImageCacheService.get_entity_image`` precedence (Feature 092, T011).

The resolver is the single place where (manual columns, source preference, properties.image)
are reduced to one displayed portrait. These tests pin its precedence offline — a fake session
returns the entity row and a temp ``data_dir`` holds synthetic bytes; no network, no database.

Cases (FR-006, FR-014):
  * manual pref + file present            → serve the manual image
  * manual pref + file missing            → fall through (here: a cached Wikidata render)
  * wikidata pref (cached render present)  → serve the Wikidata render
  * neither manual nor wikidata            → placeholder
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.services.image_cache import ImageCacheConfig, ImageCacheService

pytestmark = pytest.mark.asyncio

_EID = str(uuid.UUID(int=1))
_MANUAL_BYTES = b"\xff\xd8\xff\xe0manual-portrait" + b"\x00" * 2048
_WIKIDATA_RENDER = b"\x89PNG\r\n\x1a\nwikidata-render" + b"\x00" * 2048


def _service(tmp_path: Path) -> ImageCacheService:
    config = ImageCacheConfig(
        cache_dir=tmp_path / "cache",
        channels_dir=tmp_path / "cache" / "channels",
        videos_dir=tmp_path / "cache" / "videos",
        entities_dir=tmp_path / "cache" / "entities",
        manual_images_dir=tmp_path / "data" / "entity_images",
    )
    return ImageCacheService(config=config)


class _FakeResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def first(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeSession:
    """Returns one fixed ``(manual_ext, source_pref, properties)`` row for any query."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    async def execute(self, *args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult(self._row)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class TestGetEntityImagePrecedence:
    async def test_manual_pref_with_file_serves_manual(self, tmp_path: Path) -> None:
        service = _service(tmp_path)
        _write(tmp_path / "data" / "entity_images" / f"{_EID}.jpg", _MANUAL_BYTES)
        session = _FakeSession(("jpg", "manual", None))
        response = await service.get_entity_image(cast(AsyncSession, session), _EID)
        assert response.headers["X-Cache"] == "MANUAL"
        assert response.body == _MANUAL_BYTES

    async def test_manual_pref_missing_file_falls_through_to_wikidata(
        self, tmp_path: Path
    ) -> None:
        service = _service(tmp_path)
        # No manual file on disk; a prior Wikidata render is cached.
        _write(tmp_path / "cache" / "entities" / f"{_EID}.jpg", _WIKIDATA_RENDER)
        session = _FakeSession(("jpg", "manual", None))
        response = await service.get_entity_image(cast(AsyncSession, session), _EID)
        assert response.headers["X-Cache"] == "HIT"
        assert response.body == _WIKIDATA_RENDER

    async def test_wikidata_pref_serves_cached_render(self, tmp_path: Path) -> None:
        service = _service(tmp_path)
        _write(tmp_path / "cache" / "entities" / f"{_EID}.jpg", _WIKIDATA_RENDER)
        session = _FakeSession((None, "wikidata", None))
        response = await service.get_entity_image(cast(AsyncSession, session), _EID)
        assert response.headers["X-Cache"] == "HIT"
        assert response.body == _WIKIDATA_RENDER

    async def test_no_image_serves_placeholder(self, tmp_path: Path) -> None:
        service = _service(tmp_path)
        session = _FakeSession((None, "wikidata", None))
        response = await service.get_entity_image(cast(AsyncSession, session), _EID)
        assert response.headers["X-Cache"] == "PLACEHOLDER"
        assert response.media_type == "image/svg+xml"

    async def test_manual_pref_wins_over_cached_wikidata_render(
        self, tmp_path: Path
    ) -> None:
        # A stale Wikidata render on disk must NOT pre-empt a 'manual' preference whose
        # file exists — precedence is decided before the cache HIT check.
        service = _service(tmp_path)
        _write(tmp_path / "data" / "entity_images" / f"{_EID}.jpg", _MANUAL_BYTES)
        _write(tmp_path / "cache" / "entities" / f"{_EID}.jpg", _WIKIDATA_RENDER)
        session = _FakeSession(("jpg", "manual", None))
        response = await service.get_entity_image(cast(AsyncSession, session), _EID)
        assert response.headers["X-Cache"] == "MANUAL"
        assert response.body == _MANUAL_BYTES
