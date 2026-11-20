"""Fitness guard: the connection-evidence query is language-scoped (FR-017, segment-side).

The (video, language) grain is the invariant that keeps the evidence panel from fabricating a
co-occurrence — ignoring language inflated one pair's co-mention count 478 → 1,476 by pairing a
mention in one language's transcript with a mention in another's. The `EvidenceItem` model validator
proves the MENTION side at the serialization boundary (`tests/unit/models/`); THIS guard proves the
QUERY side — that `EntityMentionRepository.co_occurrence_evidence`:
  (a) language-scopes the mention→segment join, so a segment from another language can't attach, and
  (b) groups/pairs mentions by `(video, language)`, so an a-mention is only ever paired with a
      b-mention from the SAME language.

Both halves are required; neither substitutes for the other (research D7).

Mutation-verify (do before merge): delete the language-scope join clause, or drop `language_code`
from the grouping key → the matching test below goes red; restore it → green.
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "src" / "chronovista" / "repositories" / "entity_mention_repository.py"


def _evidence_method_source() -> str:
    """The body of ``co_occurrence_evidence`` (up to the next top-level method), whitespace-
    normalized so formatter line-wrapping (e.g. black splitting a long ``==``) can't hide a clause.
    """
    src = _SRC.read_text()
    start = src.index("async def co_occurrence_evidence(")
    end = src.index("\n    async def get_association_counts(", start)
    return " ".join(src[start:end].split())


def test_segment_join_is_language_scoped() -> None:
    body = _evidence_method_source()
    assert (
        "TranscriptSegmentDB.language_code == EntityMentionDB.language_code" in body
    ), (
        "co_occurrence_evidence must language-scope the mention→segment join (FR-017): a segment "
        "from another language must never attach to a mention."
    )


def test_pairing_is_grouped_by_video_and_language() -> None:
    body = _evidence_method_source()
    assert "(m.video_id, m.language_code)" in body, (
        "co_occurrence_evidence must group mentions by (video, language) so an a-mention is only "
        "ever paired with a b-mention from the SAME language (FR-017)."
    )
