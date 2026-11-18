"""Tests for the connection-explorer result models (Feature 112)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from chronovista.models.graph_connection import (
    ConnectionChain,
    ConnectionKind,
    GraphConnection,
    GraphNode,
    PathStep,
    ReviewedVerdict,
)


def _node(name: str, *, bridge: bool = False) -> GraphNode:
    return GraphNode(entity_id=None if bridge else uuid4(), name=name, is_bridge=bridge)


def _chain(kind: ConnectionKind, end: GraphNode, **kw: Any) -> ConnectionChain:
    return ConnectionChain(
        kind=kind, steps=[PathStep(edge_type="E", kind=kind, to_node=end)], **kw
    )


class TestConnectionKind:
    def test_declaration_order_is_strongest_first(self) -> None:
        # Enum order IS the presentation/sort order, incl. the relative order of the four
        # co-occurrence kinds (which share a prefix and are otherwise indistinguishable).
        assert [k.value for k in ConnectionKind] == [
            "asserted",
            "shared_category",
            "co_occurrence_transcript",
            "co_occurrence_titledesc",
            "co_occurrence_tags",
            "co_occurrence_manual",
        ]

    def test_co_occurrence_is_four_distinct_kinds(self) -> None:
        co = [k for k in ConnectionKind if k.value.startswith("co_occurrence_")]
        assert len(co) == 4


class TestGraphNode:
    def test_string_uuid_is_coerced(self) -> None:
        # Neo4j stores entityId as a string; strict=True would otherwise reject it.
        raw = uuid4()
        node = GraphNode(entity_id=str(raw), name="X")
        assert node.entity_id == raw
        assert isinstance(node.entity_id, UUID)

    def test_bridge_has_no_entity_id(self) -> None:
        node = GraphNode(name="Cat", label="Category", is_bridge=True)
        assert node.entity_id is None


class TestConnectionChain:
    def test_length_is_computed_from_steps(self) -> None:
        b = _node("B")
        chain = ConnectionChain(
            kind=ConnectionKind.ASSERTED,
            steps=[
                PathStep(
                    edge_type="X", kind=ConnectionKind.ASSERTED, to_node=_node("M")
                ),
                PathStep(edge_type="Y", kind=ConnectionKind.ASSERTED, to_node=b),
            ],
        )
        assert chain.length == 2
        assert chain.model_dump()["length"] == 2  # computed field serializes

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConnectionChain(kind=ConnectionKind.ASSERTED, steps=[])

    def test_score_allowed_only_on_shared_category(self) -> None:
        b = _node("B")
        _chain(ConnectionKind.SHARED_CATEGORY, b, score=3.5)  # ok
        with pytest.raises(ValueError):
            _chain(ConnectionKind.ASSERTED, b, score=3.5)


class TestReviewedVerdict:
    def test_relationship_requires_relation(self) -> None:
        with pytest.raises(ValueError):
            ReviewedVerdict(verdict="relationship", origin="human")
        ReviewedVerdict(
            verdict="relationship", relation="associated_with", origin="human"
        )

    def test_coincidence_must_not_carry_relation(self) -> None:
        with pytest.raises(ValueError):
            ReviewedVerdict(verdict="coincidence", relation="covers", origin="human")
        ReviewedVerdict(verdict="coincidence", origin="human")

    def test_confidence_is_computed_from_origin(self) -> None:
        assert (
            ReviewedVerdict(verdict="coincidence", origin="human").confidence == "high"
        )
        assert (
            ReviewedVerdict(verdict="coincidence", origin="reaudited_c").confidence
            == "high"
        )
        medium = ReviewedVerdict(verdict="coincidence", origin="suggested_agreed")
        assert medium.confidence == "medium"
        assert (
            medium.model_dump()["confidence"] == "medium"
        )  # computed field serializes

    def test_settled_defaults_true(self) -> None:
        assert ReviewedVerdict(verdict="coincidence", origin="human").settled is True

    def test_judged_over_defaults_to_the_co_occurrence_kinds(self) -> None:
        # A queue-derived verdict defaults to suppressing its co-occurrence channels —
        # never an empty scope (which would suppress nothing).
        verdict = ReviewedVerdict(verdict="coincidence", origin="human")
        assert set(verdict.judged_over) == {
            ConnectionKind.CO_OCCURRENCE_TRANSCRIPT,
            ConnectionKind.CO_OCCURRENCE_TITLEDESC,
            ConnectionKind.CO_OCCURRENCE_TAGS,
            ConnectionKind.CO_OCCURRENCE_MANUAL,
        }

    def test_judged_over_rejects_non_co_occurrence_kinds(self) -> None:
        # The spec's hard "never": a verdict may not be judged over asserted/shared_category.
        with pytest.raises(ValueError):
            ReviewedVerdict(
                verdict="coincidence",
                origin="human",
                judged_over=[ConnectionKind.ASSERTED],
            )
        # an explicit co-occurrence subset is allowed
        ReviewedVerdict(
            verdict="coincidence",
            origin="human",
            judged_over=[ConnectionKind.CO_OCCURRENCE_TAGS],
        )


class TestGraphConnection:
    def test_has_connection_false_when_empty(self) -> None:
        a, b = _node("A"), _node("B")
        gc = GraphConnection(entity_a=a, entity_b=b, searched_max_hops=0)
        assert gc.has_connection is False
        assert gc.model_dump()["has_connection"] is False

    def test_has_connection_true_with_chain(self) -> None:
        a, b = _node("A"), _node("B")
        gc = GraphConnection(
            entity_a=a,
            entity_b=b,
            chains=[_chain(ConnectionKind.ASSERTED, b)],
            searched_max_hops=4,
        )
        assert gc.has_connection is True

    def test_has_connection_true_with_verdict_only(self) -> None:
        a, b = _node("A"), _node("B")
        verdict = ReviewedVerdict(
            verdict="relationship", relation="associated_with", origin="human"
        )
        gc = GraphConnection(
            entity_a=a, entity_b=b, reviewed_verdict=verdict, searched_max_hops=0
        )
        assert gc.has_connection is True

    def test_chains_sorted_strongest_first(self) -> None:
        a, b = _node("A"), _node("B")
        weak = _chain(ConnectionKind.CO_OCCURRENCE_TAGS, b)
        strong = _chain(ConnectionKind.ASSERTED, b)
        gc = GraphConnection(
            entity_a=a, entity_b=b, chains=[weak, strong], searched_max_hops=4
        )
        assert [c.kind for c in gc.chains] == [
            ConnectionKind.ASSERTED,
            ConnectionKind.CO_OCCURRENCE_TAGS,
        ]

    def test_co_occurrence_kinds_sort_in_enum_order(self) -> None:
        # The four co-occurrence kinds share a prefix; only _KIND_ORDER (enum order)
        # separates them, so a scrambling bug would be invisible without this.
        a, b = _node("A"), _node("B")
        shuffled = [
            _chain(ConnectionKind.CO_OCCURRENCE_MANUAL, b),
            _chain(ConnectionKind.CO_OCCURRENCE_TRANSCRIPT, b),
            _chain(ConnectionKind.CO_OCCURRENCE_TAGS, b),
            _chain(ConnectionKind.CO_OCCURRENCE_TITLEDESC, b),
        ]
        gc = GraphConnection(
            entity_a=a, entity_b=b, chains=shuffled, searched_max_hops=4
        )
        assert [c.kind for c in gc.chains] == [
            ConnectionKind.CO_OCCURRENCE_TRANSCRIPT,
            ConnectionKind.CO_OCCURRENCE_TITLEDESC,
            ConnectionKind.CO_OCCURRENCE_TAGS,
            ConnectionKind.CO_OCCURRENCE_MANUAL,
        ]

    def test_at_most_one_chain_per_kind(self) -> None:
        a, b = _node("A"), _node("B")
        with pytest.raises(ValueError):
            GraphConnection(
                entity_a=a,
                entity_b=b,
                chains=[
                    _chain(ConnectionKind.ASSERTED, b),
                    _chain(ConnectionKind.ASSERTED, b),
                ],
                searched_max_hops=4,
            )

    def test_chain_must_end_at_entity_b(self) -> None:
        a, b = _node("A"), _node("B")
        with pytest.raises(ValueError):
            GraphConnection(
                entity_a=a,
                entity_b=b,
                chains=[_chain(ConnectionKind.ASSERTED, a)],  # ends at A, not B
                searched_max_hops=4,
            )

    def test_bridge_terminus_with_matching_name_is_rejected(self) -> None:
        # H1: entity_b is a real entity (has an id); a chain ending on a BRIDGE node
        # (id None) whose name merely coincides is NOT entity_b — it stops short.
        b = _node("TARGET")  # has an id
        bridge = GraphNode(entity_id=None, name="TARGET", is_bridge=True)
        with pytest.raises(ValueError):
            GraphConnection(
                entity_a=_node("A"),
                entity_b=b,
                chains=[_chain(ConnectionKind.SHARED_CATEGORY, bridge, score=1.0)],
                searched_max_hops=4,
            )

    def test_name_only_endpoint_accepts_name_match(self) -> None:
        # The name-compare fallback is sound only when entity_b itself has no id.
        a = _node("A", bridge=True)
        b = GraphNode(entity_id=None, name="B")
        end = GraphNode(entity_id=None, name="B")
        gc = GraphConnection(
            entity_a=a,
            entity_b=b,
            chains=[_chain(ConnectionKind.ASSERTED, end)],
            searched_max_hops=4,
        )
        assert gc.has_connection is True
