"""CLI commands for API server management."""

from __future__ import annotations

import typer

api_app = typer.Typer(
    name="api",
    help="API server management commands",
    no_args_is_help=True,
)


@api_app.command()
def start(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the server on"),
    production: bool = typer.Option(
        False, "--production", help="Run in production mode"
    ),
) -> None:
    """
    Start the chronovista API server.

    Development mode (default): Auto-reload enabled, debug logging.
    Production mode: Multiple workers, warning-level logging.

    Examples:
        chronovista api start
        chronovista api start --port 3000
        chronovista api start --production
        chronovista api start -p 8080 --production
    """
    import uvicorn

    if production:
        uvicorn.run(
            "chronovista.api.main:app",
            host="127.0.0.1",
            port=port,
            workers=2,
            log_level="warning",
        )
    else:
        uvicorn.run(
            "chronovista.api.main:app",
            host="127.0.0.1",
            port=port,
            reload=True,
            log_level="info",
        )
