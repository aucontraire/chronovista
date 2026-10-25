"""Unit tests for the ``entities backfill-wikipedia-images`` command wiring (Feature 093, T009).

The command's orchestration — dry-run rollback (``get_session`` auto-commits on scope exit, so a
dry run MUST roll back explicitly), the pre-change backup, the dev-DSN refusal, per-entity commit on
apply, the ``source:"wikipedia"`` write ONLY on a STORED outcome, and the per-outcome counting — is
tested here with ``db_manager``, ``NamedEntityRepository`` and ``WikipediaImageFallback`` all mocked
and a synchronous ``CliRunner`` (so no nested event loop). The real write seam (repo -> UPDATE ->
serving) and the gate itself are covered by the integration test and the gate unit test. Neutral
placeholders only (Constitution VI).
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
from chronovista.models.wikipedia_image import FallbackOutcome, FallbackResult

runner = CliRunner()


def _make_get_session(mock_session: AsyncMock) -> Any:
    async def _gen(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    return _gen()


def _candidate(
    *, entity_id: uuid.UUID | None = None, properties: dict[str, Any] | None = None
) -> MagicMock:
    """A MagicMock that looks like a grounded, image-less NamedEntity ORM row."""
    entity = MagicMock()
    entity.id = entity_id or uuid.uuid4()
    entity.canonical_name = f"Placeholder Entity {uuid.uuid4().hex[:6]}"
    entity.external_ids = {"wikidata": {"id": "Q000111"}}
    entity.properties = properties if properties is not None else {}
    return entity


def _stored(
    entity_id: uuid.UUID, filename: str = "Placeholder_Portrait.jpg"
) -> FallbackResult:
    return FallbackResult(
        entity_id=entity_id, outcome=FallbackOutcome.STORED, filename=filename
    )


def _declined(entity_id: uuid.UUID) -> FallbackResult:
    return FallbackResult(
        entity_id=entity_id, outcome=FallbackOutcome.DECLINED_NON_FREE
    )


class TestDryRun:
    def test_dry_run_rolls_back_and_never_writes_even_on_stored(self) -> None:
        ent = _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(return_value=_stored(ent.id))
            MockFallback.return_value = fb

            result = runner.invoke(entity_app, ["backfill-wikipedia-images"])

        assert result.exit_code == 0, result.output
        assert mock_session.rollback.await_count == 1
        assert mock_session.commit.await_count == 0
        repo.replace_properties.assert_not_called()
        assert "dry run" in result.output.lower()

    def test_nothing_to_backfill_still_rolls_back(self) -> None:
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikipediaImageFallback"),
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[])
            MockRepo.return_value = repo

            result = runner.invoke(entity_app, ["backfill-wikipedia-images"])

        assert result.exit_code == 0, result.output
        assert mock_session.rollback.await_count == 1
        repo.replace_properties.assert_not_called()

    def test_entity_type_and_limit_are_passed_through(self) -> None:
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikipediaImageFallback"),
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[])
            MockRepo.return_value = repo

            result = runner.invoke(
                entity_app,
                [
                    "backfill-wikipedia-images",
                    "--entity-type",
                    "person",
                    "--limit",
                    "5",
                ],
            )

        assert result.exit_code == 0, result.output
        _, kwargs = repo.list_grounded_without_image.await_args
        assert kwargs == {"entity_type": "person", "limit": 5}


class TestApply:
    def test_apply_writes_wikipedia_block_and_backup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        entity_id = uuid.uuid4()
        ent = _candidate(entity_id=entity_id, properties={})
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            repo.replace_properties = AsyncMock(return_value=1)
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(
                return_value=_stored(entity_id, "Free_Commons_File.jpg")
            )
            MockFallback.return_value = fb

            result = runner.invoke(
                entity_app,
                ["backfill-wikipedia-images", "--apply", "--allow-dev"],
                input="y\n",
            )

        assert result.exit_code == 0, result.output
        backup_files = list(
            (tmp_path / "backups").glob("wikipedia_image_backfill_*.json")
        )
        assert len(backup_files) == 1, result.output
        backup_data = json.loads(backup_files[0].read_text())
        assert backup_data == [{"id": str(entity_id), "properties": {}}]

        repo.replace_properties.assert_awaited_once()
        _, kwargs = repo.replace_properties.await_args
        block = kwargs["properties"]["image"]
        assert block["source"] == "wikipedia"
        assert block["values"] == ["Free_Commons_File.jpg"]
        assert mock_session.commit.await_count == 1
        assert mock_session.rollback.await_count == 0

    def test_declined_outcome_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ent = _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(return_value=_declined(ent.id))
            MockFallback.return_value = fb

            result = runner.invoke(
                entity_app,
                ["backfill-wikipedia-images", "--apply", "--allow-dev"],
                input="y\n",
            )

        assert result.exit_code == 0, result.output
        repo.replace_properties.assert_not_called()
        assert mock_session.commit.await_count == 0

    def test_dev_dsn_without_allow_dev_is_refused(self) -> None:
        ent = _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.settings") as mock_settings,
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikipediaImageFallback"),
        ):
            mock_settings.effective_database_url = (
                "postgresql+asyncpg://u:p@localhost:5434/chronovista_dev"
            )
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo

            result = runner.invoke(entity_app, ["backfill-wikipedia-images", "--apply"])

        assert result.exit_code != 0
        assert "dev database" in result.output.lower()
        repo.replace_properties.assert_not_called()

    def test_confirm_declined_aborts_without_writing(self) -> None:
        ent = _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikipediaImageFallback"),
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo

            result = runner.invoke(
                entity_app,
                ["backfill-wikipedia-images", "--apply", "--allow-dev"],
                input="n\n",
            )

        assert result.exit_code != 0
        repo.replace_properties.assert_not_called()

    def test_nondev_dsn_apply_still_requires_confirmation(self) -> None:
        # The dev-DSN refusal short-circuits only dev-without-allow-dev; a genuine PROD DSN must
        # still prompt for confirmation (declining it aborts before any write).
        ent = _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.settings") as mock_settings,
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch("chronovista.cli.entity_commands.WikipediaImageFallback"),
        ):
            mock_settings.effective_database_url = (
                "postgresql+asyncpg://u:p@prod-host:5435/chronovista"
            )
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo

            result = runner.invoke(
                entity_app, ["backfill-wikipedia-images", "--apply"], input="n\n"
            )

        # No dev-refusal (it is a prod DSN); it reaches the confirm prompt, which we decline.
        assert result.exit_code != 0
        assert "dev database" not in result.output.lower()
        repo.replace_properties.assert_not_called()

    def test_markup_in_entity_name_does_not_crash_the_output(self) -> None:
        # A canonical_name containing Rich markup ("[...]") must not crash the streamed output.
        ent = _candidate()
        ent.canonical_name = "Placeholder [bold]name[/bold] with markup"
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[ent])
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(return_value=_stored(ent.id))
            MockFallback.return_value = fb

            result = runner.invoke(
                entity_app, ["backfill-wikipedia-images", "--pause", "0"]
            )

        assert result.exit_code == 0, result.output


class TestOutcomeCounting:
    def test_summary_counts_each_outcome_distinctly(self) -> None:
        # A mixed batch: one stored, one non-free, one no-page — each counted in its own bucket.
        e1, e2, e3 = _candidate(), _candidate(), _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[e1, e2, e3])
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(
                side_effect=[
                    _stored(e1.id),
                    _declined(e2.id),
                    FallbackResult(entity_id=e3.id, outcome=FallbackOutcome.NO_PAGE),
                ]
            )
            MockFallback.return_value = fb

            result = runner.invoke(
                entity_app, ["backfill-wikipedia-images", "--pause", "0"]
            )

        assert result.exit_code == 0, result.output
        out = result.output
        assert "stored=1" in out
        assert "declined_non_free=1" in out
        assert "no_page=1" in out
        assert "total=3" in out

    def test_outcomes_stream_per_entity_not_only_in_summary(self) -> None:
        # The fix for the "silent until the end" hang: each entity's outcome is printed as it is
        # processed (above the progress bar), so the outcome token appears BOTH on its own
        # streamed line and in the final summary — i.e. more than once.
        e1, e2 = _candidate(), _candidate()
        mock_session = AsyncMock()
        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository") as MockRepo,
            patch(
                "chronovista.cli.entity_commands.WikipediaImageFallback"
            ) as MockFallback,
        ):
            mock_db.get_session.return_value = _make_get_session(mock_session)
            repo = AsyncMock()
            repo.list_grounded_without_image = AsyncMock(return_value=[e1, e2])
            MockRepo.return_value = repo
            fb = AsyncMock()
            fb.evaluate = AsyncMock(
                side_effect=[
                    _stored(e1.id, "Streamed_File.jpg"),
                    FallbackResult(entity_id=e2.id, outcome=FallbackOutcome.NO_PAGE),
                ]
            )
            MockFallback.return_value = fb

            result = runner.invoke(
                entity_app, ["backfill-wikipedia-images", "--pause", "0"]
            )

        assert result.exit_code == 0, result.output
        out = result.output
        # The stored filename only appears on the streamed per-entity line (never in the summary),
        # so its presence proves the line streamed.
        assert "Streamed_File.jpg" in out
        # "no_page" appears once streamed + once in the summary counter.
        assert out.count("no_page") >= 2
