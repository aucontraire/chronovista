"""Unit tests for the novel-relationship generator's pure compute (Feature 107).

Exercises :func:`compute_candidates` on small synthetic inputs — no database — so
the measured contracts (three-arm novelty filter, lift, canonical order, no floor,
corroboration, eligibility) are verified in isolation.

IMPORTANT: every "should be excluded" test includes filler videos so the pair
clears ``lift >= 5`` on its own — otherwise the exclusion could be an artifact of
low lift rather than the novelty filter, and the test would pass vacuously.
"""

from __future__ import annotations

import uuid
from typing import Any

from chronovista.services import relationship_candidate_service as svc

# 30 filler single-entity videos push N up so a support-6 pair clears lift>=5:
# lift = 6 * (6 + 30) / (6 * 6) = 6.
_FILLER_VIDEOS = 30


def _entity(
    qid: str, **fields: list[str]
) -> tuple[uuid.UUID, dict[str, Any], dict[str, Any]]:
    """Build an (id, external_ids, properties) row; fields map name -> [qids]."""
    eid = uuid.uuid4()
    props: dict[str, Any] = {name: {"qids": qids} for name, qids in fields.items()}
    return eid, {"wikidata": {"id": qid}}, props


def _cooccur(
    ids: list[uuid.UUID], videos: int, start: int = 0
) -> list[tuple[uuid.UUID, str]]:
    """All ids co-occur in `videos` distinct videos (v{start}..)."""
    rows: list[tuple[uuid.UUID, str]] = []
    for v in range(start, start + videos):
        for eid in ids:
            rows.append((eid, f"v{v}"))
    return rows


def _with_filler(
    core_rows: list[tuple[uuid.UUID, str]],
) -> tuple[
    list[tuple[uuid.UUID, str]], tuple[uuid.UUID, dict[str, Any], dict[str, Any]]
]:
    """Append filler single-entity videos so the co-occurring pair clears lift>=5."""
    filler = _entity("QFILL")
    rows = core_rows + [(filler[0], f"f{v}") for v in range(_FILLER_VIDEOS)]
    return rows, filler


class TestNoveltyFilter:
    def test_novel_pair_with_no_tie_is_emitted(self) -> None:
        a = _entity("Q1")
        b = _entity("Q2")
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert len(candidates) == 1
        assert {candidates[0].entity_a_id, candidates[0].entity_b_id} == {a[0], b[0]}
        assert candidates[0].lift >= svc.LIFT_MIN

    def test_direct_edge_excludes_pair(self) -> None:
        a = _entity("Q1", founder=["Q2"])  # a.founder -> b's QID
        b = _entity("Q2")
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert candidates == []  # excluded by novelty, not by low lift

    def test_shared_co_membership_excludes_pair(self) -> None:
        a = _entity("Q1", member_of=["QORG"])
        b = _entity("Q2", member_of=["QORG"])
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert candidates == []

    def test_shared_headquarters_excludes_pair(self) -> None:
        # The attribute arm MUST include headquarters (R3).
        a = _entity("Q1", headquarters=["QCITY"])
        b = _entity("Q2", headquarters=["QCITY"])
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert candidates == []

    def test_shared_country_excludes_pair(self) -> None:
        a = _entity("Q1", country=["QC"])
        b = _entity("Q2", country=["QC"])
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert candidates == []


class TestThresholds:
    def test_support_below_5_excluded(self) -> None:
        a = _entity("Q1")
        b = _entity("Q2")
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 4))  # only 4 shared
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert candidates == []

    def test_lift_below_5_excluded(self) -> None:
        # Co-occur in all their videos with a tiny universe -> lift = 1 (no filler).
        a = _entity("Q1")
        b = _entity("Q2")
        rows = _cooccur([a[0], b[0]], 6)  # N = 6, A = B = 6 -> lift = 1
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b], run_id=uuid.uuid4()
        )
        assert candidates == []

    def test_canonical_order_and_no_duplicate(self) -> None:
        a = _entity("Q1")
        b = _entity("Q2")
        core = _cooccur([a[0], b[0]], 6) + _cooccur([a[0], b[0]], 1, start=100)
        rows, filler = _with_filler(core)
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert len(candidates) == 1
        assert candidates[0].entity_a_id < candidates[0].entity_b_id

    def test_lift_value_is_correct(self) -> None:
        a = _entity("Q1")
        b = _entity("Q2")
        filler = _entity("Q3")
        # a,b share 5 videos; filler fills to N=50 -> lift = 5*50/(5*5) = 10.
        rows = _cooccur([a[0], b[0]], 5) + [(filler[0], f"v{v}") for v in range(5, 50)]
        candidates, universe = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert universe == 50
        assert len(candidates) == 1
        assert candidates[0].shared_video_count == 5
        assert candidates[0].lift == 10.0


class TestCorroborationAndEligibility:
    def test_corroboration_counts_shared_non_filter_field(self) -> None:
        # A shared referent on a non-filter captured field (field_of_work) is NOT a
        # novelty disqualifier but IS a corroboration signal.
        a = _entity("Q1", field_of_work=["QFIELD"])
        b = _entity("Q2", field_of_work=["QFIELD"])
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert len(candidates) == 1
        assert candidates[0].kb_corroboration_count >= 1
        assert "field_of_work" in candidates[0].kb_corroboration_detail["fields"]

    def test_both_typed_eligible_flag(self) -> None:
        # a has a tie field (position_held), b has none -> not both eligible.
        a = _entity("Q1", position_held=["QPOS"])
        b = _entity("Q2")
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler], run_id=uuid.uuid4()
        )
        assert len(candidates) == 1
        assert candidates[0].both_typed_eligible is False

    def test_corroboration_excludes_hub_referent(self) -> None:
        # A shared HUB referent (same big country, >HUB_CAP members) must NOT count as
        # corroboration — it's the same hub the novelty filter rejects, so counting it
        # would be an unnormalized-signal leak into a user-facing badge.
        a = _entity("Q1", country=["QC"])
        b = _entity("Q2", country=["QC"])
        # 19 more entities also share QC -> 21 members -> a hub above HUB_CAP (20).
        hub = [_entity(f"QH{i}", country=["QC"]) for i in range(19)]
        rows, filler = _with_filler(_cooccur([a[0], b[0]], 6))
        candidates, _ = svc.compute_candidates(
            mention_rows=rows, entity_rows=[a, b, filler, *hub], run_id=uuid.uuid4()
        )
        # QC is a hub, so the pair is NOT excluded by the attribute arm -> still novel.
        assert len(candidates) == 1
        # ...but the shared hub country must not register as corroboration.
        assert "country" not in candidates[0].kb_corroboration_detail["fields"]
        assert candidates[0].kb_corroboration_count == 0
