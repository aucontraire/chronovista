"""Unit tests for `chronovista entities backfill-wikidata-properties` (Feature 079, US2 / T014).

Mocked, no real database — covers the command's own wiring, which the real-DB integration seam
test (T013, ``tests/integration/api/test_entity_wikidata_backfill_capture.py``) deliberately does
not exercise:

(a) Dry run performs an explicit ``session.rollback()`` and never writes
    (``NamedEntityRepository.replace_properties`` is never called) — ``db_manager.get_session``
    auto-commits on scope exit, so a dry run that merely skipped ``commit()`` would still persist.
(b) ``--apply`` writes the pre-change backup JSON file before any write, containing exactly the
    id + prior ``properties`` of every entity in scope.

The command calls ``asyncio.run()`` internally, so — like the other entity CLI tests
(``tests/integration/cli/test_entity_commands.py``, ``test_entity_recount_command.py``) —
``db_manager``, ``NamedEntityRepository``, and ``WikidataClient`` are all mocked; ``CliRunner``
stays synchronous so no nested event loop is created. Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app

runner = CliRunner()

_FRESH_BAG: dict[str, Any] = {
    "image": {
        "values": ["Placeholder_Portrait.jpg"],
        "qids": [],
        "source": "wikidata",
        "set_at": "2026-01-01T00:00:00+00:00",
    }
}


def _make_get_session(mock_session: AsyncMock) -> Any:
    """Async generator factory matching ``db_manager.get_session(echo=False)``."""

    async def _gen(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    return _gen()


def _make_grounded_entity(
    *, entity_id: uuid.UUID | None = None, properties: dict[str, Any] | None = None
) -> MagicMock:
    """A MagicMock that looks like a Wikidata-grounded NamedEntity ORM row."""
    entity = MagicMock()
    entity.id = entity_id or uuid.uuid4()
    entity.canonical_name = f"Placeholder Entity {uuid.uuid4().hex[:6]}"
    entity.external_ids = {
        "wikidata": {"id": "Q000111", "verified": True, "status": "verified"}
    }
    entity.properties = properties if properties is not None else {}
    return entity


class TestBackfillWikidataPropertiesDryRun:
    def test_dry_run_rolls_back_and_never_writes(self) -> None:
        """Dry run (no ``--apply``) must roll back and must never call ``replace_properties``."""
        fake_entity = _make_grounded_entity()
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikidataClient") as MockClient,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_wikidata_grounded = AsyncMock(return_value=[fake_entity])
            MockRepo.return_value = repo
            client = AsyncMock()
            client.fetch_properties = AsyncMock(return_value=dict(_FRESH_BAG))
            MockClient.return_value = client

            result = runner.invoke(entity_app, ["backfill-wikidata-properties"])

        assert result.exit_code == 0, result.output
        assert mock_session.rollback.await_count == 1
        assert mock_session.commit.await_count == 0
        repo.replace_properties.assert_not_called()
        assert "dry run" in result.output.lower()

    def test_dry_run_with_nothing_grounded_still_rolls_back(self) -> None:
        """No grounded entities at all is also a no-write path — still rolls back."""
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikidataClient"),
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_wikidata_grounded = AsyncMock(return_value=[])
            MockRepo.return_value = repo

            result = runner.invoke(entity_app, ["backfill-wikidata-properties"])

        assert result.exit_code == 0, result.output
        assert mock_session.rollback.await_count == 1
        assert mock_session.commit.await_count == 0
        repo.replace_properties.assert_not_called()


class TestBackfillWikidataPropertiesApply:
    def test_apply_writes_backup_file_before_writing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--apply`` writes a pre-change backup (id + prior properties) for every entity in scope."""
        monkeypatch.chdir(tmp_path)
        entity_id = uuid.uuid4()
        prior_properties = {
            "occupation": {
                "values": ["Stale Placeholder Occupation"],
                "qids": [],
                "source": "wikidata",
                "set_at": "2020-01-01T00:00:00+00:00",
            }
        }
        fake_entity = _make_grounded_entity(
            entity_id=entity_id, properties=prior_properties
        )
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikidataClient") as MockClient,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_wikidata_grounded = AsyncMock(return_value=[fake_entity])
            repo.replace_properties = AsyncMock(return_value=1)
            MockRepo.return_value = repo
            client = AsyncMock()
            client.fetch_properties = AsyncMock(return_value=dict(_FRESH_BAG))
            MockClient.return_value = client

            result = runner.invoke(
                entity_app,
                ["backfill-wikidata-properties", "--apply", "--allow-dev"],
                input="y\n",
            )

        assert result.exit_code == 0, result.output
        backup_files = list((tmp_path / "backups").glob("enrichment_backfill_*.json"))
        assert len(backup_files) == 1, result.output
        backup_data = json.loads(backup_files[0].read_text())
        # The backup is captured BEFORE the write — exactly the prior properties, not the merged
        # bag — so a botched apply can be reverted to what was actually there beforehand.
        assert backup_data == [{"id": str(entity_id), "properties": prior_properties}]

        repo.replace_properties.assert_awaited_once()
        _, kwargs = repo.replace_properties.await_args
        assert (
            kwargs["properties"] != prior_properties
        )  # the merge actually changed something
        assert mock_session.commit.await_count == 1
        assert mock_session.rollback.await_count == 0

    def test_apply_without_allow_dev_on_dev_dsn_is_refused(self) -> None:
        """FR-012 guard: --apply against a dev DSN without --allow-dev refuses and never writes."""
        fake_entity = _make_grounded_entity()
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.settings") as mock_settings,
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikidataClient"),
        ):
            mock_settings.effective_database_url = (
                "postgresql+asyncpg://u:p@localhost:5434/chronovista_dev"
            )
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_wikidata_grounded = AsyncMock(return_value=[fake_entity])
            MockRepo.return_value = repo

            result = runner.invoke(
                entity_app, ["backfill-wikidata-properties", "--apply"]
            )

        assert result.exit_code != 0
        assert "dev database" in result.output.lower()
        repo.replace_properties.assert_not_called()
        assert mock_session.commit.await_count == 0

    def test_apply_confirm_declined_aborts_without_writing(self) -> None:
        """FR-016 guard: declining the confirmation aborts before any write."""
        fake_entity = _make_grounded_entity()
        mock_session = AsyncMock()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikidataClient"),
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_wikidata_grounded = AsyncMock(return_value=[fake_entity])
            MockRepo.return_value = repo

            # --allow-dev clears the dev guard; the confirmation is then declined ("n").
            result = runner.invoke(
                entity_app,
                ["backfill-wikidata-properties", "--apply", "--allow-dev"],
                input="n\n",
            )

        assert result.exit_code != 0
        repo.replace_properties.assert_not_called()
        assert mock_session.commit.await_count == 0
