"""Fitness guard: the evidence panel's mention query is language-scoped (FR-017, segment-side).

The (video, language) grain is the invariant that keeps the evidence panel from fabricating a
co-occurrence — ignoring language inflated one pair's co-mention count 478 → 1,476 by pairing a
mention in one language's transcript with a mention in another's. It has two halves:

  (a) the mention→segment joins are language-scoped, so a segment from another language can't
      attach to a mention. Every reader of mentions behind the panel goes through
      ``EntityMentionRepository._pair_qualifying_mentions``, which joins the mention's START and
      END segments; THIS guard pins both joins.
  (b) mentions are only ever paired within one language. The panel's pairs are proximity records,
      paired by ``language_scope_predicate`` in ``entity_pair_proximity_repository``; that half is
      held by ``tests/integration/test_proximity_language_scoping_guard.py``.

Mutation-verify: delete either language clause from ``_pair_qualifying_mentions`` → the matching
test below goes red; restore it → green.
"""

from __future__ import annotations

import inspect

from chronovista.repositories.entity_mention_repository import EntityMentionRepository


def _qualifying_mentions_source() -> str:
    """The helper's source, whitespace-normalized so formatter line-wrapping (e.g. black
    splitting a long ``==``) can't hide a clause."""
    return " ".join(
        inspect.getsource(EntityMentionRepository._pair_qualifying_mentions).split()
    )


def test_start_segment_join_is_language_scoped() -> None:
    assert "start.language_code == EntityMentionDB.language_code" in (
        _qualifying_mentions_source()
    ), (
        "_pair_qualifying_mentions must language-scope the mention→start-segment join "
        "(FR-017): a segment from another language must never attach to a mention."
    )


def test_end_segment_join_is_language_scoped() -> None:
    assert "end.language_code == EntityMentionDB.language_code" in (
        _qualifying_mentions_source()
    ), (
        "_pair_qualifying_mentions must language-scope the mention→end-segment join "
        "(FR-017): a cross-segment mention must never end in another language's segment."
    )
