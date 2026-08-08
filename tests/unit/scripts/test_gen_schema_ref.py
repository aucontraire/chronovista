"""
Unit tests for scripts/gen_schema_ref.py.

Regression coverage for non-deterministic output: ``Table.constraints`` is a
``set``, so iteration follows object hashes and varies between processes. Two
comprehensions consumed it unsorted, so unchanged models rendered a different
file on every run — a diff that reads as schema drift and is only reordering.

**Why this asserts ordering rather than rendering twice.** The obvious test —
call ``render_schema()`` twice and compare — passes even with the bug present.
Set iteration is stable *within* a process: the same set object, holding the
same objects, iterates the same way every time. The variation is between
processes, so a same-process comparison is vacuous. Verified: with the fix
reverted, two in-process renders are byte-identical.

**Why a synthetic table as well as the real schema.** The live schema has tables
with several CHECK constraints, so that half is exercised for real. It has no
table with two or more *multi-column* UNIQUE constraints, so an assertion
against the real schema could never fail for that branch. The synthetic table
supplies the input the schema does not.

No database is touched — rendering reads metadata only.
"""

from __future__ import annotations

import re

from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

from scripts.gen_schema_ref import _render_table, render_schema

# One "**Constraints:**" block, capturing its bullet list.
CONSTRAINT_BLOCK = re.compile(r"\*\*Constraints:\*\*\n\n((?:- .*\n)+)")

# The two bullet shapes put the constraint name in different places, so they
# need different patterns:
#     - CHECK `ck_name`: `expr`             -> name is the first backtick
#     - UNIQUE on `col_a`, `col_b` (`uq_name`)  -> name is the LAST, parenthesised
# A single "first backticked token" pattern silently reads column names for
# UNIQUE, yielding a list that is trivially sorted and can never fail.
NAME_PATTERNS = {
    "CHECK": re.compile(r"^- CHECK `([^`]+)`:", re.M),
    "UNIQUE": re.compile(r"^- UNIQUE on .*\(`([^`]+)`\)\s*$", re.M),
}


def _named_constraints(text: str, kind: str) -> list[str]:
    """Constraint names of one kind, in the order they were rendered."""
    return NAME_PATTERNS[kind].findall(text)


class TestRealSchemaOrdering:
    """The rendered reference must be stable across runs."""

    def test_check_constraints_are_sorted_within_each_table(self) -> None:
        """The regression: CHECK constraints came out in set-iteration order."""
        blocks = CONSTRAINT_BLOCK.findall(render_schema())
        assert blocks, "no constraint blocks rendered — the parser is wrong"

        unsorted_blocks = [
            names
            for block in blocks
            if (names := _named_constraints(block, "CHECK")) != sorted(names)
        ]
        assert not unsorted_blocks, f"CHECK constraints not sorted: {unsorted_blocks}"

    def test_a_table_actually_has_multiple_checks(self) -> None:
        """Guards the test above from passing vacuously.

        A table with 0 or 1 CHECK constraint is sorted whatever the code does.
        If the schema ever lost every multi-constraint table, the ordering
        assertion would still pass while testing nothing.
        """
        blocks = CONSTRAINT_BLOCK.findall(render_schema())
        widest = max((len(_named_constraints(b, "CHECK")) for b in blocks), default=0)
        assert widest >= 2, (
            "no table renders 2+ CHECK constraints, so the ordering test "
            f"cannot fail (widest block: {widest})"
        )


class TestSyntheticTableOrdering:
    """Both branches of the sort, on input the live schema does not provide."""

    @staticmethod
    def _table() -> Table:
        """A table whose constraint names are deliberately not in insertion order.

        Six of each: with the sort removed, the chance that set iteration
        happens to emit them alphabetically is 1/720 per kind, so the test
        reliably catches a regression rather than catching it half the time.
        """
        columns = [Column(name, String) for name in "abcdef"]
        constraints: list[UniqueConstraint | CheckConstraint] = []
        for suffix in ("zulu", "yankee", "xray", "delta", "charlie", "alpha"):
            constraints.append(UniqueConstraint("a", "b", name=f"uq_{suffix}"))
            constraints.append(CheckConstraint("a IS NOT NULL", name=f"ck_{suffix}"))
        return Table(
            "synthetic",
            MetaData(),
            Column("id", Integer, primary_key=True),
            *columns,
            *constraints,
        )

    def test_multi_column_unique_constraints_are_sorted(self) -> None:
        rendered = "\n".join(_render_table(self._table(), None))
        names = _named_constraints(rendered, "UNIQUE")
        assert len(names) == 6, f"expected 6 UNIQUE constraints, got {names}"
        assert names == sorted(names), f"UNIQUE constraints not sorted: {names}"

    def test_check_constraints_are_sorted(self) -> None:
        rendered = "\n".join(_render_table(self._table(), None))
        names = _named_constraints(rendered, "CHECK")
        assert len(names) == 6, f"expected 6 CHECK constraints, got {names}"
        assert names == sorted(names), f"CHECK constraints not sorted: {names}"
