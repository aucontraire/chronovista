"""Generate the Database Schema reference page from the SQLAlchemy models.

Reads ``chronovista.db.models.Base.metadata`` — the same metadata Alembic
autogenerates migrations from — and writes ``reference/schema.md``: one section
per table with columns, types, nullability, defaults, keys, constraints, and
indexes. Executed at build time by the ``gen-files`` mkdocs plugin.

This page is generated rather than hand-written because the previous
hand-maintained schema documentation drifted badly from the shipped database:
it described columns that never existed, documented a table that was never
created, and omitted six tables that were. Generating from the models makes
that class of drift impossible.

Types are compiled with the PostgreSQL dialect so they read exactly as they do
in the database (``VARCHAR(50)``, ``TIMESTAMP WITH TIME ZONE``, ``JSONB``).
"""

from __future__ import annotations

from typing import Any

import mkdocs_gen_files
from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from chronovista.db.models import Base

# Table groupings, mirroring how the schema is actually organised. Any table not
# listed here still appears, under "Other" — so a new table can never be
# silently dropped from the docs just because this map wasn't updated.
GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "Core Content",
        "Channels, videos, and the reference data they hang off.",
        ["channels", "videos", "video_categories", "video_localizations"],
    ),
    (
        "Transcripts",
        "Transcript text, per-segment timing, and the append-only correction audit trail.",
        ["video_transcripts", "transcript_segments", "transcript_corrections"],
    ),
    (
        "User Data",
        "The local user's own engagement data, keyed by the canonical identity.",
        ["app_identities", "user_videos", "user_language_preferences"],
    ),
    (
        "Playlists",
        "Playlists and their membership, including Takeout-imported system playlists.",
        ["playlists", "playlist_memberships"],
    ),
    (
        "Topics",
        "YouTube's topic taxonomy and its associations to videos and channels.",
        ["topic_categories", "topic_aliases", "video_topics", "channel_topics"],
    ),
    (
        "Tags and Normalization",
        "Raw tags plus the canonical-tag layer that collapses spelling variants.",
        [
            "video_tags",
            "channel_keywords",
            "canonical_tags",
            "tag_aliases",
            "tag_operation_logs",
        ],
    ),
    (
        "Named Entities",
        "Curated entities, their aliases, and every place they are mentioned.",
        [
            "named_entities",
            "entity_aliases",
            "entity_mentions",
            "entity_operation_logs",
        ],
    ),
]


def _type_of(column: Any) -> str:
    """Render a column type as PostgreSQL sees it."""
    try:
        return str(column.type.compile(dialect=postgresql.dialect()))
    except Exception:  # pragma: no cover - exotic types fall back to repr
        return str(column.type)


def _default_of(column: Any) -> str:
    """Render the effective default, preferring the server-side one."""
    if column.server_default is not None:
        arg = getattr(column.server_default, "arg", None)
        text = str(getattr(arg, "text", arg) if arg is not None else "").strip()
        if text:
            return f"`{text}`"
    if column.default is not None and getattr(column.default, "is_scalar", False):
        return f"`{column.default.arg!r}`"
    return ""


def _notes_of(column: Any, table: Table) -> str:
    """Key membership and uniqueness, as short markers."""
    notes: list[str] = []
    if column.primary_key:
        notes.append("**PK**")
    for fk in sorted(column.foreign_keys, key=lambda f: str(f.target_fullname)):
        notes.append(f"FK → `{fk.target_fullname}`")
    if column.unique:
        notes.append("unique")
    else:
        for constraint in table.constraints:
            if (
                isinstance(constraint, UniqueConstraint)
                and len(constraint.columns) == 1
                and column.name in constraint.columns
            ):
                notes.append("unique")
                break
    return ", ".join(notes)


def _render_table(table: Table, doc: str | None) -> list[str]:
    lines: list[str] = [f"### `{table.name}`", ""]
    if doc:
        lines += [doc, ""]

    lines += [
        "| Column | Type | Null | Default | Notes |",
        "|--------|------|------|---------|-------|",
    ]
    for column in table.columns:
        lines.append(
            f"| `{column.name}` | {_type_of(column)} | "
            f"{'yes' if column.nullable else 'no'} | "
            f"{_default_of(column)} | {_notes_of(column, table)} |"
        )
    lines.append("")

    pk_cols = list(table.primary_key.columns)
    if len(pk_cols) > 1:
        joined = ", ".join(f"`{c.name}`" for c in pk_cols)
        lines += [f"**Composite primary key:** {joined}", ""]

    multi_unique = [
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and len(c.columns) > 1
    ]
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    if multi_unique or checks:
        lines.append("**Constraints:**")
        lines.append("")
        for constraint in multi_unique:
            cols = ", ".join(f"`{c.name}`" for c in constraint.columns)
            name = f" (`{constraint.name}`)" if constraint.name else ""
            lines.append(f"- UNIQUE on {cols}{name}")
        for constraint in checks:
            name = f"`{constraint.name}`" if constraint.name else "CHECK"
            lines.append(f"- CHECK {name}: `{constraint.sqltext}`")
        lines.append("")

    if table.indexes:
        lines.append("**Indexes:**")
        lines.append("")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            cols = ", ".join(f"`{c.name}`" for c in index.columns)
            kind = "UNIQUE INDEX" if index.unique else "INDEX"
            lines.append(f"- {kind} `{index.name}` on {cols}")
        lines.append("")

    return lines


def render_schema() -> str:
    """Render the whole schema reference as Markdown."""
    metadata = Base.metadata
    docs: dict[str, str | None] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table_name = getattr(cls, "__tablename__", None)
        if isinstance(table_name, str):
            raw = (cls.__doc__ or "").strip()
            docs[table_name] = raw.split("\n\n")[0].replace("\n", " ").strip() or None

    grouped: set[str] = {t for _, _, tables in GROUPS for t in tables}
    ungrouped = sorted(set(metadata.tables) - grouped)

    lines: list[str] = [
        "# Database Schema",
        "",
        "Every table in the PostgreSQL schema, generated from the SQLAlchemy models",
        "at build time — the same metadata Alembic autogenerates migrations from, so",
        "this page cannot drift from the shipped database.",
        "",
        f"**{len(metadata.tables)} tables.** For the reasoning behind the design, see",
        "[Data Model](../architecture/data-model.md).",
        "",
    ]

    sections: list[tuple[str, str, list[str]]] = list(GROUPS)
    if ungrouped:
        sections.append(
            ("Other", "Tables not yet assigned to a group above.", ungrouped)
        )

    for title, blurb, table_names in sections:
        present = [t for t in table_names if t in metadata.tables]
        if not present:
            continue
        lines += [f"## {title}", "", blurb, ""]
        for name in present:
            lines += _render_table(metadata.tables[name], docs.get(name))

    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    with mkdocs_gen_files.open("reference/schema.md", "w") as fd:
        fd.write(render_schema())
    mkdocs_gen_files.set_edit_path(
        "reference/schema.md", "src/chronovista/db/models.py"
    )


main()
