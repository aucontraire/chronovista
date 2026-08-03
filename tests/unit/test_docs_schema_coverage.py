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
from pathlib import Path

from chronovista.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "gen_schema_ref.py"
DATA_MODEL_DOC = REPO_ROOT / "docs" / "architecture" / "data-model.md"


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


def test_data_model_doc_mentions_every_table() -> None:
    doc = DATA_MODEL_DOC.read_text(encoding="utf-8")
    undocumented = sorted(
        name for name in Base.metadata.tables if f"`{name}`" not in doc
    )
    assert not undocumented, (
        f"tables absent from {DATA_MODEL_DOC.name}: {undocumented}. "
        "Add them to the Table Groups overview."
    )
