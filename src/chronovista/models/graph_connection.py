"""Pydantic result models for the connection explorer (Feature 112).

The engine answers "how are entity A and entity B connected?" by returning a
:class:`GraphConnection`: the human-reviewed verdict where one exists, plus one labeled
:class:`ConnectionChain` per inferred connecting kind, in a fixed by-kind order. These are domain
models (not API schemas) so the repository can return them without depending on the API
layer, mirroring the Feature-066 association models.

Ranking note: a ``shared_category`` chain's :attr:`ConnectionChain.score` is a SINGLE
log-compressed specificity sum — ``Σ max(0, ln(1e6 / globalSize(c)))`` over the shared
categories, whose count enters as the number of terms. There is deliberately no separate
"count" field: a second ranking key invites a re-invented blend (measured review).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class ConnectionKind(str, Enum):
    """The inferred connection kinds, declared in a fixed by-kind presentation order.

    Declaration order IS presentation order and the sort key for a result's chains. It is a
    CATEGORICAL precedence of connection type (a composed/stated fact is listed before a
    co-mention) — NOT a numeric strength ranking across kinds. Each scored tier's ``score``
    is a WITHIN-TIER quantity on its own scale: asserted/shared_referent use
    ``ln(entity_count / local_degree)`` (reference ≈ a few thousand entities), shared_category
    uses ``ln(1e6 / globalSize)`` (reference 1e6). Those are different references over
    different populations, so a chain's score and a category's score are NOT comparable and
    the list is never ordered by score across kinds.

    Co-occurrence is four DISTINCT kinds (one per presence channel), never merged or
    weighted into a single score (measured review §4). The human-reviewed layer is NOT a
    kind — it is a short-circuit (:class:`ReviewedVerdict`).
    """

    ASSERTED = "asserted"
    SHARED_REFERENT = "shared_referent"
    SHARED_CATEGORY = "shared_category"
    CO_OCCURRENCE_TRANSCRIPT = "co_occurrence_transcript"
    CO_OCCURRENCE_TITLEDESC = "co_occurrence_titledesc"
    CO_OCCURRENCE_TAGS = "co_occurrence_tags"
    CO_OCCURRENCE_MANUAL = "co_occurrence_manual"


# Enum-declaration order = by-kind presentation/sort order (categorical, not a score ranking).
_KIND_ORDER: dict[ConnectionKind, int] = {
    kind: index for index, kind in enumerate(ConnectionKind)
}

# The four co-occurrence channels — the default scope a queue-derived verdict was judged
# over (these verdicts came from the co-occurrence review queue).
_CO_OCCURRENCE_KINDS: list[ConnectionKind] = [
    kind for kind in ConnectionKind if kind.value.startswith("co_occurrence_")
]

# Kinds that carry a log-specificity `score`: asserted (its weakest intermediate hub's
# specificity), shared_category (over category globalSize), and shared_referent (the shared
# node's local degree). The four co-occurrence kinds never carry a score.
_SCORED_KINDS: set[ConnectionKind] = {
    ConnectionKind.ASSERTED,
    ConnectionKind.SHARED_CATEGORY,
    ConnectionKind.SHARED_REFERENT,
}


class ReviewedVerdict(BaseModel):
    """A human-judgment short-circuit for a pair (NOT a :class:`ConnectionKind`).

    A ``relationship`` verdict is an authoritative *positive* (a confirmed tie), surfaced
    ahead of the inferred chains. A ``coincidence`` verdict is NOT a blanket negative: it
    is the least-reliable class and was judged only over its source channels
    (``judged_over``). How a coincidence renders (negative vs ignored) is origin-gated and
    applied by the service, never by this model.

    Attributes
    ----------
    verdict : {"relationship", "coincidence"}
        The human judgment.
    relation : {"associated_with", "covers", "co_cast"} or None
        Set iff ``verdict == "relationship"``; ``None`` for coincidence.
    origin : {"human", "reaudited_c", "suggested_agreed"}
        Where the verdict came from; drives ``confidence`` and the coincidence rendering.
    confidence : {"high", "medium"}
        ``high`` for human / ``reaudited_c``; ``medium`` for ``suggested_agreed``.
    settled : bool
        ``False`` for the known resort-defect set (verdicts needing re-review).
    judged_over : list[ConnectionKind]
        The kinds the verdict was actually judged over. A coincidence may suppress ONLY
        these — never an ``asserted`` or ``shared_category`` chain. Defaults to the
        co-occurrence kinds (the queue these verdicts came from).
    provenance : str
        Free-text provenance note.
    """

    verdict: Literal["relationship", "coincidence"]
    relation: Literal["associated_with", "covers", "co_cast"] | None = None
    origin: Literal["human", "reaudited_c", "suggested_agreed"]
    settled: bool = True
    judged_over: list[ConnectionKind] = Field(
        default_factory=lambda: list(_CO_OCCURRENCE_KINDS)
    )
    provenance: str = ""

    model_config = ConfigDict(strict=True)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.verdict == "relationship" and self.relation is None:
            raise ValueError("a 'relationship' verdict requires a relation")
        if self.verdict == "coincidence" and self.relation is not None:
            raise ValueError("a 'coincidence' verdict must not carry a relation")
        # A verdict is judged over the co-occurrence channels it came from; it may never
        # suppress an asserted or shared_category chain (spec), so forbid those here.
        if not set(self.judged_over) <= set(_CO_OCCURRENCE_KINDS):
            raise ValueError("judged_over may contain only co-occurrence kinds")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence(self) -> Literal["high", "medium"]:
        """Derived from origin: ``medium`` for ``suggested_agreed``, else ``high``.

        A total, deterministic function of origin (matching the loader), so it is computed
        rather than stored — there is no legitimate independent value for it to get wrong.
        """
        return "medium" if self.origin == "suggested_agreed" else "high"


class GraphNode(BaseModel):
    """A node on a connection path: an entity, or a non-entity bridge (category / stub).

    Attributes
    ----------
    entity_id : UUID or None
        The Postgres entity UUID; ``None`` for a non-entity bridge (a category or a
        Wikidata stub shared as a referent).
    name : str
        Display name.
    label : str
        The node's graph label/type (e.g. ``Person``, ``Category``, ``WikidataItem``).
    is_bridge : bool
        True for a bridge node (category intermediary or stub shared referent), which may
        never be a transit node on an asserted path — only a shared endpoint.
    """

    entity_id: UUID | None = None
    name: str
    label: str = ""
    is_bridge: bool = False
    # Count of this entity's WIKIDATA KB edges (reviewed edges excluded — they are human
    # judgments, not knowledge-base coverage) — set only for the queried endpoints, so "no
    # asserted path" can be attributed to under-enrichment vs a genuine non-relationship
    # (FR-016). None for bridges and intermediate nodes.
    kb_degree: int | None = None

    model_config = ConfigDict(strict=True)

    @field_validator("entity_id", mode="before")
    @classmethod
    def _coerce_entity_id(cls, value: str | UUID | None) -> UUID | None:
        """Coerce a string UUID (how Neo4j stores ``entityId``) to a ``UUID`` at the boundary.

        ``strict=True`` otherwise rejects the string form the graph delivers; handling it
        here means the Phase-3 repository can build nodes straight from graph rows.
        """
        if isinstance(value, str):
            return UUID(value)
        return value


class PathStep(BaseModel):
    """One hop ``A → … → B``: the edge taken, its kind, and the node it lands on.

    Attributes
    ----------
    edge_type : str
        The concrete graph relationship type traversed (e.g. ``IN_CATEGORY``,
        ``CO_OCCURS_TRANSCRIPT``, a Wikidata rel type).
    kind : ConnectionKind
        The connection kind this step belongs to.
    to_node : GraphNode
        The node reached by this hop.
    specificity : float or None
        For a shared-category step, the term ``max(0, ln(1e6 / globalSize))``; ``None``
        otherwise.
    """

    edge_type: str
    kind: ConnectionKind
    to_node: GraphNode
    specificity: float | None = None
    forward: bool = True

    model_config = ConfigDict(strict=True)


class ConnectionChain(BaseModel):
    """One inferred connection of a single kind: an ordered path ``A → … → B``.

    Attributes
    ----------
    kind : ConnectionKind
        The connection kind (also the sort key within a result).
    steps : list[PathStep]
        The ordered hops from A to B; non-empty, last step lands on B.
    truncated : bool
        True if the search hit its hop budget before fully resolving this chain.
    score : float or None
        The log-specificity ranking value for a scored kind (asserted / shared_category /
        shared_referent); ``None`` for a co-occurrence chain. For shared_category it is
        ``Σ max(0, ln(1e6 / globalSize(c)))`` over the shared categories; for a chain, its
        weakest intermediate hub's specificity. One field — never a separate ``count`` field.
    """

    kind: ConnectionKind
    steps: list[PathStep]
    truncated: bool = False
    score: float | None = None

    model_config = ConfigDict(strict=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def length(self) -> int:
        """Number of hops (== ``len(steps)``); computed so it can never disagree."""
        return len(self.steps)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.steps:
            raise ValueError("a ConnectionChain must have at least one step")
        if self.score is not None and self.kind not in _SCORED_KINDS:
            raise ValueError(
                "score is only meaningful for an asserted, shared_category, or "
                "shared_referent chain"
            )
        return self


class GraphConnection(BaseModel):
    """The result: the reviewed verdict (if any) + one chain per inferred kind, in by-kind order.

    Attributes
    ----------
    entity_a, entity_b : GraphNode
        The two endpoints the connection was searched between.
    reviewed_verdict : ReviewedVerdict or None
        A ``relationship`` verdict leads as the authoritative answer; a ``coincidence`` is
        scoped/origin-gated by the service and never overrides an asserted/category chain.
        The inferred ``chains`` are always populated alongside it (a false coincidence is
        invisible to the inferred signals, so showing them keeps it recoverable).
    chains : list[ConnectionChain]
        One chain per inferred connecting kind, ordered by kind (enforced here); the order
        is categorical, not a cross-kind score ranking. Empty ⇒ no inferred connection.
    searched_max_hops : int
        The hop budget the search used.
    any_truncated : bool
        True if any chain (or the search) hit the hop budget.
    """

    entity_a: GraphNode
    entity_b: GraphNode
    reviewed_verdict: ReviewedVerdict | None = None
    chains: list[ConnectionChain] = Field(default_factory=list)
    searched_max_hops: int = Field(ge=0)
    any_truncated: bool = False

    model_config = ConfigDict(strict=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_connection(self) -> bool:
        """True if there is a reviewed verdict or at least one inferred chain."""
        return bool(self.reviewed_verdict or self.chains)

    @model_validator(mode="after")
    def _check(self) -> Self:
        kinds = [chain.kind for chain in self.chains]
        if len(kinds) != len(set(kinds)):
            raise ValueError("at most one chain per ConnectionKind")
        # Guarantee the by-kind order by construction (sort, don't merely assert), so a
        # service ordering bug can't produce an out-of-kind-order result.
        self.chains.sort(key=lambda chain: _KIND_ORDER[chain.kind])
        # Every chain must actually land on entity_b — catches a malformed path that stops
        # short of the target. When entity_b is a real entity (has an id), the last node must
        # carry THAT id; a bridge terminus (id None) with a coincidentally-matching name is
        # NOT entity_b. The name comparison is a sound fallback only for a name-only endpoint.
        b_id = self.entity_b.entity_id
        for chain in self.chains:
            last = chain.steps[-1].to_node
            if b_id is not None:
                ends_at_b = last.entity_id == b_id
            else:
                ends_at_b = last.entity_id is None and last.name == self.entity_b.name
            if not ends_at_b:
                raise ValueError(f"{chain.kind.value} chain does not end at entity_b")
        return self
