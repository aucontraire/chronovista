"""Tests for ChannelRepository.titles_for_ids (ownership promotion support, read-only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.channel_repository import ChannelRepository

pytestmark = pytest.mark.asyncio


async def test_empty_ids_short_circuits() -> None:
    session = AsyncMock(spec=AsyncSession)
    assert await ChannelRepository().titles_for_ids(session, []) == {}
    session.execute.assert_not_awaited()


async def test_maps_present_ids_to_titles() -> None:
    session = AsyncMock(spec=AsyncSession)
    a = MagicMock()
    a.channel_id, a.title = "UCaaa", "Channel A"
    b = MagicMock()
    b.channel_id, b.title = "UCbbb", "Channel B"
    result = MagicMock()
    result.all.return_value = [a, b]
    session.execute.return_value = result
    # "UCccc" is not in the library -> simply absent from the result (caller reads it as external).
    out = await ChannelRepository().titles_for_ids(session, ["UCaaa", "UCbbb", "UCccc"])
    assert out == {"UCaaa": "Channel A", "UCbbb": "Channel B"}
