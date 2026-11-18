"""Neo4j-backed connection-explorer repository (Feature 112).

Reads the dev-scoped graph (read-only) to answer "how are entity A and entity B
connected?", returning a :class:`GraphConnection`: the human-reviewed verdict where one
exists, plus one labeled chain per inferred connecting kind, strongest-first.

This is the Phase-2 SHELL. The tiered Cypher search (asserted/reviewed → shared-category →
co-occurrence), the log-specificity ranking, and proven-absence handling land in US1+
(tasks T014+).
"""

from __future__ import annotations

from uuid import UUID

from chronovista.graph import Neo4jClient
from chronovista.models.graph_connection import GraphConnection


class Neo4jGraphRepository:
    """Read-only access to the connection graph.

    All graph reads go through this repository (Principle III). It depends on a
    :class:`Neo4jClient` — a distinct data source from the Postgres repositories — and
    never writes (FR-008).
    """

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def connection(
        self,
        a_id: UUID,
        b_id: UUID,
        *,
        max_hops: int = 4,
        max_category_size: int | None = None,
    ) -> GraphConnection:
        """Return how two entities are connected (reviewed verdict + inferred chains).

        Parameters
        ----------
        a_id, b_id : UUID
            The two entities to connect.
        max_hops : int
            The traversal hop budget for the asserted tier (default 4).
        max_category_size : int | None
            A NAMED tractability bound on a shared category's global size — NOT a signal
            ceiling. ``None`` (the default) applies no cut: rank by log-specificity, never
            filter by breadth (measured review).

        Returns
        -------
        GraphConnection
            The result, with ``has_connection`` False when neither a verdict nor any
            inferred chain exists.
        """
        raise NotImplementedError(
            "Neo4jGraphRepository.connection is implemented in US1 (tasks T014+)"
        )
