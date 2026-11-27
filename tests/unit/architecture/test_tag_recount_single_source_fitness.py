"""Single-source fitness guard for the tag-counter rule (register G3).

A canonical tag's ``alias_count`` is its number of aliases, and its ``video_count`` is
the distinct videos whose tag is one of its aliases' raw forms. The rule is built once,
by ``tag_alias_count_query`` and ``tag_video_count_query`` in
``repositories/canonical_tag_repository.py``, and used by the operator recount
(``TagBackfillService.run_recount``) and the invariant audit's G3 check, so the check
and the repair cannot disagree.

Exact counts (Constitution: Single-Source Operations and Fitness Guards): a new caller,
or a removed one, changes a number here and must be a reviewed edit. Four older writers
still count inline (``_recalculate_counts``, ``_count_over_tag_ids``,
``_update_video_counts``, and ``run_recount``'s write). The structural-fix plan moves
them onto the builders, which raises these counts in the same reviewed edit.

Mutation-verified (2026-11-27): a second ``tag_alias_count_query()`` call in
``tag_backfill.py`` turns ``test_the_alias_count_builder_has_exactly_its_callers`` red.
"""

from __future__ import annotations

from pathlib import Path

import chronovista

_SRC = Path(chronovista.__file__).parent


def _calls(needle: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _SRC.rglob("*.py"):
        if "docs" in path.relative_to(_SRC).parts:
            continue
        source = path.read_text(encoding="utf-8")
        n = source.count(needle) - source.count(f"def {needle}")
        if n:
            counts[path.relative_to(_SRC).as_posix()] = n
    return counts


def test_the_alias_count_builder_has_exactly_its_callers() -> None:
    assert _calls("tag_alias_count_query()") == {
        "repositories/canonical_tag_repository.py": 1,
        "services/tag_backfill.py": 1,
    }


def test_the_video_count_builder_has_exactly_its_callers() -> None:
    assert _calls("tag_video_count_query()") == {
        "repositories/canonical_tag_repository.py": 1,
        "services/tag_backfill.py": 1,
    }
