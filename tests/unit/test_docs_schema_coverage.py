"""Guard: schema documentation must cover every table.

`docs/architecture/data-model.md` previously drifted badly from the shipped
schema — it documented a table that was never created, omitted six that were,
and described columns that never existed. The per-table reference is now
generated from the SQLAlchemy models so it cannot drift, but two hand-maintained
things still can:

1. the ``GROUPS`` map in ``scripts/gen_schema_ref.py`` (a table missing from it
   falls into an "Other" bucket rather than its proper section), and
2. the "Table Groups" overview table in ``data-model.md``.

Both are checked here against ``Base.metadata``, so adding a table without
documenting it fails the build.

``GROUPS`` is read with ``ast`` rather than imported, because the generator calls
``main()`` at module scope (the interface the mkdocs ``gen-files`` plugin
expects) and importing it would try to write files.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from chronovista.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "gen_schema_ref.py"
DATA_MODEL_DOC = REPO_ROOT / "docs" / "architecture" / "data-model.md"
SCHEMA_DOC = REPO_ROOT / "docs" / "reference" / "schema.md"


def _grouped_tables() -> set[str]:
    """Table names listed in the generator's GROUPS constant."""
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        if not any(isinstance(t, ast.Name) and t.id == "GROUPS" for t in targets):
            continue
        assert node.value is not None
        groups = ast.literal_eval(node.value)
        return {table for _title, _blurb, tables in groups for table in tables}
    raise AssertionError("GROUPS not found in scripts/gen_schema_ref.py")


def test_every_table_is_assigned_to_a_group() -> None:
    missing = sorted(set(Base.metadata.tables) - _grouped_tables())
    assert not missing, (
        f"tables missing from GROUPS in scripts/gen_schema_ref.py: {missing}. "
        "They would render under a generic 'Other' heading."
    )


def test_groups_reference_only_real_tables() -> None:
    phantom = sorted(_grouped_tables() - set(Base.metadata.tables))
    assert not phantom, (
        f"GROUPS references tables that do not exist: {phantom}. "
        "This is how the old hand-written docs came to describe a "
        "'user_subscriptions' table that was never created."
    )


def _rendered_schema() -> str:
    """The page the generator would produce from the current models.

    Imported rather than executed: ``main()`` runs only under ``__main__`` or
    mkdocs-gen-files' ``<run_path>``, so a plain import writes nothing.
    """
    spec = importlib.util.spec_from_file_location("_gen_schema_ref", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered: str = module.render_schema()
    return rendered


def test_schema_reference_is_not_stale() -> None:
    """The committed page must match what the generator produces.

    ``docs/reference/schema.md`` is tracked *and* regenerated at build time by
    mkdocs-gen-files, which writes into the build tree rather than over the
    source file. The published site is therefore always current while the
    committed copy — the one people read on GitHub — silently rots.

    It had: two tables short (the ADR-011 provenance pair, undocumented since
    they shipped), two columns missing, and no index or constraint sections at
    all, under a header stating "this page cannot drift". The claim was true of
    the built page and false of the committed one. This test is what makes it
    true of both.
    """
    committed = SCHEMA_DOC.read_text(encoding="utf-8")
    assert committed == _rendered_schema(), (
        f"{SCHEMA_DOC.relative_to(REPO_ROOT)} is out of date with the models. "
        "Regenerate it — the build shadows this file, so a stale copy fails "
        "silently everywhere except GitHub."
    )


def test_data_model_doc_mentions_every_table() -> None:
    doc = DATA_MODEL_DOC.read_text(encoding="utf-8")
    undocumented = sorted(
        name for name in Base.metadata.tables if f"`{name}`" not in doc
    )
    assert not undocumented, (
        f"tables absent from {DATA_MODEL_DOC.name}: {undocumented}. "
        "Add them to the Table Groups overview."
    )
