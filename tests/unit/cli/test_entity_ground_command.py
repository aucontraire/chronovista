"""Unit tests for `chronovista entities ground` — wiring only.

`db_manager`, `NamedEntityRepository`, and the enrichment service are mocked; `CliRunner`
drives the command. These assert the command sets the structured Wikidata grounding via
`add_external_id`, commits, and calls the on-approval enrichment seam with the right
(entity_id, qid) — plus the two validation guards. The real ground+enrich seam is exercised
against a live entity, not here (the mocks would hide a seam defect — see the project's
"test the seam, not the mock" note).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app

runner = CliRunner()


def _session_cm(mock_session: AsyncMock) -> Any:
    @asynccontextmanager
    async def _cm(*args: Any, **kwargs: Any) -> Any:
        yield mock_session

    return _cm


def _reloaded(entity_id: uuid.UUID) -> MagicMock:
    r = MagicMock()
    r.id = entity_id
    r.canonical_name = "Some Event"
    r.entity_type = "event"
    r.description = None
    r.properties = {"instance_of": {"qids": ["Q198"]}}
    r.external_ids = {"wikidata": {"id": "Q42", "verified": True, "status": "verified"}}
    return r


class TestGroundCommand:
    def test_grounds_and_enriches_by_id(self) -> None:
        eid = uuid.uuid4()
        entity = MagicMock(id=eid)
        repo = MagicMock()
        repo.get = AsyncMock(return_value=entity)
        repo.add_external_id = AsyncMock(return_value=1)
        repo.get_with_aliases = AsyncMock(return_value=_reloaded(eid))
        enrichment = MagicMock()
        enrichment.enrich_on_approval = AsyncMock()
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository",
                return_value=repo,
            ),
            patch(
                "chronovista.cli.entity_commands.get_enrichment_service",
                return_value=enrichment,
            ),
        ):
            mock_db.session = _session_cm(mock_session)
            result = runner.invoke(
                entity_app, ["ground", str(eid), "--wikidata", "Q42"]
            )

        assert result.exit_code == 0, result.output
        # grounding: add_external_id merged a structured wikidata identifier
        repo.add_external_id.assert_awaited_once()
        kwargs = repo.add_external_id.await_args.kwargs
        assert kwargs["source"] == "wikidata"
        assert kwargs["identifier"]["id"] == "Q42"
        assert mock_session.commit.await_count == 1
        # enrichment ran with the resolved id + qid
        enrichment.enrich_on_approval.assert_awaited_once_with(eid, "Q42")

    def test_invalid_qid_exits_without_db(self) -> None:
        repo = MagicMock()
        repo.get = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository",
                return_value=repo,
            ),
        ):
            mock_db.session = _session_cm(AsyncMock())
            result = runner.invoke(
                entity_app, ["ground", str(uuid.uuid4()), "--wikidata", "42"]
            )
        assert result.exit_code == 1
        repo.get.assert_not_awaited()

    def test_not_found_exits_one(self) -> None:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.add_external_id = AsyncMock()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository",
                return_value=repo,
            ),
        ):
            mock_db.session = _session_cm(mock_session)
            result = runner.invoke(
                entity_app, ["ground", str(uuid.uuid4()), "--wikidata", "Q42"]
            )
        assert result.exit_code == 1
        repo.add_external_id.assert_not_awaited()

    def test_resolve_by_name_requires_type(self) -> None:
        repo = MagicMock()
        repo.find_by_normalized_and_type = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository",
                return_value=repo,
            ),
        ):
            mock_db.session = _session_cm(AsyncMock())
            result = runner.invoke(
                entity_app, ["ground", "Some Event", "--wikidata", "Q42"]
            )
        assert result.exit_code == 1
        repo.find_by_normalized_and_type.assert_not_awaited()
