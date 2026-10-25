"""Unit tests for the on-grounding Wikipedia image fallback step (Feature 094).

Covers `EntityEnrichmentService._store_wikipedia_image` in isolation — its skip/precedence logic,
the source-tagged write, the manual-image-does-not-suppress rule, and graceful degradation. The
gate itself (`WikipediaImageFallback.evaluate`) is Feature-093-tested; here a canned-`FallbackResult`
fake is injected via `image_fallback_factory` so these tests pin the STEP's orchestration, not the
gate. Neutral placeholders / synthetic filenames only (Constitution VI).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.models.wikipedia_image import FallbackOutcome, FallbackResult
from chronovista.services.entity_enrichment_service import EntityEnrichmentService

pytestmark = pytest.mark.asyncio

_EID = uuid.UUID("00000000-0000-7000-8000-000000000001")
_QID = "Q000001"


def _factory_yielding(session: Any) -> MagicMock:
    """A session_factory whose ``async with`` yields ``session`` (mirrors the sibling test)."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


class _Fallback:
    """A fake WikipediaImageFallback returning a canned result and recording calls."""

    def __init__(self, result: FallbackResult | Exception) -> None:
        self._result = result
        self.calls: list[tuple[uuid.UUID, str]] = []

    async def evaluate(self, entity_id: uuid.UUID, qid: str) -> FallbackResult:
        self.calls.append((entity_id, qid))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _stored(filename: str = "Free_Commons_Portrait.jpg") -> FallbackResult:
    return FallbackResult(
        entity_id=_EID, outcome=FallbackOutcome.STORED, filename=filename
    )


def _service(
    *, entity: Any, fallback: _Fallback, replace_rowcount: int = 1
) -> tuple[EntityEnrichmentService, AsyncMock, AsyncMock]:
    """Build the service with a mocked session + repo and the fake fallback injected."""
    session = AsyncMock()
    svc = EntityEnrichmentService(
        _factory_yielding(session), image_fallback_factory=lambda: fallback
    )
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=entity)
    repo.replace_properties = AsyncMock(return_value=replace_rowcount)
    svc._repo = repo  # type: ignore[assignment]
    return svc, repo, session


def _entity(
    properties: dict[str, Any] | None = None, *, manual_ext: str | None = None
) -> Any:
    return SimpleNamespace(
        id=_EID, properties=properties or {}, manual_image_ext=manual_ext
    )


class TestStoresOnGrounding:
    async def test_stores_wikipedia_block_when_no_automated_image(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fallback = _Fallback(_stored("Free_A.jpg"))
        svc, repo, session = _service(entity=_entity({}), fallback=fallback)

        import logging

        with caplog.at_level(logging.INFO):
            await svc._store_wikipedia_image(_EID, _QID)

        repo.replace_properties.assert_awaited_once()
        _, kwargs = repo.replace_properties.await_args
        block = kwargs["properties"]["image"]
        assert block["source"] == "wikipedia"
        assert block["values"] == ["Free_A.jpg"]
        assert session.commit.await_count == 1
        # FR-010: a successful store is logged (entity id + filename).
        assert any("Free_A.jpg" in r.message for r in caplog.records)

    async def test_manual_image_does_not_suppress_the_fetch(self) -> None:
        # Entity has a manual image (a column) but no automated image in `properties` → still fetch.
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(entity=_entity({}, manual_ext="jpg"), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        assert len(fallback.calls) == 1  # the manual column did NOT suppress the fetch
        repo.replace_properties.assert_awaited_once()


class TestPrecedenceAndSkip:
    async def test_skips_when_wikidata_p18_present(self) -> None:
        # A P18 block the property write just stored must NOT be overridden (FR-004).
        p18 = {"image": {"values": ["Real_P18.jpg"], "qids": [], "source": "wikidata"}}
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(entity=_entity(p18), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        assert fallback.calls == []  # never even fetched
        repo.replace_properties.assert_not_called()

    async def test_skips_when_prior_wikipedia_image_present(self) -> None:
        prior = {"image": {"values": ["Old.jpg"], "qids": [], "source": "wikipedia"}}
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(entity=_entity(prior), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        assert fallback.calls == []  # idempotent — already imaged
        repo.replace_properties.assert_not_called()

    @pytest.mark.parametrize(
        "image_less_properties",
        [
            {},
            {"image": {}},
            {"image": {"values": []}},
            {"image": {"values": [""]}},
            {"image": {"values": [None]}},
            {"image": "not-a-dict"},
        ],
    )
    async def test_degenerate_image_blocks_do_not_skip(
        self, image_less_properties: dict[str, Any]
    ) -> None:
        # These are "no usable automated image" → the fallback MUST run (pins the skip predicate so
        # it cannot be weakened to a plain "has an image key").
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(
            entity=_entity(image_less_properties), fallback=fallback
        )

        await svc._store_wikipedia_image(_EID, _QID)

        assert len(fallback.calls) == 1
        repo.replace_properties.assert_awaited_once()

    async def test_declined_outcome_stores_nothing(self) -> None:
        fallback = _Fallback(
            FallbackResult(entity_id=_EID, outcome=FallbackOutcome.DECLINED_NON_FREE)
        )
        svc, repo, _ = _service(entity=_entity({}), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        assert len(fallback.calls) == 1
        repo.replace_properties.assert_not_called()


class TestGracefulDegradation:
    async def test_gate_exception_does_not_raise_and_writes_nothing(self) -> None:
        # The gate normally never raises, but if it (or anything) does, the step must swallow it.
        fallback = _Fallback(RuntimeError("wikimedia exploded"))
        svc, repo, _ = _service(entity=_entity({}), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)  # must NOT raise

        repo.replace_properties.assert_not_called()

    async def test_error_outcome_writes_nothing(self) -> None:
        fallback = _Fallback(
            FallbackResult(entity_id=_EID, outcome=FallbackOutcome.ERROR, detail="boom")
        )
        svc, repo, _ = _service(entity=_entity({}), fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        repo.replace_properties.assert_not_called()

    async def test_db_write_error_does_not_raise(self) -> None:
        # A STORED outcome but the persistence raises (transient DB error) → caught, no propagation.
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(entity=_entity({}), fallback=fallback)
        repo.replace_properties = AsyncMock(side_effect=RuntimeError("db down"))

        await svc._store_wikipedia_image(_EID, _QID)  # must NOT raise

    async def test_absent_entity_is_a_noop(self) -> None:
        fallback = _Fallback(_stored())
        svc, repo, _ = _service(entity=None, fallback=fallback)

        await svc._store_wikipedia_image(_EID, _QID)

        assert fallback.calls == []
        repo.replace_properties.assert_not_called()
