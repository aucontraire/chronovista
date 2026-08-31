"""Unit tests for NamedEntityRepository.find_by_name_or_alias (issue #256).

Mocks the session so each branch of the canonical → alias → resolve fallback is
exercised deterministically. The real SQL is validated separately against the DB.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio


class TestFindByNameOrAlias:
    """Tests for NamedEntityRepository.find_by_name_or_alias."""

    @pytest.fixture
    def repository(self) -> NamedEntityRepository:
        return NamedEntityRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_canonical_name_hit_returns_immediately(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """A canonical-name match returns without touching the alias table."""
        entity_id = uuid.uuid4()
        canonical_result = MagicMock()
        canonical_result.first.return_value = SimpleNamespace(
            id=entity_id, canonical_name="Acme Corp"
        )
        mock_session.execute.return_value = canonical_result

        result = await repository.find_by_name_or_alias(mock_session, "acme corp")

        assert result == (entity_id, "Acme Corp")
        mock_session.execute.assert_called_once()  # no alias lookup

    async def test_alias_hit_resolves_canonical_name(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """On a canonical miss, an alias match resolves the entity's canonical name."""
        entity_id = uuid.uuid4()
        canonical_miss = MagicMock()
        canonical_miss.first.return_value = None
        alias_hit = MagicMock()
        alias_hit.first.return_value = SimpleNamespace(
            entity_id=entity_id, alias_name="ACME"
        )
        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = "Acme Corp"
        mock_session.execute.side_effect = [canonical_miss, alias_hit, name_result]

        result = await repository.find_by_name_or_alias(mock_session, "acme")

        assert result == (entity_id, "Acme Corp")
        assert mock_session.execute.call_count == 3

    async def test_no_match_returns_none_none(
        self, repository: NamedEntityRepository, mock_session: MagicMock
    ) -> None:
        """No canonical and no alias match returns (None, None)."""
        miss = MagicMock()
        miss.first.return_value = None
        mock_session.execute.side_effect = [miss, miss]

        result = await repository.find_by_name_or_alias(mock_session, "nonexistent")

        assert result == (None, None)
        assert mock_session.execute.call_count == 2
