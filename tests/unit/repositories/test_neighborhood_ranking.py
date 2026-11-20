"""Mutation-verified tests for the Explore neighborhood cap-ranking (Feature 115, FR-004/SC-005).

The load-bearing guarantee: when the node cap binds, co-occurrence neighbors are dropped
BEFORE verified / category ones. These test the pure ``rank_and_cap_neighbors`` core directly,
so the guarantee holds without a live graph. Node keys are synthetic (no library content).
Mutation check: swap _LAYER_RANK so co-occurrence sorts first, and
``test_co_occurrence_dropped_first`` fails.
"""

from __future__ import annotations

from chronovista.models.graph_connection import EdgeLayer
from chronovista.repositories.neo4j_graph_repository import (
    NeighborCandidate,
    rank_and_cap_neighbors,
)


def _c(
    key: str, layer: EdgeLayer, sort_size: int = 0, name: str = ""
) -> NeighborCandidate:
    return NeighborCandidate(
        node_key=key, layer=layer, sort_size=sort_size, name=name or key
    )


def test_co_occurrence_dropped_first_when_cap_binds() -> None:
    # 2 verified + 2 co-occurrence, room for only 2 neighbors (limit 3, 1 seed) → the two
    # verified survive, both co-occurrence are dropped (FR-004/SC-005).
    candidates = [
        _c("v1", EdgeLayer.VERIFIED),
        _c("v2", EdgeLayer.VERIFIED),
        _c("co1", EdgeLayer.CO_OCCURRENCE),
        _c("co2", EdgeLayer.CO_OCCURRENCE),
    ]
    kept, truncated, total = rank_and_cap_neighbors(
        candidates, seed_count=1, limit=3, ceiling=250
    )
    assert set(kept) == {"v1", "v2"}
    assert truncated is True
    assert total == 4


def test_category_kept_over_co_occurrence() -> None:
    candidates = [_c("cat", EdgeLayer.CATEGORY), _c("co", EdgeLayer.CO_OCCURRENCE)]
    kept, _, _ = rank_and_cap_neighbors(candidates, seed_count=1, limit=2, ceiling=250)
    assert kept == ["cat"]


def test_more_specific_category_first() -> None:
    # smaller sort_size (globalSize) = more specific = kept first within the category layer
    candidates = [
        _c("broad", EdgeLayer.CATEGORY, sort_size=900),
        _c("specific", EdgeLayer.CATEGORY, sort_size=10),
    ]
    kept, _, _ = rank_and_cap_neighbors(candidates, seed_count=1, limit=2, ceiling=250)
    assert kept == ["specific"]


def test_dedupe_keeps_best_rank() -> None:
    # same neighbor seen as both a verified and a co-occurrence edge → deduped to verified.
    candidates = [
        _c("n", EdgeLayer.CO_OCCURRENCE),
        _c("n", EdgeLayer.VERIFIED),
    ]
    kept, truncated, total = rank_and_cap_neighbors(
        candidates, seed_count=1, limit=10, ceiling=250
    )
    assert kept == ["n"]
    assert total == 1
    assert truncated is False


def test_ceiling_caps_below_limit() -> None:
    candidates = [_c(f"v{i}", EdgeLayer.VERIFIED, name=f"v{i:02d}") for i in range(20)]
    kept, truncated, total = rank_and_cap_neighbors(
        candidates, seed_count=2, limit=60, ceiling=5
    )
    assert len(kept) == 3  # ceiling 5 - 2 seeds
    assert truncated is True
    assert total == 20


def test_not_truncated_when_all_fit() -> None:
    candidates = [_c("v1", EdgeLayer.VERIFIED), _c("cat", EdgeLayer.CATEGORY)]
    kept, truncated, total = rank_and_cap_neighbors(
        candidates, seed_count=1, limit=60, ceiling=250
    )
    assert set(kept) == {"v1", "cat"}
    assert truncated is False
    assert total == 2
