"""Neo4j graph access for the dev-scoped connection explorer (Feature 112).

A distinct data source from the Postgres ``db/`` layer: a lazy, read-only async client
over the ``--profile graph`` Neo4j container. Import stays driver-free until a connection
is actually opened.
"""

from chronovista.graph.client import GraphUnavailableError, Neo4jClient

__all__ = ["GraphUnavailableError", "Neo4jClient"]
