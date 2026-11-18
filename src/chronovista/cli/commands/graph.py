"""CLI commands for the connection explorer (Feature 112).

``chronovista graph`` groups the dev-scoped graph commands. The engine is read-only and
connects lazily; when the graph is unavailable the commands degrade with a clear message
rather than a traceback. The ``connect`` command (US1) lands on this sub-app next.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="graph",
    help="🕸️ Explore connections between entities in the dev-scoped graph.",
    no_args_is_help=True,
)


@app.callback()
def graph() -> None:
    """Explore how entities are connected in the dev-scoped graph."""
