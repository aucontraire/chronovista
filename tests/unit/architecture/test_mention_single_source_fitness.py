"""Single-source fitness guards for keeping stored mentions on their words (#426).

Two rules each had several hand-rolled copies, and the copies disagreed:

* **"Does a stored mention still read as its text?"** Four forms in about ten places
  (per-segment slice, per-half prefix/suffix, joined text, inline located slice). A
  split name whose halves no longer joined passed one form and failed another, so a
  writer could decline to record an occurrence that the repair then removed. The rule
  now lives in ``TranscriptTextIndex.mention_reads`` and nothing else compares a
  stored slice to ``mention_text``.
* **"Where is this entity's name in this text?"** Corrections used a plain
  case-insensitive search while the scan folds diacritics, honours case-sensitive
  aliases and registered ASR forms, and arbitrates longest-match-wins. They now ask
  the scan, through ``EntityMentionScanService.detect_in_text``.

Exact counts (Constitution: Single-Source Operations and Fitness Guards): a new caller,
or a removed one, changes a number here and must be a reviewed edit. Files are read
from disk, so untracked new modules are counted too.

Mutation-verified (2026-11-24, counting rule 2026-11-25): adding a hand-rolled ``.casefold() ==
mention_text.casefold()`` comparison to the repair turns
``test_only_the_predicate_compares_a_slice_to_mention_text`` red; deleting the
``mention_reads`` call from ``TextEdit.rebase`` turns the call-site test red; adding a
second ``detect_in_text`` call to the batch writer turns the detection test red.
"""

from __future__ import annotations

from pathlib import Path

import chronovista

_SRC = Path(chronovista.__file__).parent


def _count(needle: str, *, exclude: str | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _SRC.rglob("*.py"):
        if "docs" in path.relative_to(_SRC).parts:
            continue
        source = path.read_text(encoding="utf-8")
        n = source.count(needle) - (source.count(exclude) if exclude else 0)
        if n:
            counts[path.relative_to(_SRC).as_posix()] = n
    return counts


# Every reader of stored offsets: the correction rebase (single segment, the old and
# new joined texts of a split name), the batch writer's occupied check, the scanner's
# full-rescan survivors and cross-segment recorded checks, TextEdit.rebase, and the
# repair's classification.
_EXPECTED_READS = {
    "services/batch_correction_service.py": 1,
    "services/entity_mention_scan_service.py": 2,
    "services/mention_offset_rebase.py": 1,
    "services/mention_repair_service.py": 1,
    "services/transcript_correction_service.py": 3,
}


def test_stored_mentions_are_read_through_the_one_predicate() -> None:
    assert _count(".mention_reads(") == _EXPECTED_READS, (
        "TranscriptTextIndex.mention_reads call sites changed. A new reader of stored "
        "mention offsets must use it (and be added here); a reader that stopped using "
        "it can disagree with the others about which rows are stale (#426)."
    )
    assert sum(_EXPECTED_READS.values()) == 8


def test_only_the_predicate_compares_a_slice_to_mention_text() -> None:
    """A hand-rolled "slice equals mention_text" check is the parallel mechanism
    #426 removed; only the predicate itself may make that comparison."""
    assert _count("mention_text.casefold()") == {"services/transcript_text_index.py": 1}


# Corrections locating a name: the batch writer's widening helper, the rebase's
# single-segment and split-name re-pointing, and the repair's relocation.
_EXPECTED_DETECTION_CALLS = {
    "services/batch_correction_service.py": 1,
    "services/mention_repair_service.py": 1,
    "services/transcript_correction_service.py": 2,
}


def test_corrections_find_names_by_the_scans_rule() -> None:
    assert (
        _count("detect_in_text(", exclude="def detect_in_text(")
        == _EXPECTED_DETECTION_CALLS
    ), (
        "detect_in_text call sites changed. Code that must find where an entity's "
        "name is in a text uses the scan's matching rule through it; a private "
        "matcher drifts from the scan (accents, case-sensitive aliases, ASR forms)."
    )


# What counts toward an entity's stored totals: the counter recompute,
# the span column the survivor rule ranks by, and the audit's snapshot. Before this rule had a home the
# recompute held the only copy inline, and the survivor rule ranked by length alone.
_EXPECTED_COUNTING_RULE_CALLS = {"repositories/entity_mention_repository.py": 3}


def test_what_counts_has_one_home() -> None:
    assert (
        _count(
            "_mention_counts_toward_totals(",
            exclude="def _mention_counts_toward_totals(",
        )
        == _EXPECTED_COUNTING_RULE_CALLS
    ), (
        "_mention_counts_toward_totals call sites changed. Code that decides whether "
        "a mention counts toward mention_count / video_count uses it; a private copy "
        "can keep an uncounted row over a counted one."
    )


def test_no_private_copy_of_the_counting_method_arm() -> None:
    """The stored-counter rule's method arm, written out by hand, is the copy its
    extraction removed from ``update_entity_counters``."""
    assert _count('detection_method == "asr_match"') == {
        "repositories/entity_mention_repository.py": 1
    }
