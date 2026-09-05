"""
Tests for ``scan_metadata(new_entities_only=...)``.

Regression coverage for a defect where ``scan_metadata()`` accepted no
``new_entities_only`` parameter and passed a hardcoded ``False`` to
``_load_entity_patterns``. ``scan()`` honoured the flag, so
``entities scan --new-entities-only --sources transcript,title,description``
scoped the transcript half to zero-mention entities while the metadata half
silently ran across every active entity.

Observed before the fix: a dry run reported 139,845 mentions across 369 entities
where 27 were expected.

The parameter is the whole subject here, so every test asserts on what
``_load_entity_patterns`` received rather than on scan output — output would look
identical whether the flag was honoured or ignored, which is precisely why the
bug survived.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)

# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


def _make_session_factory() -> MagicMock:
    """Session factory whose session yields no rows — enough to reach pattern
    loading, which is all these tests inspect."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    empty = MagicMock()
    empty.all.return_value = []
    empty.scalars.return_value.all.return_value = []
    session.execute.return_value = empty

    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


def _spy_on_pattern_loading(service: Any) -> dict[str, Any]:
    """Replace ``_load_entity_patterns`` with a recorder returning no patterns."""
    captured: dict[str, Any] = {}

    async def _fake(
        session: Any,
        entity_type: Any = None,
        new_entities_only: Any = False,
        entity_ids: Any = None,
    ) -> list[Any]:
        captured["entity_type"] = entity_type
        captured["new_entities_only"] = new_entities_only
        captured["entity_ids"] = entity_ids
        return []

    service._load_entity_patterns = _fake  # type: ignore[method-assign]
    return captured


class TestScanMetadataHonoursNewEntitiesOnly:
    """``scan_metadata`` must forward the flag, not hardcode it."""

    async def test_flag_true_is_forwarded(self) -> None:
        """new_entities_only=True must reach _load_entity_patterns.

        This is the regression: the call site previously passed a literal False.
        """
        service = EntityMentionScanService(_make_session_factory())
        captured = _spy_on_pattern_loading(service)

        await service.scan_metadata(sources=["title"], new_entities_only=True)

        assert captured["new_entities_only"] is True

    async def test_flag_defaults_to_false(self) -> None:
        """Omitting the flag must scan every active entity, as before."""
        service = EntityMentionScanService(_make_session_factory())
        captured = _spy_on_pattern_loading(service)

        await service.scan_metadata(sources=["description"])

        assert captured["new_entities_only"] is False

    async def test_flag_false_is_forwarded(self) -> None:
        """Explicit False behaves the same as omitting it."""
        service = EntityMentionScanService(_make_session_factory())
        captured = _spy_on_pattern_loading(service)

        await service.scan_metadata(sources=["title"], new_entities_only=False)

        assert captured["new_entities_only"] is False

    async def test_flag_composes_with_entity_type(self) -> None:
        """Both filters must arrive together, not one replacing the other."""
        service = EntityMentionScanService(_make_session_factory())
        captured = _spy_on_pattern_loading(service)

        await service.scan_metadata(
            sources=["title", "description"],
            entity_type="person",
            new_entities_only=True,
        )

        assert captured["new_entities_only"] is True
        assert captured["entity_type"] == "person"

    async def test_flag_composes_with_entity_ids(self) -> None:
        """Explicit ids and the flag are an AND filter, per _load_entity_patterns."""
        service = EntityMentionScanService(_make_session_factory())
        captured = _spy_on_pattern_loading(service)
        ids = [uuid.uuid4(), uuid.uuid4()]

        await service.scan_metadata(
            sources=["title"], new_entities_only=True, entity_ids=ids
        )

        assert captured["new_entities_only"] is True
        assert captured["entity_ids"] == ids


class TestScanAndScanMetadataAgree:
    """The two entry points maintain parallel parameter lists by hand.

    They had already drifted by exactly this parameter. These tests pin the
    signatures together so the next drift fails here rather than in production.
    """

    async def test_both_forward_the_flag_identically(self) -> None:
        """scan() and scan_metadata() must pass the same value through."""
        results: dict[str, Any] = {}

        for name, kwargs in (
            ("scan", {}),
            ("scan_metadata", {"sources": ["title"]}),
        ):
            service = EntityMentionScanService(_make_session_factory())
            captured = _spy_on_pattern_loading(service)
            await getattr(service, name)(new_entities_only=True, **kwargs)
            results[name] = captured["new_entities_only"]

        assert results["scan"] is True
        assert results["scan_metadata"] is True
        assert results["scan"] == results["scan_metadata"]

    @pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
    async def test_scan_metadata_accepts_every_filter_scan_does(self) -> None:
        """Filter parameters must not drift apart again.

        ``progress_callback`` and the source/segment-specific parameters are
        excluded: they are genuinely per-method. Everything that narrows *which
        entities* are scanned must exist on both. ``limit`` is also required on
        both: it caps a dry-run preview, and its absence from ``scan_metadata``
        is exactly what made ``--dry-run --limit`` scan every video in full
        (#290).
        """
        import inspect

        shared = {
            "entity_type",
            "video_ids",
            "language_code",
            "batch_size",
            "dry_run",
            "full_rescan",
            "new_entities_only",
            "entity_ids",
            "limit",
        }
        scan_params = set(inspect.signature(EntityMentionScanService.scan).parameters)
        meta_params = set(
            inspect.signature(EntityMentionScanService.scan_metadata).parameters
        )

        assert shared <= scan_params, shared - scan_params
        assert shared <= meta_params, shared - meta_params
