"""Graceful degradation for on-approval enrichment (Feature 068, T016 / US2, FR-006/FR-006a).

The fetch runs in a detached background task, so a failure must never propagate (it would surface an
unretrieved-exception traceback) and must leave the entity grounded. Instead it is logged at warning
level with the entity id + reason, and no properties are written. Also covers the silent-no-op guard:
a write that matches no row (rowcount 0) logs rather than passing unnoticed. Neutral placeholders.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from chronovista.services.wikidata_client import WikidataUnavailable

pytestmark = pytest.mark.asyncio


class _UnavailableClient:
    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        raise WikidataUnavailable("knowledge base unreachable")


class _BrokenClient:
    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        raise ValueError("unexpected parse error")


class _OkClient:
    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return {"occupation": {"values": ["x"], "qids": [], "source": "wikidata"}}


def _factory_yielding(session: Any) -> MagicMock:
    """A session_factory whose ``async with`` yields ``session``."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


class TestDegradation:
    async def test_wikidata_unavailable_is_swallowed_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        entity_id = uuid.uuid4()
        # A session factory that must NOT be used when the fetch fails before any write.
        factory = MagicMock(name="session_factory")
        service = EntityEnrichmentService(
            factory, client_factory=lambda: _UnavailableClient()
        )

        with caplog.at_level(logging.WARNING):
            # Must NOT raise — a detached task exception would surface as an ugly traceback.
            await service.enrich_on_approval(entity_id, "Q000009")

        assert (
            factory.call_count == 0
        ), "no DB session should be opened on fetch failure"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "a warning must be logged on failure (FR-006a)"
        joined = " ".join(r.getMessage() for r in warnings)
        assert str(entity_id) in joined, "the warning must name the entity id"

    async def test_unexpected_exception_is_swallowed_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        entity_id = uuid.uuid4()
        service = EntityEnrichmentService(
            MagicMock(), client_factory=lambda: _BrokenClient()
        )
        with caplog.at_level(logging.WARNING):
            await service.enrich_on_approval(entity_id, "Q000009")
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    async def test_zero_row_write_logs_and_does_not_commit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The entity vanished between commit and the background task: replace_properties matches no
        # row (rowcount 0). It must log rather than silently no-op, and must NOT commit.
        entity_id = uuid.uuid4()
        session = MagicMock()
        result = MagicMock()
        result.rowcount = 0
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        service = EntityEnrichmentService(
            _factory_yielding(session), client_factory=lambda: _OkClient()
        )
        with caplog.at_level(logging.WARNING):
            await service.enrich_on_approval(entity_id, "Q000009")
        assert session.commit.await_count == 0, "no commit when nothing was written"
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "no row" in joined and str(entity_id) in joined
