"""
Property-based tests for entity intersection qualification (Feature 062).

FR-003 and FR-004 state the invariant this feature is most exposed to:
``entity_mentions`` holds multiple rows per ``(entity_id, video_id)`` by design
-- across sources, and within a source per issue #106 -- so qualification must
depend only on WHICH distinct entities are present, never on how many rows each
one has.

Example-based tests check the multiplicities someone thought of. These check
arbitrary ones. The property is enforced in two places, and both are asserted
here: the requested ids are deduplicated before the bar is set, and the bar is
counted over ``DISTINCT entity_id`` rather than raw rows.
"""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st

from chronovista.models.enums import EvidenceScope
from chronovista.repositories.entity_mention_repository import EntityMentionRepository

_REPO = EntityMentionRepository()

# A pool of fixed ids so hypothesis can construct lists with real repetition;
# drawing fresh uuid4s would make duplicates vanishingly unlikely and the
# property would go untested while appearing to pass.
_POOL = [uuid.UUID(int=n) for n in range(1, 9)]


def _compiled(entity_ids: list[uuid.UUID], scope: EvidenceScope) -> str:
    subquery = _REPO.build_entity_qualification_subquery(entity_ids, scope)
    return str(
        subquery.element.compile(compile_kwargs={"literal_binds": True})
    ).replace("\n", " ")


@given(
    ids=st.lists(st.sampled_from(_POOL), min_size=1, max_size=20),
    scope=st.sampled_from(list(EvidenceScope)),
)
def test_bar_is_set_from_distinct_ids_only(
    ids: list[uuid.UUID], scope: EvidenceScope
) -> None:
    """The HAVING bar equals the number of DISTINCT requested entities.

    If the bar were set from ``len(ids)``, requesting the same entity twice
    would demand two distinct matches and the intersection would silently
    collapse to empty -- a wrong answer returned confidently.
    """
    sql = _compiled(ids, scope)
    assert f"= {len(set(ids))}" in sql


@given(ids=st.lists(st.sampled_from(_POOL), min_size=1, max_size=20))
def test_repetition_does_not_change_the_query(ids: list[uuid.UUID]) -> None:
    """A list and its deduplicated form produce identical SQL.

    This is the strongest statement of FR-003's requesting-side half: row
    multiplicity in the REQUEST cannot influence the result at all.
    """
    deduped = list(dict.fromkeys(ids))
    assert _compiled(ids, EvidenceScope.ANY) == _compiled(deduped, EvidenceScope.ANY)


@given(ids=st.lists(st.sampled_from(_POOL), min_size=1, max_size=20))
def test_qualification_counts_distinct_entities_not_rows(
    ids: list[uuid.UUID],
) -> None:
    """The stored-side half: the bar counts DISTINCT entity_id.

    Counting raw rows would let a single entity mentioned N times satisfy an
    N-entity intersection -- a video would qualify for entities it never
    mentions. Asserted against the compiled SQL because no fixture can
    enumerate every multiplicity a real corpus produces.
    """
    sql = _compiled(ids, EvidenceScope.ANY).lower()
    assert "count(distinct" in sql


@given(ids=st.lists(st.sampled_from(_POOL), min_size=1, max_size=20))
def test_transcript_scope_always_constrains_source(ids: list[uuid.UUID]) -> None:
    """Scope is expressed over mention SOURCE only, never detection method.

    FR-020d: the two are orthogonal, and every human-added mention is
    transcript-sourced. A scope that filtered on detection_method would discard
    the highest-trust evidence in the system.
    """
    sql = _compiled(ids, EvidenceScope.TRANSCRIPT).lower()
    assert "mention_source" in sql
    assert "detection_method" not in sql


@given(ids=st.lists(st.sampled_from(_POOL), min_size=1, max_size=20))
def test_qualification_never_joins_transcript_segments(
    ids: list[uuid.UUID],
) -> None:
    """Research R1: the timestamp join must stay off the qualification query.

    Joining ``transcript_segments`` before pagination returns byte-identical
    output at roughly eight times the cost, so no value-based assertion can
    detect the regression. This one can, because it inspects the shape.
    """
    sql = _compiled(ids, EvidenceScope.ANY).lower()
    assert "transcript_segments" not in sql


def test_cooccurrence_ordering_carries_the_id_tiebreak() -> None:
    """The appears-with ordering must be total, not merely count-descending.

    R5 makes the ``entity_id`` tiebreak contractual: without it, two partners
    with equal shared counts may swap between requests, so a bounded list looks
    unstable and a reveal-more page can repeat or skip a partner.

    Asserted against the COMPILED statement, because a row-based test cannot
    detect the tiebreak's removal -- Postgres returns small groups in
    ascending-id order whether or not the ORDER BY asks for it, so the
    integration test passes either way. Same class of problem as R1's two query
    shapes returning identical output: only inspecting the query separates them.
    """
    stmt = _REPO.build_cooccurrence_query(uuid.UUID(int=1), 12, EvidenceScope.ANY)
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()

    order_clause = sql.split("order by", 1)[1]
    assert "desc" in order_clause, "partners must be ranked by shared count"
    assert "asc" in order_clause, (
        "ordering must carry the entity_id tiebreak (R5); count DESC alone is "
        "not a total order and leaves tied partners free to swap"
    )


def test_cooccurrence_restricts_to_the_available_video_population() -> None:
    """FR-024b holds only if the panel counts the same videos the list shows.

    The videos list excludes unavailable videos by default. A co-occurrence
    count over every shared video would be inflated, and the user would be
    shown one number and land on another.
    """
    stmt = _REPO.build_cooccurrence_query(uuid.UUID(int=1), 12, EvidenceScope.ANY)
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "videos" in sql and "availability_status" in sql
