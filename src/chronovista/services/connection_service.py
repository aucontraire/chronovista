"""ConnectionService — the policy seam over the Neo4j connection repository (Feature 112).

The repository owns the Cypher; this service owns the *policy*. It exists to keep domain
decisions out of the Typer presentation command: ``resolve()`` (token → entity, with the
ambiguous-name policy) and ``_apply_coincidence_policy`` (the US2 scoped, origin-gated
suppression) are real policy that should not live in a CLI renderer. In US1 the policy is
thin — the reviewed-relationship short-circuit, the by-kind ordering, and the single
log-specificity ranking all come from the repository and the result model and flow through
unchanged; US2 adds the coincidence suppression. That a future API could reuse the same seam
is a bonus, not the reason it exists.
"""

from __future__ import annotations

from uuid import UUID

from chronovista.models.graph_connection import GraphConnection, GraphNode
from chronovista.repositories.neo4j_graph_repository import (
    EntityNotInGraphError,
    Neo4jGraphRepository,
)


class AmbiguousEntityError(LookupError):
    """A CLI token matched more than one entity by name; the user must disambiguate by id."""

    def __init__(self, token: str, matches: list[GraphNode]) -> None:
        super().__init__(f"'{token}' matches {len(matches)} entities")
        self.token = token
        self.matches = matches


class ConnectionService:
    """Answer "how are entity A and entity B connected?" with policy applied."""

    def __init__(self, repository: Neo4jGraphRepository) -> None:
        self._repository = repository

    async def resolve(self, token: str) -> GraphNode:
        """Resolve a CLI token (an entity UUID, or an exact entity name) to a :class:`GraphNode`.

        Raises
        ------
        EntityNotInGraphError
            No entity matches the token.
        AmbiguousEntityError
            The name matches more than one entity (the user must pick by id).
        """
        try:
            entity_id: UUID | None = UUID(token)
        except ValueError:
            entity_id = None
        if entity_id is not None:
            return await self._repository.get_entity_node(entity_id)
        matches = await self._repository.find_entities_by_name(token)
        if not matches:
            raise EntityNotInGraphError(token, kind="name")
        if len(matches) > 1:
            raise AmbiguousEntityError(token, matches)
        return matches[0]

    async def connect(
        self,
        a_id: UUID,
        b_id: UUID,
        *,
        max_hops: int = 4,
        max_category_size: int | None = None,
    ) -> GraphConnection:
        """Every connecting kind between two entities, in by-kind order, plus the reviewed verdict.

        Parameters
        ----------
        a_id, b_id : UUID
            The two entities to connect.
        max_hops : int
            Traversal hop budget for the asserted tier (default 4).
        max_category_size : int | None
            A named tractability bound on a shared category's global size (default ``None`` —
            no cut; rank by log-specificity, never filter by breadth).

        Returns
        -------
        GraphConnection
            ``has_connection`` is False when neither a verdict nor any inferred chain exists.
        """
        result = await self._repository.connection(
            a_id, b_id, max_hops=max_hops, max_category_size=max_category_size
        )
        return self._apply_coincidence_policy(result)

    @staticmethod
    def _apply_coincidence_policy(result: GraphConnection) -> GraphConnection:
        """Scoped, origin-gated coincidence suppression (US2).

        A HIGH-confidence coincidence (origin human / reaudited_c) is a reliable negative over
        its ``judged_over`` co-occurrence channels: those chains are dropped. It NEVER suppresses
        an asserted / shared_category / shared_referent chain (the model forbids those in
        ``judged_over``), and every surviving chain is still shown. A ``suggested_agreed``
        coincidence is medium-confidence — treated as no verdict, so nothing is suppressed.
        """
        verdict = result.reviewed_verdict
        if verdict is None or verdict.verdict != "coincidence":
            return result
        if verdict.confidence != "high":
            # suggested_agreed (medium) → treated as no verdict: drop it entirely and suppress
            # nothing, so a medium-only pair doesn't read as having a (negative) verdict.
            return result.model_copy(update={"reviewed_verdict": None})
        suppressed = set(verdict.judged_over)
        kept = [chain for chain in result.chains if chain.kind not in suppressed]
        return result.model_copy(update={"chains": kept})
