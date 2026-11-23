"""Feature 117 migration (``c6a2e8d4f193``): upgrade shape, populated downgrade, round trip.

Harness choice: the shared integration database is built by ``Base.metadata.create_all``
and dropped after every test, so it carries no ``alembic_version`` and cannot host a real
``alembic upgrade``/``downgrade``. These tests therefore create a throwaway database on
the same Postgres server (never the production port), run the real Alembic CLI against
it up to the parent revision, and drop it afterwards. Every test returns the scratch
database to head in a ``finally`` block.

Name-free placeholders only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PARENT_REVISION = "b4e8a1c7d305"
_REVISION = "c6a2e8d4f193"
_PROD_PORT = 5435

_TABLES = (
    "proximity_scope_states",
    "proximity_dirty_scopes",
    "proximity_generation_runs",
    "entity_pair_proximity_rollup",
)


def _server_url() -> Any:
    raw = os.getenv(
        "DATABASE_INTEGRATION_URL",
        os.getenv(
            "CHRONOVISTA_INTEGRATION_DB_URL",
            "postgresql+asyncpg://dev_user:dev_password@localhost:5434/"
            "chronovista_integration_test",
        ),
    )
    url = make_url(raw).set(drivername="postgresql")
    assert url.port != _PROD_PORT, "refusing to run migration tests on the prod port"
    return url


@pytest.fixture(scope="module")
def scratch_url() -> Iterator[str]:
    """Create a scratch database migrated to the parent revision; drop it at the end."""
    server = _server_url()
    name = f"chronovista_mig117_{uuid.uuid4().hex[:10]}"
    admin = create_engine(server.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = server.set(database=name)
    rendered = url.render_as_string(hide_password=False)
    try:
        _alembic(rendered, "upgrade", _PARENT_REVISION)
        yield rendered
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic(url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


@pytest.fixture
def engine(scratch_url: str) -> Iterator[Engine]:
    """Engine on the scratch DB; guarantees the DB is back at head after the test."""
    eng = create_engine(scratch_url)
    try:
        yield eng
    finally:
        eng.dispose()
        _alembic(scratch_url, "upgrade", "head")


def _current(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        )


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return {r[0] for r in rows}


def _shape(engine: Engine) -> dict[str, Any]:
    """Columns, constraints and indexes of every proximity table that exists."""
    shape: dict[str, Any] = {}
    present = [t for t in _TABLES if t in _tables(engine)]
    with engine.connect() as conn:
        for table in present:
            cols = conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable, column_default, "
                    "character_maximum_length FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :t "
                    "ORDER BY column_name"
                ),
                {"t": table},
            ).all()
            cons = conn.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:t AS regclass) ORDER BY conname"
                ),
                {"t": table},
            ).all()
            idx = conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = :t ORDER BY indexname"
                ),
                {"t": table},
            ).all()
            shape[table] = {
                "columns": [tuple(r) for r in cols],
                "constraints": [tuple(r) for r in cons],
                "indexes": [tuple(r) for r in idx],
            }
    return shape


def _constraint_names(engine: Engine, table: str) -> set[str]:
    return {name for name, _ in _shape(engine)[table]["constraints"]}


def _seed_parents(engine: Engine) -> dict[str, Any]:
    """Seed FK parents plus one proximity instance row; returns the ids used."""
    ent_a, ent_b = sorted([uuid.uuid4(), uuid.uuid4()])
    video = "vid_117_a"
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE videos, named_entities, proximity_generation_runs CASCADE")
        )
        conn.execute(
            text(
                "INSERT INTO videos (video_id, title, upload_date, duration, "
                "made_for_kids, self_declared_made_for_kids) VALUES "
                "(:v, 'Placeholder video', now(), 60, false, false)"
            ),
            {"v": video},
        )
        for ent, label in ((ent_a, "EntA"), (ent_b, "EntB")):
            conn.execute(
                text(
                    "INSERT INTO named_entities (id, canonical_name, "
                    "canonical_name_normalized, entity_type) "
                    "VALUES (:i, :n, :nn, 'person')"
                ),
                {"i": ent, "n": label, "nn": label.lower()},
            )
        conn.execute(
            text(
                "INSERT INTO video_transcripts (video_id, language_code, "
                "transcript_text, transcript_type, download_reason, is_cc, "
                "is_auto_synced, track_kind) VALUES "
                "(:v, 'en', 'placeholder text', 'AUTO', 'USER_REQUEST', false, "
                "false, 'standard')"
            ),
            {"v": video},
        )
        seg_ids = [
            conn.execute(
                text(
                    "INSERT INTO transcript_segments (video_id, language_code, text, "
                    "start_time, duration, end_time, sequence_number) VALUES "
                    "(:v, 'en', 'segment', :s, 1.0, :e, :n) RETURNING id"
                ),
                {"v": video, "s": float(n), "e": float(n) + 1.0, "n": n},
            ).scalar_one()
            for n in (0, 1)
        ]
        conn.execute(
            text(
                "INSERT INTO entity_pair_proximity (id, entity_a_id, entity_b_id, "
                "video_id, language_code, segment_a_id, segment_b_id, gap_seconds) "
                "VALUES (:id, :a, :b, :v, 'en', :sa, :sb, 1.0)"
            ),
            {
                "id": uuid.uuid4(),
                "a": ent_a,
                "b": ent_b,
                "v": video,
                "sa": seg_ids[0],
                "sb": seg_ids[1],
            },
        )
    return {"video": video, "ent_a": ent_a, "ent_b": ent_b}


class TestUpgradeShape:
    def test_scope_state_table_and_checks(self, engine: Engine) -> None:
        _alembic(engine.url.render_as_string(hide_password=False), "upgrade", "head")
        assert _current(engine) == _REVISION
        tables = _tables(engine)
        assert "proximity_scope_states" in tables
        assert "proximity_dirty_scopes" not in tables
        assert "entity_pair_proximity_rollup" not in tables

        shape = _shape(engine)["proximity_scope_states"]
        columns = {c[0]: c for c in shape["columns"]}
        assert set(columns) == {
            "video_id",
            "language_code",
            "revision",
            "computed_revision",
            "computed_rule_version",
            "computed_at",
            "invalidated_at",
            "reason",
            "attempts",
            "failed_rule_version",
            "next_attempt_at",
            "last_error",
        }
        assert columns["revision"][1] == "bigint"
        assert columns["revision"][2] == "NO" and columns["revision"][3] == "1"
        assert columns["computed_revision"][1:3] == ("bigint", "YES")
        assert columns["computed_rule_version"][4] == 50
        assert columns["attempts"][1] == "integer"
        assert columns["attempts"][2] == "NO" and columns["attempts"][3] == "0"
        assert columns["last_error"][4] == 500
        assert columns["invalidated_at"][2] == "NO"
        for name in ("computed_at", "next_attempt_at"):
            assert columns[name][2] == "YES"

        names = _constraint_names(engine, "proximity_scope_states")
        assert {
            "proximity_scope_states_pkey",
            "proximity_scope_states_video_id_fkey",
            "chk_proximity_scope_state_revision_positive",
            "chk_proximity_scope_state_computed_le_revision",
            "chk_proximity_scope_state_computed_pair",
        } <= names
        assert not {n for n in names if n.startswith("proximity_dirty_scopes")}

    def test_scope_state_checks_enforced(self, engine: Engine) -> None:
        _alembic(engine.url.render_as_string(hide_password=False), "upgrade", "head")
        _seed_parents(engine)
        insert = (
            "INSERT INTO proximity_scope_states (video_id, language_code, revision, "
            "computed_revision, computed_rule_version) "
            "VALUES ('vid_117_a', :lang, :rev, :crev, :rule)"
        )
        bad_rows = (
            ("b1", 0, None, None),  # revision >= 1
            ("b2", 2, 3, "117.0"),  # computed_revision <= revision
            ("b3", 2, 1, None),  # computed pair: revision without rule
            ("b4", 2, None, "117.0"),  # computed pair: rule without revision
        )
        for lang, rev, crev, rule in bad_rows:
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(
                    text(insert), {"lang": lang, "rev": rev, "crev": crev, "rule": rule}
                )
        with engine.begin() as conn:
            conn.execute(
                text(insert), {"lang": "ok", "rev": 2, "crev": 2, "rule": "117.0"}
            )

    def test_run_status_check_accepts_new_statuses(self, engine: Engine) -> None:
        _alembic(engine.url.render_as_string(hide_password=False), "upgrade", "head")
        insert = (
            "INSERT INTO proximity_generation_runs (id, status, generator_version) "
            "VALUES (:id, :s, 'v-test')"
        )
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE proximity_generation_runs"))
            for status in ("incomplete", "abandoned", "completed", "failed"):
                conn.execute(text(insert), {"id": uuid.uuid4(), "s": status})
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(insert), {"id": uuid.uuid4(), "s": "bogus"})


class TestPopulatedDowngrade:
    def test_downgrade_semantics(self, engine: Engine) -> None:
        url = engine.url.render_as_string(hide_password=False)
        _alembic(url, "upgrade", "head")
        seeded = _seed_parents(engine)
        with engine.begin() as conn:
            for status in ("incomplete", "abandoned", "completed"):
                conn.execute(
                    text(
                        "INSERT INTO proximity_generation_runs "
                        "(id, status, generator_version) VALUES (:id, :s, 'v-test')"
                    ),
                    {"id": uuid.uuid4(), "s": status},
                )
            conn.execute(
                text(
                    "INSERT INTO proximity_scope_states (video_id, language_code, "
                    "revision, computed_revision, computed_rule_version) VALUES "
                    "(:v, 'cur', 3, 3, '117.0'), (:v, 'old', 3, 2, '117.0'), "
                    # current under ANOTHER rule version: must survive (rule check)
                    "(:v, 'oth', 3, 3, '116.9'), "
                    # never computed: must survive (null-safe delete)
                    "(:v, 'nev', 1, NULL, NULL)"
                ),
                {"v": seeded["video"]},
            )
        proximity_before = _proximity_rows(engine)
        assert len(proximity_before) == 1

        _alembic(url, "downgrade", _PARENT_REVISION)
        assert _current(engine) == _PARENT_REVISION

        tables = _tables(engine)
        assert "proximity_dirty_scopes" in tables
        assert "proximity_scope_states" not in tables
        assert "entity_pair_proximity_rollup" in tables

        with engine.connect() as conn:
            statuses = sorted(
                r[0]
                for r in conn.execute(
                    text("SELECT status FROM proximity_generation_runs")
                )
            )
            assert statuses == ["completed", "failed", "failed"]
            scopes = conn.execute(
                text("SELECT language_code, marked_at FROM proximity_dirty_scopes")
            ).all()
            assert sorted(s[0] for s in scopes) == ["nev", "old", "oth"]
            assert all(s[1] is not None for s in scopes)
            rollup = conn.execute(
                text("SELECT count(*) FROM entity_pair_proximity_rollup")
            ).scalar_one()
            assert rollup == 0
        assert _proximity_rows(engine) == proximity_before

        # Legacy CHECK is back: the widened statuses are rejected again.
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO proximity_generation_runs (id, status, "
                    "generator_version) VALUES (:id, 'abandoned', 'v-test')"
                ),
                {"id": uuid.uuid4()},
            )
        assert {
            "proximity_dirty_scopes_pkey",
            "proximity_dirty_scopes_video_id_fkey",
        } <= {n for n, _ in _legacy_constraints(engine)}

        # Re-upgrading the populated database keeps the surviving stale scope.
        _alembic(url, "upgrade", "head")
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT language_code, revision, computed_revision "
                    "FROM proximity_scope_states ORDER BY language_code"
                )
            ).all()
        assert [tuple(r) for r in row] == [
            ("nev", 1, None),
            ("old", 1, None),
            ("oth", 1, None),
        ]
        assert _proximity_rows(engine) == proximity_before


def _proximity_rows(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, entity_a_id, entity_b_id, video_id, segment_a_id, "
                "segment_b_id, gap_seconds FROM entity_pair_proximity ORDER BY id"
            )
        )
        return [tuple(r) for r in rows]


def _legacy_constraints(engine: Engine) -> list[tuple[str, str]]:
    return list(_shape(engine)["proximity_dirty_scopes"]["constraints"])


class TestRoundTrip:
    def test_upgrade_downgrade_upgrade_shape_is_stable(self, engine: Engine) -> None:
        url = engine.url.render_as_string(hide_password=False)
        _alembic(url, "upgrade", "head")
        first = _shape(engine)

        _alembic(url, "downgrade", _PARENT_REVISION)
        legacy_before = _shape(engine)
        assert "proximity_scope_states" not in legacy_before

        _alembic(url, "upgrade", "head")
        assert _current(engine) == _REVISION
        assert _shape(engine) == first

        # Downgrade is also stable: a second cycle lands on the identical legacy shape.
        _alembic(url, "downgrade", _PARENT_REVISION)
        assert _shape(engine) == legacy_before
        _alembic(url, "upgrade", "head")
